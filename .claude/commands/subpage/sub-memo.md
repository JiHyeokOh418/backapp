# 작업: 의사 메인 페이지 API (환자를 고르면 위젯이 바뀌는 구조)

## 배경
- 프로젝트: 마음브릿지 (정신과 환자 비대면 추적 관리). 백엔드는 이 저장소(backapp, FastAPI)
- 참고 자료: `C:\Users\ohjih\OneDrive\Desktop\KDT-중간 자료\`
  - `마음브릿지_의사웹_API명세_2026-11-22.md` (2장 F-02, F-08)
  - `3조_마음브릿지_요구사항_명세.pdf` (9장 의사-01~08, 10장 보안-02)
- 의사 메인 화면(Doctormanagechart)은 왼쪽 환자 목록에서 환자를 고르면
  경과 그래프·AI 상담 기록·메모 위젯이 그 환자의 데이터로 바뀐다.
  프론트는 선택한 `patientId`만 바꿔 같은 API를 다시 부르면 되도록 만든다.

## 만들 API (prefix `/doctor`, 모두 의사만 호출 가능)
### 1단계: 화면 전체 (환자 선택과 무관)
| 요청 | 메서드·주소 | 받는 것 |
|---|---|---|
| 오늘 요약 | GET /doctor/dashboard/summary?date= | todayCount, completedCount, waitingCount, openRiskCount |
| 진료실 목록 | GET /doctor/rooms | 내 병원(doctor_profiles.hospital_id)의 활성 진료실 |
| 오늘 예약 일정 | GET /doctor/appointments?date= | scheduledAt, 환자, visitType, roomId, status (취소 제외) |
| 위험 환자 알림 | GET /doctor/risk-events?status=open | level, 환자, 사유(evidence), origin, createdAt |
| 위험 알림 확인 | POST /doctor/risk-events/{eventId}/review | status=reviewed로 바뀐 알림 |
| 월 캘린더 | GET /doctor/calendar?month=2026-11 | 날짜별 상담(treatment)·검사(psych_test) 개수 |

#### 환자 목록·검색 (요구사항 의사-01)
GET /doctor/patients?tab=all·waiting·booked&date=&q=

- 대상: 현재 담당 중인 환자만 (care_relations.doctor_id = 나, ended_at IS NULL).
  담당이 끝난 환자는 어떤 탭에서도 나오지 않는다
  - all: 담당 환자 전체
  - waiting / booked: 담당 환자 중 그날 예약 상태가 waiting / booked인 환자
- 정렬: 위험도 높은 순
  - 위험도 = 그 환자의 확인 안 한(status=open) risk_events 중 가장 높은 level
  - 순서: high → medium → low → 알림 없음
  - 위험도가 같으면 가장 최근 알림(createdAt)이 먼저, 그다음 예약 시각 순
- 받는 것: 환자(id, name, gender, birthDate), riskLevel(없으면 null), 그날 예약(appointmentId, scheduledAt, status)
- 확인 기준: 담당이 끝난 환자는 나오지 않는다. high 알림이 있는 환자가 맨 위에 온다

### 2단계: 환자를 고르면 바뀌는 위젯 (담당 환자만)
| 요청 | 메서드·주소 | 받는 것 |
|---|---|---|
| 경과 그래프 | GET /doctor/patients/{patientId}/assessments?instrument=phq9&months=3 | 측정일별 점수, severity |
| AI 상담 기록 위젯 | GET /doctor/patients/{patientId}/records?tab=chat·diary | 세션(또는 일기) 목록, hasRisk |

### 3단계: 메모 팝업 (Doctor_DetailMemo)
| 요청 | 메서드·주소 | 권한 |
|---|---|---|
| 메모 목록 | GET /doctor/patients/{patientId}/memos?pinned=&sort=latest·oldest | 담당 |
| 메모 작성 | POST /doctor/patients/{patientId}/memos (category: clinic·counsel, content, isPinned) | 담당 |
| 메모 수정·고정 | PUT /doctor/memos/{memoId} (보낸 값만 수정) | 작성자 |
| 메모 삭제 | DELETE /doctor/memos/{memoId} (soft delete) | 작성자 |

메모 화면 요구사항:
- 헤더 "김민준 환자 · 3건 · 고정 1", 탭 "전체 3 / 고정 1": 목록 응답에 totalCount, pinnedCount를 함께 보낸다
- 고정 메모가 항상 위, 그 다음 정렬 기준
- 작성자 이름(doctor.name), createdAt, updatedAt을 보낸다. 내용을 고쳤을 때만 "수정됨"이 뜨게
  (작성할 때 created_at = updated_at, 고정만 바꿀 때는 updated_at을 바꾸지 않는다)

## 권한 규칙
- `dependencie/auth_dependency.py`에 `get_current_doctor` 추가:
  `get_current_user` + `role == doctor` 확인, 아니면 403
- "담당" = care_relations에서 doctor_id가 나이고 ended_at이 NULL인 환자. 아니면 403 (보안-02, 공통-04)
  환자 목록·예약·위험 알림 같은 목록 API도 담당 환자만 돌려준다
- "작성자" = doctor_memos.doctor_id가 나. 아니면 403. 없거나 삭제된 메모는 404
- 위험 알림 확인 시: risk_events 상태 변경 + risk_event_actions에 review 이력 1건 추가 (보안-04: 이력은 수정·삭제 없음)
  이미 확인한 알림이면 409

## 반드시 지킬 코드 규칙 (.claude/CLAUDE.md)
- 파일: `api/doctor_api.py` → `service/doctor_service.py` → `repository/doctor_repository.py`,
  DTO는 `schema/doctor_schema.py`. 기존 `user_api.py` → `user_service.py` → `user_repository.py`와
  같은 모양(생성자 주입, `get_xxx_service`/`get_xxx_repository` 팩토리, 한국어 주석)으로 작성
- DTO는 `common_schema.BaseDTO` 상속 (camelCase), 응답은 `ApiResponseDTO`로 감싼다
- 예외는 서비스에서 `HTTPException`, commit은 레포지토리에서
- 비동기라 관계(환자 이름, 작성자 이름)는 `selectinload`로 미리 불러온다.
  수정 직후 다시 조회할 때는 `execution_options(populate_existing=True)`
- 날짜·시각은 KST(+09:00). `date` 파라미터가 없으면 오늘
- 모델·enum은 새로 만들지 말고 `app/model/*`, `app/enum/*`의 실제 이름·값을 먼저 읽고 맞춘다
- `main.py`에 `app.include_router(doctor_api.router, prefix="/doctor", tags=["doctor"])` 추가

## 작업 방식
- 단계(1→2→3)마다 멈추고, 만든 파일과 핵심 코드를 설명해 줘. 내가 직접 따라 쳐 보면서 공부할 거야
- 기존 파일을 고칠 때 줄바꿈(CRLF)을 그대로 유지해. 파일 전체를 다시 쓰지 말고 필요한 부분만 고쳐
- git commit은 하지 마. 브랜치는 `feat/doctor-main`으로 만들 거야
- 확인: `cd src && uvicorn main:app --reload` 후 `/docs`의 doctor 탭

## 정해지지 않은 것 (코드에 TODO로 남기기)
- 의사가 일기를 볼 수 있는지 (결정-39·40) → 일기 탭은 TODO 주석
- 의사 승인 API가 없음 (명세 4장) → 테스트할 때는 DB에서 users.role='doctor', care_relations 행을 직접 넣고 다시 로그인
- 위험도가 같을 때 정렬 기준은 미정 (결정-39) → 일단 "최근 알림 순 → 예약 시각 순"으로 하고 TODO