# 작업: 의사웹 "예약 일정" 팝업 (Doctor_DetailReservation, F-07) — 백엔드 보완 + 프론트 화면

## 배경
- 프로젝트: 마음브릿지 (정신과 환자 비대면 추적 관리). 프론트 frontapp(Next.js), 백엔드 backapp(FastAPI)
- 참고 자료: C:\Users\ohjih\OneDrive\Desktop\KDT-중간 자료\
  - figma_images/Doctor_DetailReservation.png (예약 일정 팝업)
  - 3조_마음브릿지_요구사항_명세_2026-11-24.pdf (연결-06 진료 예약 확정, 연결-07 양쪽 캘린더 등록)
- F-07 API 5개는 이미 있다 (doctor_api.py 17~21번, 임의 결정 D-21~D-29).
  백엔드는 새로 만들지 않고 화면에 필요한데 응답에 없는 것만 채운다.
  기존 동작·응답 필드·테스트는 바꾸지 않는다 (필드는 추가만).

## 작업 순서
1. 백엔드 ①~⑥
2. 프론트: 타입 → API → 컴포넌트 → 페이지
각 단계마다 멈추고 고친 파일과 핵심 코드를 설명해 줘. 내가 직접 따라 쳐 보면서 공부할 거야.

====================================================================
# PART 1. 백엔드 (backapp)
====================================================================

## 지금 구현 vs 팝업 화면
| 화면 | 지금 | 할 일 |
|---|---|---|
| 제목 아래 `김민준 · 다음 예약 D-13` | 없음 | ① nextAppointment |
| 월 캘린더 점 (파랑 예약 / 회색 내원 완료) | items의 status로 프론트가 계산 | 그대로 |
| 날짜 카드 `재진 · 이은솔` | 의사 이름 없음 | ② doctorName |
| 날짜 카드 `진료실01 · 건강보험` | roomId만, 보험 없음 | ② roomName, insuranceType |
| 심리검사 카드 `PHQ-9 · GAD-7 · BDI-II` | tests 있음 | 그대로 |
| 정보 박스 `예약 경로` | 없음 | ② bookingSource, autoBookedAfter |
| 정보 박스 `알림` | 없음 | ② reminders |
| 정보 박스 `요청 사항` | patientNote 있음 | 그대로 |
| `예약 이력` (여러 달) | items는 그 달 것만 | ③ history |
| `10.21에서 변경 (환자 요청)` | 이력의 requestedBy가 항상 doctor | ④ requestedBy |
| `변경 1회 · 노쇼 0회` | rescheduleCount, noShowCount 있음 | 그대로 |
| `예약 추가` 버튼 | insuranceType 못 받음, 검사 목록 검증 없음 | ⑤ |
| 예약이 생기는 모든 경로 | 생성 함수가 하나로 정해져 있지 않음 | ⑥ |

### ① 다음 예약 — GET /doctor/patients/{patientId}/appointments
- PatientAppointmentsResponseDTO에 next_appointment: NextAppointmentDTO | None = None 추가
  - NextAppointmentDTO: appointment_id, scheduled_at(KstDateTime), d_day: int
- 대상: 내 예약(doctor_id = 나) 중 지금 이후이고 booked·waiting인 가장 이른 1건. month와 상관없음
- d_day = (예약 날짜 - today_kst()).days (KST 날짜 기준, 오늘이면 0)
- 레포지토리에 find_next_appointment(doctor_id, patient_id, now) 추가

### ② 예약 1건에 표시용 필드 추가 — AppointmentDetailResponseDTO
- 추가 필드 (모두 기본값 있음)
  - doctor_name: str | None ← appointment.doctor.name
  - room_name: str | None ← appointment.room.name
  - insurance_type: str | None
  - booking_source: AppointmentBookingSource | None
  - auto_booked_after: date | None — booking_source = auto_after_visit일 때만 (아래 규칙)
  - reminders: list[AppointmentReminderDTO] = []
    - AppointmentReminderDTO: title, sent_at(KstDateTime | None), created_at(KstDateTime)
- find_appointment, find_patient_appointments의 selectinload에 Appointment.doctor, Appointment.room, Appointment.notifications 추가
- reminders: appointment.notifications 중 user_id == patient_id 인 것을 created_at 순으로
- auto_booked_after (임의 결정 D-38): 같은 환자·같은 병원의 completed 예약 중
  completed_at <= 이 예약.created_at 인 가장 늦은 예약의 날짜(KST). 없으면 None
  - 예약 수만큼 쿼리가 늘지 않게, 서비스에서 환자의 완료 예약 목록을 한 번 불러와 파이썬에서 고른다
- _to_appointment_detail에서 채운다 (추가·변경·취소·상태 변경 응답에도 자동으로 들어감)

### ③ 예약 이력 — 같은 GET 응답에 history 추가
- PatientAppointmentsResponseDTO에 history: list[AppointmentHistoryDTO]
  - AppointmentHistoryDTO: appointment_id, scheduled_at, kind, visit_type, status,
    changed_from: KstDateTime | None (가장 최근 reschedule의 from_at),
    change_requested_by: RequestedBy | None
- 범위: 내 예약·이 환자, 전체 기간, scheduled_at 내림차순, 취소 포함
- 개수: 최근 20건 (임의 결정 D-39). HISTORY_LIMIT = 20 상수
- 같은 날 진료+심리검사를 한 줄로 묶는 건 프론트가 한다
- 레포지토리에 find_appointment_history(doctor_id, patient_id, limit) 추가 (selectinload(Appointment.changes))

### ④ 누가 요청한 변경인지 — PUT /doctor/appointments/{id}, POST .../cancel
- AppointmentRescheduleDTO, AppointmentCancelDTO에 requested_by: RequestedBy = RequestedBy.DOCTOR 추가
- 레포지토리 reschedule_appointment, cancel_appointment가 RequestedBy.DOCTOR 대신 받은 값을 넣도록 인자 추가

### ⑤ 예약 추가 입력 보강 — POST /doctor/appointments
- AppointmentCreateDTO
  - insurance_type: str | None = Field(default=None, max_length=20) 추가 → 저장 값에 넣는다
  - tests: list[str] | None → list[Instrument] | None
  - model_validator: kind = treatment면 tests는 None, psych_test면 1개 이상·중복 없음 (어기면 422)
- 서비스: 진료실을 보냈으면 treatment → consult, psych_test → exam 인지 확인,
  아니면 400 "예약 종류와 맞지 않는 진료실입니다." (임의 결정 D-40)

### ⑥ 예약 생성은 doctor_repository.create_appointment 하나로 (연결-07)
- create_appointment(values, schedule_type, title)는 Appointment 1건과 환자·의사 Schedule 2건을
  한 트랜잭션으로 만든다. insert(Appointment)를 직접 쓰면 캘린더 등록이 빠지므로 금지
- 지금 이 함수를 쓰는 곳은 POST /doctor/appointments (booking_source=doctor) 하나
- 아직 없는 경로를 나중에 만들 때도 같은 함수를 호출한다
  - 채팅·전화로 확정되는 경로 (연결-06): contact_method=chat|phone, request_id 포함
  - 진료 후 자동 예약: booking_source=auto_after_visit
  - 환자 앱 예약: booking_source=patient_app
- schedule_type / title은 doctor_service의 kind 매핑을 그대로 쓴다
  (treatment → APPOINTMENT "진료 예약", psych_test → EXAM "심리검사 예약")
- 연결-06은 여기에 더해 "요청 상태 '예약됨'"과 "환자 예약 확정 알림 1건"이 같이 생겨야 한다.
  이번에는 만들지 않고 create_appointment 위에 TODO 주석으로 남긴다
- 일정 변경·취소는 reschedule_appointment / cancel_appointment만 쓴다
- 이 규칙을 어기는 코드가 있으면 점검 결과로 알려 줄 것

## 권한 규칙 (기존 그대로)
- get_current_doctor + _ensure_in_charge (담당 아니면 403)
- 예약을 바꾸는 API는 _get_my_appointment (없으면 404, 내 예약 아니면 403)

## 백엔드 코드 규칙 (.claude/CLAUDE.md)
- api/doctor_api.py → service/doctor_service.py → repository/doctor_repository.py, DTO는 schema/doctor_schema.py
  기존 F-07 코드 안·아래에 이어서 쓴다. 새 파일을 만들지 않는다
- DTO는 BaseDTO 상속 (camelCase 응답), 시각 필드는 KstDateTime, 응답은 ApiResponseDTO
- 예외는 서비스에서 HTTPException, commit은 레포지토리에서
- 관계는 selectinload로 미리 불러온다. 수정 직후 다시 조회는 populate_existing=True
- 모델·enum은 새로 만들지 않는다 (app/models/*, app/enums/*의 실제 이름·값 사용)
- 임의 결정은 주석에 (임의 결정 D-38) 형태로 남긴다
- 기존 파일은 CRLF 유지, 파일 전체를 다시 쓰지 말고 필요한 부분만 고친다

## 백엔드 테스트
- tests/doctor_api_test.py의 `# ===== F-07 예약 =====` 아래에 추가 (기존 check는 그대로 통과)
  - 조회: nextAppointment.dDay가 맞음, history가 다른 달 예약까지 내림차순, items[*].doctorName·roomName 있음
  - 추가: insuranceType 저장, treatment + tests → 422, psych_test + consult 진료실 → 400
  - 변경: requestedBy "patient" → changes[-1].requestedBy == "patient", history의 changeRequestedBy도 patient
- 필요하면 tests/seed_doctor_test_data.py에 auto_after_visit 예약 1건과 그 예약의 알림 1건 추가
- 확인: cd src && uvicorn main:app --reload 후 /docs의 doctor 탭, python tests/doctor_api_test.py

====================================================================
# PART 2. 프론트 (frontapp)
====================================================================

## 프론트 규칙
- Next.js 16 (App Router). 코드를 쓰기 전에 AGENTS.md대로 node_modules/next/dist/docs의 관련 문서를 먼저 확인
- Tailwind v4: 색상 토큰은 styles/tailwind/tailwind.theme.css의 @theme에 추가 (--color-brand: #4F6BED)
- 버튼은 components/ui/button.tsx (shadcn, base-ui) 재사용, variant="outline" / "default"
- React Query v5 (providers/ReactQueryProvider.tsx 이미 있음)
- 날짜 라이브러리·새 패키지 설치 금지, Date 객체로 직접 계산
- 컴포넌트는 "use client", props는 interface

## 파일 구조
- types/reservation/reservation.type.ts
- api/reservation/reservation.api.ts
- enums/reservation.enum.ts (상태·예약 경로·검사 이름 라벨)
- lib/date.ts (KST 날짜 차이, "11.25 (수)" 같은 포맷)
- components/reservation/
  - ReservationModal.tsx (조립 + 데이터 조회)
  - ReservationCalendar.tsx
  - ReservationDayDetail.tsx
  - ReservationHistory.tsx
  - StatusBadge.tsx
- app/reservation/page.tsx (모달을 띄우는 테스트 페이지, patientId는 일단 상수)

## API (api/member/member.api.ts 방식 그대로)
- fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/...`), credentials: "include" (JWT 쿠키),
  JSON body면 Content-Type 헤더, response.ok가 아니면 throw new Error("메시지"),
  반환은 Promise<ApiResponseDTO<T>> (@/types/common/common.type)
- getPatientAppointmentsApi(patientId, month)  GET  /doctor/patients/{patientId}/appointments?month=YYYY-MM
- createAppointmentApi(dto)                    POST /doctor/appointments
- rescheduleAppointmentApi(appointmentId, dto) PUT  /doctor/appointments/{appointmentId}
- cancelAppointmentApi(appointmentId, dto)     POST /doctor/appointments/{appointmentId}/cancel
- 시각은 +09:00을 붙여 보낸다 (예: 2026-12-09T10:30:00+09:00)
- 조회: useQuery({ queryKey: ["patientAppointments", patientId, month], queryFn })
- 추가·변경·취소: useMutation → onSuccess에서 invalidateQueries({ queryKey: ["patientAppointments", patientId] })

## 타입 (응답은 camelCase, 이름은 XxxResponseDTO / XxxRequestDTO)
- AppointmentStatus = "booked" | "waiting" | "in_progress" | "completed" | "cancelled" | "no_show"
- AppointmentKind = "treatment" | "psych_test"
- AppointmentVisitType = "first" | "return"
- ContactMethod = "phone" | "chat"
- BookingSource = "patient_app" | "auto_after_visit" | "doctor"
- RequestedBy = "patient" | "doctor"
- AppointmentChangeResponseDTO { id, changeType: "reschedule" | "cancel", fromAt, toAt, reason, requestedBy, changedBy, createdAt }
- AppointmentReminderResponseDTO { title, sentAt, createdAt }
- AppointmentDetailResponseDTO { appointmentId, scheduledAt, endAt, patient: { id, name }, visitType, kind,
    contactMethod, roomId, roomName, doctorName, insuranceType, status, tests, patientNote, completedAt,
    bookingSource, autoBookedAfter, reminders: AppointmentReminderResponseDTO[], changes: AppointmentChangeResponseDTO[] }
- NextAppointmentResponseDTO { appointmentId, scheduledAt, dDay }
- AppointmentHistoryResponseDTO { appointmentId, scheduledAt, kind, visitType, status, changedFrom, changeRequestedBy }
- PatientAppointmentsResponseDTO { patient, month, rescheduleCount, cancelCount, noShowCount,
    nextAppointment: NextAppointmentResponseDTO | null, items: AppointmentDetailResponseDTO[],
    history: AppointmentHistoryResponseDTO[] }
- AppointmentCreateRequestDTO { patientId, scheduledAt, endAt?, kind?, contactMethod?, roomId?, tests?, insuranceType? }
- AppointmentRescheduleRequestDTO { scheduledAt, endAt?, reason?, requestedBy? }
- AppointmentCancelRequestDTO { reason?, requestedBy? }

## 화면 (모달, 너비 약 660px, 흰 배경, rounded-xl, shadow)

### 헤더
- 제목 "예약 일정" (text-lg, bold), 우측 상단 X 닫기
- 부제 "{patient.name} · 다음 예약 D-{nextAppointment.dDay}" (text-sm, gray-500)
  nextAppointment가 null이면 "다음 예약 없음", dDay가 0이면 "오늘"

### 본문 상단: 좌우 2단 (grid-cols-2, 가운데 세로 구분선)

[좌] ReservationCalendar
- ◀ "2026년 11월" ▶ → 달을 바꾸면 month를 바꿔 다시 조회
- 요일 일~토, 일요일 요일·날짜는 빨간색, 7열 그리드
- 오늘: 연한 파란 원 + 파란 글씨 / 선택 날짜: brand 색 원 + 흰 글씨 bold
- 날짜 아래 점 (items 기준): booked·waiting·in_progress는 파란 점, completed는 회색 점, cancelled·no_show는 없음
- 하단 범례 "● 예약  ● 내원 완료" (text-xs)
- 날짜 클릭 → onSelectDate(date)

[우] ReservationDayDetail
- 제목 "11월 25일 (수)" + D-day 배지 (brand 배경, 흰 글씨, 오늘 기준)
- 그날 예약 카드 (cancelled 제외, 시각순)
  - 왼쪽 세로 바: treatment는 파랑, psych_test는 초록
  - 시간 "10:30 – 10:50" (바와 같은 색)
  - 제목: treatment → "{초진|재진} · {doctorName}", psych_test → "심리검사" (bold)
  - 보조 줄: treatment → "roomName · insuranceType", psych_test → "roomName · PHQ-9 · GAD-7 · BDI-II"
    (tests 값을 표시 이름으로 매핑), contactMethod=chat이면 "· 채팅" 추가, null인 항목은 생략
  - 우측 상단 StatusBadge
- 하단 정보 박스 (bg-gray-50, rounded, text-sm, 라벨 gray-500 + 값 2열), 그날 첫 예약 기준
  - 예약 경로: patient_app "환자 앱 예약" / auto_after_visit "진료 후 자동 예약" / doctor "의사 직접 등록"
    autoBookedAfter가 있으면 뒤에 "({MM.DD} 진료)"
  - 알림: reminders를 "{title} {sentAt MM.DD HH:mm}" 형태로 " · "로 연결, 없으면 줄 숨김
  - 요청 사항: patientNote, 없으면 줄 숨김
- 일정이 없으면 "예약된 일정이 없습니다"

### 본문 하단: ReservationHistory (history 사용, 여러 달)
- 헤더: "예약 이력" (bold) / 오른쪽 "변경 {rescheduleCount}회 · 노쇼 {noShowCount}회" (text-xs, gray)
- 같은 날짜의 treatment와 psych_test는 한 줄로 묶는다 ("재진 · 심리검사")
- 행: [MM.DD (요일) HH:mm] [내용] [StatusBadge], 최신순, border-b
  - 내용: 초진/재진(· 심리검사), changedFrom이 있으면 "· {MM.DD}에서 변경 ({환자|의사} 요청)"
- 선택 날짜 행은 bg-blue-50 강조, 행 클릭 시 그 날짜로 이동 (다른 달이면 month도 바꿈)

### StatusBadge
- booked "예약": 회색 배경, 진한 회색 글씨 (선택 날짜 행에서는 파란 글씨)
- waiting "대기", in_progress "진료 중": 연파랑 배경, 파란 글씨
- completed "내원 완료": 연초록 배경, 초록 글씨
- cancelled "취소", no_show "노쇼": 연빨강 배경, 빨간 글씨

### 푸터 (bg-gray-50, 우측 정렬)
- "예약 취소" (outline, 빨간 글씨): 선택 날짜 예약이 booked·waiting일 때만 활성 → cancel mutation (사유, 요청자)
- "일정 변경" (outline): 같은 조건 → reschedule mutation (새 일시, 사유, 요청자 환자/의사)
- "예약 추가" (brand 배경, 흰 글씨): create mutation (일시, 종류, 진료실, 검사, 보험)
- 입력은 간단한 인라인 폼, 에러(400·403·409·422) 메시지는 버튼 위에 표시

## 상태 관리
- ReservationModal 안에서 useState로 currentMonth, selectedDate
- 처음 열면 selectedDate = nextAppointment 날짜 (없으면 오늘)

====================================================================
# 공통
====================================================================

## 정해지지 않은 것 (코드에 TODO로 남기기)
- 화면의 "예정"과 "확정" 배지 차이: status에 구분 값이 없어서 둘 다 booked
- 알림 채널(알림톡·푸시)과 예정 발송 시각: notifications에 컬럼이 없어서 title·sentAt·createdAt만
- 예약 추가·변경·취소 때 환자 알림 생성: 명세 F-07에 없어서 이번에는 만들지 않음
- 연결-06 경로의 요청 상태 변경과 확정 알림 (create_appointment 확장)
- 다른 의사의 예약까지 이력에 보일지 (결정-50): 지금처럼 내 예약만

## Git
- git commit은 하지 마. 브랜치는 feat/doctor-reservation으로 만들 거야