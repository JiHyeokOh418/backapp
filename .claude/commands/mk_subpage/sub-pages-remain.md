# 작업: 의사웹 서브페이지 4개 API 보완
# (AI 상담 상세 F-06 · 감정 그래프 F-04 · 위험 감지 상세 F-05 · 설문조사 결과 F-03)

## 배경
- 프로젝트: 마음브릿지 (정신과 환자 비대면 추적 관리). 백엔드는 이 저장소(backapp, FastAPI)
- 참고 자료: `C:\Users\ohjih\OneDrive\Desktop\KDT-중간 자료\`
  - `figma_images/Doctor_detailCounsil.png` (AI 상담 상세)
  - `figma_images/Doctor_detailmind.png` (감정 그래프)
  - `figma_images/Doctor_detailRisk.png` (위험 감지 상세)
  - `figma_images/Doctor_detailsurvey.png` (설문조사 결과)
  - `3조_마음브릿지_요구사항_명세_2026-11-24.pdf` (9장 의사-02~07)
- 4개 팝업 API는 **이미 있다** (`doctor_api.py`)
  - 10번 상담 세션 목록, 11번 상담 세션 상세 (F-06)
  - 6번 위험 알림 확인, 12번 환자별 감지 목록, 13번 감지 상세, 14번 조치 기록 추가 (F-05)
  - 15번 감정 리포트 (F-04)
  - 16번 사전 문진 결과 (F-03)
- 이번 작업은 새로 만들지 않고, **팝업 화면에 필요한데 지금 응답에 없는 것만 채운다.**
  기존 응답 필드·테스트는 바꾸지 않는다 (필드는 추가만).
  단 PART 2의 ②⑤는 계산 방식을 바꾸므로 그 부분의 기존 테스트 기대값도 같이 고친다.

## 작업 순서
PART 1 → PART 2 → PART 3 → PART 4. 공통 함수(세션 번호, 입력 방식)는 PART 1에서 만들고 뒤에서 재사용한다.

====================================================================
# PART 1. AI 상담 상세 (F-06, `GET /doctor/chat-sessions/{sessionId}`)
====================================================================

## 지금 구현 vs 팝업 화면
| 화면 | 지금 | 할 일 |
|---|---|---|
| 제목 `AI 상담 · 11월 9일 (월) 23:42` | `startedAt` 있음 | 그대로 |
| 제목 옆 태그 `#수면` | `summary.topics` 있음 | 그대로 (프론트가 첫 태그 표시) |
| 부제 `세션 #A-1109` | 없음 | ① `sessionCode` |
| 부제 `18분`, 정보 칸 `소요 시간 18분` | `startedAt`·`endedAt`만 | ① `durationMinutes` |
| 상단 `‹ 이전 세션 11.05` / `다음 세션 ›` | 없음 | ② `prevSession`, `nextSession` |
| 정보 칸 `유형 AI 상담 (텍스트)` | `sessionType`만 | ③ `inputType` |
| 정보 칸 `감정 변화 불안 → 기쁨` | 메시지별 `emotion`만 | ④ `emotionChange` |
| 정보 칸 `위험 신호 · 감지 없음` | 메시지별 `riskLevel`만 | ④ `riskCount`, `maxRiskLevel` |
| `AI 요약` 본문 + 태그 | `summary.contextSummary`, `topics` 있음 | 그대로 |
| `대화 전문` `14턴 중 8턴`, `전체 펼치기` | `messages` 전체 있음 | ⑤ `turnCount` (몇 턴 보여 줄지는 프론트) |

## 고칠 것 (`ChatSessionDetailResponseDTO`에 추가)

### ① 세션 번호·소요 시간 (공통 함수)
- `session_code: str` — `"A-" + 시작 시각(KST)의 MMDD` (예: 11월 9일 → `A-1109`) (임의 결정 D-41)
  - `started_at`이 없으면 `scheduled_at` 기준
  - PART 3에서도 쓰므로 `doctor_service.py` 위쪽 상수·함수 영역에 `session_code(session) -> str` 함수로 만든다
- `duration_minutes: int | None` — `(ended_at - started_at)`의 분(버림). 둘 중 하나라도 없으면 None
  - PART 4에서도 쓰므로 `duration_minutes(started_at, ended_at)` 함수로 만든다

### ② 이전·다음 세션
- `prev_session: ChatSessionBriefDTO | None = None`, `next_session: ChatSessionBriefDTO | None = None`
  - `ChatSessionBriefDTO`: `id`, `started_at`(KstDateTime)
- 기준: 같은 환자·같은 `session_type`, `started_at`이 있는 세션 중 바로 앞·뒤 (임의 결정 D-42)
  - `prev_session_id` 컬럼은 연결 방식이 정해지지 않아 쓰지 않는다
- 레포지토리에 `find_adjacent_sessions(user_id, session_type, started_at) -> (prev, next)` 추가

### ③ 입력 방식 (공통 함수)
- `input_type: Literal["text", "voice", "mixed"] | None` — 환자(user) 메시지의 `input_type`
  - 모두 text → text, 모두 voice → voice, 섞이면 mixed, 환자 메시지가 없으면 None (임의 결정 D-43)
  - PART 4에서도 쓰므로 `input_type_of(messages)` 함수로 만든다
- 화면 문구 `AI 상담 (텍스트)`는 프론트가 `sessionType` + `inputType`으로 만든다

### ④ 감정 변화·위험 신호
- `emotion_change: EmotionChangeDTO | None = None`
  - `EmotionChangeDTO`: `start: EmotionType`, `end: EmotionType`
  - 감정 분석이 있는 환자 메시지 중 첫 메시지의 `dominant` → 마지막 메시지의 `dominant`
  - 분석된 환자 메시지가 1개 이하면 None
- `risk_count: int` — 이 세션 메시지에서 감지된 위험 알림 수 (`find_message_risk_levels` 결과 재사용)
- `max_risk_level: RiskEventLevel | None` — 그중 가장 높은 등급 (`RISK_RANK` 재사용), 없으면 None

### ⑤ 턴 수
- `turn_count: int` — 환자(user) 메시지 수 (환자 발화 1 + AI 응답 1 = 1턴) (임의 결정 D-44)

====================================================================
# PART 2. 감정 그래프 (F-04, `GET /doctor/patients/{patientId}/emotion-report`)
====================================================================

## 지금 구현 vs 팝업 화면
| 화면 | 지금 | 할 일 |
|---|---|---|
| 부제 `김민준 · 2026.10.15 – 11.11` | `patientId`만 | ① `patient` |
| 탭 `주간 / 월간 / 3개월`, `◀ 10.15 – 11.11 ▶` | `period`, `from` 있음 | 그대로 |
| 월간이 `10.15 – 11.11`(28일), `지난 4주 대비` | month = 달력 1개월 | ② month = 28일 |
| `평균 기분 2.8 / 5`, `▲ 0.9` | `avgMoodScore`, `moodChange` 있음 | 그대로 |
| `기록한 날 14일 / 기간 28일 중` | `recordedDays`, `totalDays` 있음 | 그대로 |
| `저녁 기록 64% (18시~24시)` | `timeSlots` 있음 | 그대로 (프론트가 evening ÷ 합계) |
| `기쁨 감정 16%`, `▲ 7%p` | `topEmotion`만 | ③ `joyRatio`, `joyChange` |
| `일별 기분 추이` | `dailyMoods` 있음 | 그대로 |
| 그래프의 점선 `진료일 · PHQ-9` | 없음 | ④ `visitMarkers` |
| `주별 감정 비율` `10.15주 / 10.22주 ...` | 월요일 시작 주 | ⑤ 기간 첫날부터 7일씩 |
| `자주 고른 기분 태그` `#불안 4 #피곤 3` | `keywords` 있음 | 그대로 (상위 강조는 프론트) |
| `시간대별 기록` | `timeSlots` 있음 | 그대로 |

## 고칠 것 (`EmotionReportResponseDTO`)

### ① 환자 이름
- `patient: DoctorPatientBriefDTO` 추가 (`patient_id`는 그대로 둔다)
- 이름은 기존 `repo.find_user_names({patient_id})` 재사용

### ② 월간 = 28일 (임의 결정 D-45, D-17 수정)
- `report_range`에서 `month`는 28일(4주), `3months`는 84일(12주). `week`는 7일 그대로
- `PERIOD_MONTHS` 대신 `PERIOD_DAYS = {"week": 7, "month": 28, "3months": 84}` 상수로 바꾸고 D-17 주석도 고친다
- 직전 기간 비교(`moodChange`)는 지금처럼 같은 길이의 바로 앞 기간

### ③ 기쁨 감정 비율
- `EmotionSummaryDTO`에 추가
  - `joy_ratio: float | None` — 기간 안 AI 상담 메시지 감정 분석 중 `dominant = joy` 비율 (0~1, 소수 3자리). 분석이 없으면 None
  - `joy_change: float | None` — 직전 같은 길이 기간의 `joy_ratio`와의 차이 (0.07이면 화면 `▲ 7%p`). 하나라도 없으면 None
- 직전 기간 감정은 기존 `repo.find_message_emotions(patient_id, start_at, end_at)`를 기간만 바꿔 한 번 더 부른다

### ④ 진료일·PHQ-9 표시
- `visit_markers: list[VisitMarkerDTO] = []` 추가
  - `VisitMarkerDTO`: `date`, `appointment_id`, `phq9_score: int | None`, `phq9_severity: str | None`
- 대상: 기간 안에 내가(doctor_id = 나) 이 환자를 진료한 `completed` 예약 (`scheduled_at`의 KST 날짜), 날짜순
- PHQ-9: 같은 날(KST) `assessment_results`의 `phq9` 중 가장 늦은 결과. 없으면 None
- 레포지토리에 추가
  - `find_completed_appointments(doctor_id, patient_id, start, end)`
  - `find_assessments(patient_id, instrument, start, end)` (날짜별로 고르는 건 서비스에서 파이썬으로)

### ⑤ 주별 감정 비율을 기간 첫날부터 7일씩 (임의 결정 D-46)
- 지금은 월요일 시작 주라서 화면의 `10.15주 / 10.22주`와 맞지 않는다
- `week_start = first_day + 7 * ((그날 - first_day).days // 7)` 로 묶는다
- 데이터가 없는 주도 `total = 0`, 비율 0으로 넣어 화면 막대 수를 일정하게 한다

### 참고 (기존 그대로)
- 기분 점수·태그·시간대는 환자가 공유한(`is_shared`) 감정 기록만 쓴다

====================================================================
# PART 3. 위험 감지 상세 (F-05, `GET /doctor/risk-events/{eventId}`)
====================================================================

## 지금 구현 vs 팝업 화면
| 화면 | 지금 | 할 일 |
|---|---|---|
| 제목 옆 배지 `● 주의` `미확인` | `level`, `status` 있음 | 그대로 |
| 부제 `최근 30일 감지 2건`, 탭 `10.22 23:51 / 10.17 01:08` | 12번 목록 API | 그대로 |
| 출처 `AI 상담 · 세션 #A-1022` | `origin`, `sessionId`만 | ① `sessionCode` |
| 감지 분류 `무망감 · 소진 표현` | `category` 있음 | 그대로 |
| 모델 신뢰도 `0.82` | `score` 있음 | 그대로 |
| 담당의 `이은솔` | 없음 | ② `doctorName` |
| `대화 맥락` `감지 문장 전후 6턴`, 빨간 강조 | `context`, `isTrigger` 있음 | 그대로 |
| 감지 근거 `감지 표현`, `문맥 판단` | `matchedTerms`, `contextJudgement` 있음 | 그대로 |
| 감지 근거 `이전 기록 최근 30일 유사 표현 1회 (10.17 "…")` | 없음 | ③ `similarHistory` |
| `조치 이력` (AI·시스템·의사) | `actions` 있음 | 그대로 |
| 하단 `중간 위험 · 확인 기한 10.23 23:51 (감지 + 24시간)` | `level`, `dueAt` 있음 | 그대로 |
| 버튼 `위기 대응 요청` / `보류` / `확인 완료` | 14번 escalate·hold, 6번 review | 그대로 (확인도 조치 이력에 review로 남음) |

## 고칠 것 (`RiskEventDetailResponseDTO`에 추가)
- 14번 조치 추가 API도 같은 DTO를 돌려주므로 자동으로 들어간다

### ① 세션 번호
- `session_code: str | None = None` — 대화에서 감지됐으면 그 세션의 번호, 아니면 None
- PART 1의 `session_code(session)` 함수를 쓴다
- 세션 시작 시각이 필요하므로 레포지토리에 `find_chat_session(session_id)` 추가 (또는 기존 조회에 세션을 함께 불러온다)

### ② 담당의
- `doctor_name: str | None = None` — 이 환자의 지금 담당 의사 (`care_relations`, `ended_at IS NULL`)
  - 담당 의사가 여러 명이면 `started_at`이 가장 이른 1명 (임의 결정 D-47)
- 레포지토리에 `find_current_doctor_name(patient_id)` 추가

### ③ 이전 유사 기록
- `similar_history: RiskSimilarHistoryDTO` 추가
  - `RiskSimilarHistoryDTO`: `count: int`, `latest_id: int | None`, `latest_at: KstDateTime | None`, `latest_evidence: str | None`
- 대상: 같은 환자의 다른 위험 알림 중 `이 알림.created_at - 30일 <= created_at < 이 알림.created_at`,
  `category`가 같은 것 (category가 없으면 `origin`이 같은 것) (임의 결정 D-48)
- `latest_*`는 그중 가장 최근 1건. 화면 문구는 프론트가 만든다
- 레포지토리에 `find_similar_risk_events(user_id, category, origin, since, before, exclude_id)` 추가 (최신순)

### 참고 (기존 그대로)
- 없으면 404, 담당 아니면 403은 `_get_my_risk_event` 그대로. 조치 가능 여부(409)는 `add_risk_action` 규칙 그대로

====================================================================
# PART 4. 설문조사 결과 (F-03, `GET /doctor/patients/{patientId}/intake`)
====================================================================

## 지금 구현 vs 팝업 화면
| 화면 | 지금 | 할 일 |
|---|---|---|
| 부제 `김민준 · 남 23세 · 113912` | 이름만 | ① `patientInfo` (성별·나이·차트번호) |
| 부제 `초진 전 사전 문진` | 문진 세션이라 고정 | 그대로 (프론트 고정 문구) |
| `문진 일시 2026-10-14 09:12` | `startedAt` 있음 | 그대로 |
| `방식 AI 사전 문진 (대화형)` | 없음 | ② `inputType` |
| `소요 시간 14분` | `startedAt`·`endedAt`만 | ② `durationMinutes` |
| `응답 완료 100%` | `answers`의 `status`만 | ② `completionRate` |
| 척도 카드 `PHQ-9 19 / 27점 중등도-중증` | `totalScore`, `severity` 있음 | ③ `maxScore` |
| `PHQ-9 문항별 응답` 점수 막대 | `answers[].value` (JSON 그대로) | ④ `score` |
| `주 호소` 본문 | `chiefComplaint` 있음 | 그대로 |
| `주 호소` 아래 환자 인용 문장 | 저장 칸 없음 | TODO |
| `AI 참고 소견` 라벨 + 설명 | `findings` 있음 | 그대로 |

## 고칠 것 (`IntakeResultResponseDTO`)

### ① 환자 정보
- `patient_info: IntakePatientInfoDTO` 추가 (`patient`는 그대로 둔다)
  - `IntakePatientInfoDTO`: `gender: UserGender | None`, `birth_date: date | None`, `age: int | None`, `chart_no: str | None`
- `age`: `birth_date`와 `today_kst()`로 계산한 만 나이 (생일이 안 지났으면 -1), `birth_date`가 없으면 None
- `chart_no`: `patient_charts`에서 이 환자 + 내 병원(`doctor_profiles.hospital_id`)의 차트번호. 없으면 None
- 레포지토리에 `find_patient_info(patient_id)`(users), `find_chart_no(patient_id, hospital_id)` 추가
  (내 병원 id는 기존에 쓰는 방법 재사용)

### ② 문진 방식·소요 시간·응답률
- `input_type` — PART 1의 `input_type_of(messages)` 재사용 (임의 결정 D-43)
  - 화면 문구 `AI 사전 문진 (대화형)`은 프론트가 만든다
- `duration_minutes: int | None` — PART 1의 `duration_minutes(started_at, ended_at)` 재사용
- `completion_rate: int` — 필수(`required`) 문항 중 `done` 비율, 0~100 정수(반올림). 필수 문항이 없으면 100 (임의 결정 D-49)
- 환자 메시지가 필요하므로 `find_intake_session`의 `selectinload`에 `ChatSession.messages`를 더한다

### ③ 척도 만점
- `IntakeScoreDTO`에 `max_score: int` 추가
- `doctor_service.py` 위쪽 상수 `INSTRUMENT_MAX_SCORE = {phq9: 27, gad7: 21, isi: 28, bdi2: 63}`
- 결과가 없는 척도 카드에도 `max_score`는 넣는다

### ④ 문항별 점수
- `IntakeAnswerDTO`에 `score: int | None = None` 추가
- 척도 문항(`instrument`가 있음)이고 `status = done`일 때만 채운다 (임의 결정 D-50)
  - `value`가 int면 그 값, dict이고 `score` 키가 있으면 그 값, 그 외는 None
- 일반 문진 문항은 None (화면 막대는 척도 문항만 그린다)

====================================================================
# 공통
====================================================================

## 권한 규칙 (기존 그대로)
- 모든 API는 `get_current_doctor` + `_ensure_in_charge` (담당 아니면 403)
- 대상이 없으면 404 (세션·알림·문진)

## 코드 양식
- 참고 코드: `C:\kdt_0900_ojh\fastapi\workspace\backend`
  (`apis/post_api.py` → `services/post_service.py` → `repositories/post_repository.py`, DTO는 `schemas/post_schema.py`)
  - 클래스 + 생성자 주입(`__init__`), `get_xxx_service` / `get_xxx_repository` 팩토리를 `Depends`로 연결
  - 라우터는 서비스만 부르고 `ApiResponseDTO(success, message, data)`로 감싸 돌려준다
  - 예외는 서비스에서 `HTTPException`, commit은 레포지토리에서
- 폴더: 이 저장소에 맞는 폴더(`api/`, `service/`, `repository/`, `schema/`)가 이미 있으므로 그대로 쓴다.
  참고 코드의 복수형 폴더(`apis/` 등)는 만들지 않는다. 맞는 폴더가 없을 때만 새로 만든다
- 파일: `api/doctor_api.py` → `service/doctor_service.py` → `repository/doctor_repository.py`, DTO는 `schema/doctor_schema.py`.
  각 팝업의 기존 F-0x 영역 안·아래에 이어서 쓴다. 새 파일을 만들지 않는다
- 공통 함수(`session_code`, `duration_minutes`, `input_type_of`)와 상수는 `doctor_service.py` 위쪽 상수·함수 영역에 둔다
- DTO는 `BaseDTO` 상속(camelCase), 시각 필드는 `KstDateTime`
- 관계는 `selectinload`로 미리 불러온다. 수정 직후 다시 조회는 `populate_existing=True`
- 모델·enum은 새로 만들지 않는다 (`app/models/*`, `app/enums/*`의 실제 이름·값 사용)
- 임의 결정은 주석에 `(임의 결정 D-41)` 형태로 남긴다 (이번 작업 D-41 ~ D-50)
- 기존 파일은 줄바꿈(CRLF)을 유지하고, 파일 전체를 다시 쓰지 말고 필요한 부분만 고친다

## 테스트
- `tests/doctor_api_test.py`의 각 팝업 영역에 추가 (기존 check는 그대로 통과, PART 2의 ②⑤로 바뀌는 기대값은 이유를 주석으로 남기고 고친다)
- PART 1 상담 상세
  - `sessionCode`가 `A-MMDD` 형식, `durationMinutes`가 맞음
  - 세션 3개를 시각순으로 만들면 가운데 세션의 `prevSession`·`nextSession`이 앞뒤 세션, 첫 세션의 `prevSession`은 null
  - 위험 감지가 있는 세션은 `riskCount >= 1`, 없는 세션은 0이고 `maxRiskLevel`은 null
  - `turnCount` = 환자 메시지 수
- PART 2 감정 그래프
  - `period=month&from=2026-10-15` → `startDate` 10.15, `endDate` 11.11, `totalDays` 28
  - `weeklyEmotions`의 `weekStart`가 10.15, 10.22, 10.29, 11.05
  - `joyRatio`가 직접 센 값과 같고, `joyChange`가 직전 28일과의 차이
  - 기간 안 completed 예약 날짜가 `visitMarkers`에 나오고, 그날 PHQ-9가 있으면 점수가 들어 있음
  - `patient.name` 있음
- PART 3 위험 감지 상세
  - 대화에서 나온 알림은 `sessionCode`가 `A-MMDD`, 대화가 아닌 알림은 null
  - `doctorName`이 담당 의사 이름
  - 같은 category 알림 2건(5일 차이)이면 늦은 알림의 `similarHistory.count == 1`, `latestId`가 앞 알림, 앞 알림은 `count == 0`
  - 31일 전 알림은 `similarHistory`에 들어가지 않음
  - 조치 추가(hold) 응답에도 위 필드가 들어 있음
- PART 4 설문조사 결과
  - `patientInfo.age`가 생일 전·후로 맞게 계산됨, `chartNo`가 내 병원 차트번호
  - `durationMinutes`, `completionRate` (필수 문항 하나를 skipped로 만들면 100 미만)
  - 척도 카드 3장 모두 `maxScore` (phq9 27, gad7 21, isi 28)
  - PHQ-9 문항의 `score`가 `value`와 같고, 일반 문항은 null
- 필요하면 `tests/seed_doctor_test_data.py`에 상담 세션, completed 예약과 같은 날 PHQ-9 결과,
  같은 category 위험 알림, 환자 차트번호·생년월일을 더한다

## 작업 방식
- PART 1 → 4 순서로, PART 안에서는 ①부터 하나씩 하고 멈춰서 고친 파일과 핵심 코드를 설명해 줘.
  내가 직접 따라 쳐 보면서 공부할 거야
- git commit은 하지 마. 브랜치는 `feat/doctor-subpages`로 만들 거야
- 확인: `cd src && uvicorn main:app --reload` 후 `/docs`의 doctor 탭, 그리고 `python tests/doctor_api_test.py`

## 정해지지 않은 것 (코드에 TODO로 남기기)
- 세션 번호: ERD에 번호 컬럼이 없음. 같은 날 세션이 2개면 번호가 겹친다 → 지금은 `A-MMDD`
- 상담 감정 변화를 메시지 감정 분석으로 볼지 `session_summaries.mood_summary`로 볼지 → 지금은 메시지 기준
- 감정 그래프 `기쁨 감정` 칸을 기쁨으로 고정할지, 가장 많은 감정(`topEmotion`)으로 바꿀지 → 화면대로 기쁨 고정
- 하루에 감정 기록이 여러 건일 때 일별 그래프 값 → 지금처럼 기록을 그대로 내려 줌
- 진료일 표시에 다른 의사의 진료도 넣을지 → 지금은 내 진료만
- 위험 "유사 표현"을 category로 볼지, 걸린 단어(`matched_terms`)가 겹치는 것으로 볼지 → 지금은 category
- 담당 의사가 여러 명일 때 화면에 몇 명 보여 줄지 → 지금은 1명
- 설문 결과 주 호소 아래 환자 인용 문장: `session_summaries`에 칸이 없음 → 이번에는 내려 주지 않음
- `AI 참고 소견` 라벨 색(파랑·회색·초록) 기준: `findings`에 구분 값이 없음 → 프론트에서 정함
- `session_checklists.value`의 정확한 JSON 모양: 문진 저장 쪽이 정해지면 PART 4 ④ 규칙을 맞춘다