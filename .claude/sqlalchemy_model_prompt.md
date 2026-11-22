# 역할
너는 FastAPI + SQLAlchemy 2.0 + PostgreSQL 백엔드 개발을 도와주는 시니어 개발자야.
아래 [테이블 정의]와 [FK 정의]에 있는 모든 테이블을 [코드 양식]과 똑같은 스타일의 SQLAlchemy ORM 모델로 작성해 줘.

# 기술 스택
- Python 3.10+, FastAPI
- SQLAlchemy 2.0 (`Mapped`, `mapped_column` 방식)
- PostgreSQL. `Base`는 `app.infrastructure.postgresql`에 있고, 서버가 켜질 때 `Base.metadata`로 테이블을 동기화한다.
- Enum 클래스는 이미 `app/enums/`에 있다. 새로 만들지 말고 import만 한다. 어떤 Enum이 어느 파일에 있는지는 [Enum 위치]를 따른다.

# 코드 양식 (이 스타일을 그대로 따를 것)
```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Text, Integer, DateTime, Identity, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.member_enum import MemberProvider

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.post_model import Post

KST = timezone(timedelta(hours=9)) # UTC+9

class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    member_email: Mapped[str] = mapped_column(Text, nullable=False)
    member_password: Mapped[str | None] = mapped_column(Text)
    member_name: Mapped[str | None] = mapped_column(Text)
    member_age: Mapped[int | None] = mapped_column(Integer)
    member_phone: Mapped[str | None] = mapped_column(Text)
    member_profile: Mapped[str | None] = mapped_column(Text, default="/members/default.jpg")
    member_provider_id: Mapped[str | None] = mapped_column(Text, unique=True)
    member_provider: Mapped[MemberProvider] = mapped_column(
        SQLEnum(MemberProvider, native_enum=False),
        nullable=False,
        default=MemberProvider.LOCAL
    )
    member_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    __table_args__ = (
        UniqueConstraint("member_email", "member_provider", name="uq_member_email_provider"),
    )

    # 관계
    # cascade: Member가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    posts: Mapped[list["Post"]] = relationship(
        "Post", back_populates="member", cascade="all, delete-orphan"
    )
```

# 작성 규칙

## 1. 파일과 클래스
- 테이블 하나에 파일 하나를 만든다: `app/models/{단수형}_model.py`. 예: `users` → `user_model.py`의 `class User`, `chat_sessions` → `chat_session_model.py`의 `class ChatSession`.
- 클래스 이름은 테이블 이름의 단수형 PascalCase로 쓴다. 예: `diary_analyses` → `DiaryAnalysis`, `user_items_stackable` → `UserItemStackable`, `session_checklist` → `SessionChecklist`.
- `__tablename__`은 ERD 테이블 이름을 그대로 쓴다.
- 파일마다 맨 위에 양식처럼 `KST`를 정의한다.
- 마지막에 `app/models/__init__.py`를 만들어 모든 모델을 import한다. 그래야 서버가 켜질 때 `Base.metadata`에 전부 등록된다.

## 2. 타입 매핑 (PostgreSQL 기준)
| ERD 타입 | mapped_column 타입 | Mapped 타입 |
|---|---|---|
| BIGINT | `BigInteger` | `int` |
| INT | `Integer` | `int` |
| TINYINT | `SmallInteger` (PostgreSQL에는 TINYINT가 없음) | `int` |
| VARCHAR(n) | `String(n)` (길이 그대로) | `str` |
| CHAR(36) | `String(36)` | `str` |
| TEXT | `Text` | `str` |
| DECIMAL(p,s) | `Numeric(p, s)` | `Decimal` (`from decimal import Decimal`) |
| DATETIME | `DateTime(timezone=True)` | `datetime` |
| DATE | `Date` | `date` |
| BOOLEAN | `Boolean` | `bool` |
| JSON | `JSONB` (`from sqlalchemy.dialects.postgresql import JSONB`) | `dict \| list` |
| BLOB | `LargeBinary` (PostgreSQL에는 BLOB이 없음) | `bytes` |
| ENUM | `SQLEnum(...)` (아래 3번) | 해당 Enum 클래스 |

## 3. Enum 컬럼
- 양식처럼 `SQLEnum(EnumClass, native_enum=False)`를 쓴다.
- **반드시 `values_callable=lambda e: [m.value for m in e]`를 추가한다.** Enum 멤버 이름은 대문자(`KAKAO`)이고 값은 소문자(`"kakao"`)다. 이 옵션이 없으면 SQLAlchemy가 DB에 멤버 이름(`"KAKAO"`)을 저장해서 ERD 값과 달라진다.
- ERD에 초기값이 자연스러운 ENUM(status 등)은 `default=`를 지정한다. 예: `status` → `SessionStatus.SCHEDULED`.

```python
status: Mapped[SessionStatus] = mapped_column(
    SQLEnum(SessionStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
    nullable=False,
    default=SessionStatus.SCHEDULED
)
```

## 4. PK
- BIGINT PK: `mapped_column(BigInteger, Identity(), primary_key=True)`
- CHAR(36) PK(`emotion_analyses.id`, `notifications.notification_id`, `user_items_unique.holding_item_id`): `mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))`
- 복합 PK 테이블은 [FK 정의]의 "복합 PK" 목록을 따른다. 해당 컬럼마다 `primary_key=True`를 주고 `Identity()`는 쓰지 않는다.

## 5. nullable / default
- PK, FK(SET NULL 대상 제외), 핵심 값(이름, 내용, 상태, 점수 등)은 `nullable=False`로 둔다. Mapped 타입은 `Mapped[int]`처럼 `None` 없이 쓴다.
- 나머지는 `Mapped[타입 | None]`으로 두고 `nullable`은 생략한다.
- `created_at`: `default=lambda: datetime.now(KST)`
- `updated_at`: `default=lambda: datetime.now(KST), onupdate=lambda: datetime.now(KST)`
- `deleted_at`: nullable. soft delete용이므로 default를 두지 않는다.
- BOOLEAN은 의미에 맞게 default를 준다(`is_active=True`, `is_pinned=False`, `required=False`). 숫자 카운터도 마찬가지다(`point_balance=0`, `ask_count=0`, `attempt=1`, `quantity=1`).

## 6. FK와 관계
- FK는 `mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)`처럼 쓴다. `ondelete`는 [FK 정의]에 적힌 대로 CASCADE 또는 SET NULL로 지정한다.
- **FK 컬럼 타입은 참조하는 PK 타입과 반드시 같게 맞춘다.** ERD에서 ⚠ 표시한 컬럼은 CHAR(36)이지만 참조 PK가 BIGINT다. PostgreSQL은 타입이 다른 FK를 만들 수 없으므로 `BigInteger`로 작성하고, 줄 끝에 `# ERD: CHAR(36) -> 참조 PK에 맞춰 BIGINT로 변경` 주석을 단다.
- **CASCADE FK**에는 양방향 관계를 만든다.
  - 부모: `relationship("자식", back_populates="...", cascade="all, delete-orphan")` + `Mapped[list["자식"]]`
  - 자식: `relationship("부모", back_populates="...")` + `Mapped["부모"]`
  - 한 테이블이 같은 테이블을 FK로 2개 이상 참조하면(예: `care_relations`의 patient_id와 doctor_id → users) 양쪽 relationship 모두에 `foreign_keys=[...]`를 지정한다.
  - 1:1 관계(`doctor_profiles`, `session_summaries`, `diary_analyses`)는 부모 쪽을 `Mapped["자식 | None"]` + `uselist=False`로 둔다.
- **SET NULL FK**에는 relationship을 만들지 않고 FK 컬럼만 둔다.
- 다른 모델을 타입 힌트로 쓸 때는 양식처럼 `if TYPE_CHECKING:` 안에서 import한다.
- 순환 FK인 `chat_sessions.summary_id ↔ session_summaries.session_id`에서 `chat_sessions.summary_id`에는 `ForeignKey(..., use_alter=True)`를 지정한다.

## 7. 제약조건
- [FK 정의] 아래의 "유니크 제약" 목록을 `__table_args__`에 `UniqueConstraint(..., name="uq_테이블_컬럼")`으로 넣는다.
- 조회가 많은 FK와 날짜 컬럼(user_id, session_id, record_date 등)에는 `index=True`를 준다.

## 8. 주석
- 클래스 위에 `# 테이블 한글 이름`을 단다. 예: `# 채팅세션`
- ERD에 설명이 있는 컬럼은 줄 끝에 짧은 한글 주석을 단다.

# Enum 위치
| 파일 | Enum |
|---|---|
| `app/enums/common_enum.py` | Emotion, Instrument |
| `app/enums/user_enum.py` | UserRole, SocialProvider, Gender |
| `app/enums/chat_enum.py` | SessionStatus, SessionEndReason, SummaryStatus, SessionType, MessageRole, SystemRecordStatus, InputType, LlmPurpose, ParseStatus, GuardGate, GuardResult |
| `app/enums/checklist_enum.py` | AnswerType, ChecklistStatus, SkipReason, AssessmentSource |
| `app/enums/risk_enum.py` | RiskLevel, RiskSource, RiskStatus, RiskOrigin, ActorType, RiskAction, TrendFlag |
| `app/enums/record_enum.py` | SleepSource |
| `app/enums/hospital_enum.py` | MemoCategory, RoomType |
| `app/enums/care_request_enum.py` | RequestMode, RequestType, CareRequestStatus, ContactStatus |
| `app/enums/appointment_enum.py` | ContactMethod, AppointmentStatus, AppointmentKind, VisitType, BookingSource, ChangeType, RequestedBy, ScheduleType |
| `app/enums/notification_enum.py` | NotificationType |
| `app/enums/reward_enum.py` | ItemCategory, OwnershipType, MissionType, PointHistoryType |

# 테이블 정의
형식: `컬럼명 타입 -- 설명`. 따로 표시가 없으면 첫 번째 컬럼이 PK다. FK 대상은 아래 [FK 정의]를 따른다.

## user
**users (사용자)**
- id BIGINT
- email VARCHAR(255)
- nickname VARCHAR(50)
- role ENUM('patient','doctor')
- doctor_id BIGINT
- social_provider ENUM('kakao','naver','google')
- social_id VARCHAR(100)
- name VARCHAR(50)
- gender ENUM('male','female')
- birth_date DATE
- point_balance INT -- 현재 포인트
- created_at, updated_at, deleted_at DATETIME

**doctor_profiles (의사정보)**: user_id BIGINT(PK, users FK), hospital_id BIGINT, specialty VARCHAR(50), created_at DATETIME

**care_relations (담당관계)**: relation_id BIGINT, patient_id BIGINT, doctor_id BIGINT, started_at DATETIME, ended_at DATETIME, created_at DATETIME

**attendances (출석)**: attendance_id BIGINT, user_id BIGINT, attend_date DATE, first_access_at DATETIME

## chat
**chat_sessions (채팅세션)**
- id BIGINT, user_id BIGINT, prev_session_id BIGINT -- 이전 세션
- status ENUM('scheduled','active','ended','abandoned','missed','cancelled')
- end_reason ENUM('user','completed','timeout','safety')
- summary_status ENUM('pending','ready','failed','skipped')
- scheduled_at, expires_at, started_at, ended_at DATETIME
- summary_id BIGINT
- session_type ENUM('counselling','intake')

**messages (메시지)**
- id BIGINT, session_id BIGINT, seq INT
- role ENUM('user','assistant')
- content TEXT
- expression VARCHAR(30) -- AI 답변일 때 캐릭터 표정
- client_message_id CHAR(36) -- 클라이언트 중복 전송 방지용
- system_record_status ENUM('ok','partial','failed')
- created_at DATETIME
- input_type ENUM('text','voice')

**session_summaries (세션 사후 요약)**: id BIGINT, session_id BIGINT, context_summary TEXT, mood_summary JSON, topics JSON, chief_complaint TEXT -- 주호소, findings JSON -- AI 참고 소견, created_at DATETIME

**session_documents (세션 내 상담문서)**: session_id BIGINT, document_id BIGINT (복합 PK, 연결 테이블)

**llm_calls (llm호출)**
- id BIGINT, message_id BIGINT
- purpose ENUM('reply','summary')
- model VARCHAR(100), prompt_version VARCHAR(50), attempt INT
- parse_status ENUM('ok','retried_ok','failed')
- validation_errors JSON, tokens_in INT, tokens_out INT, latency_ms INT, status VARCHAR(20), error TEXT

**guard_checks (안전 필터 결과)**
- id BIGINT, message_id BIGINT
- gate ENUM('in','out')
- result ENUM('pass','safe_mode','blocked')
- category VARCHAR(50), model VARCHAR(100), original_text TEXT -- 차단된 원래 답변, created_at DATETIME

**emotion_analyses (감정분석)**
- id CHAR(36), message_id CHAR(36) ⚠
- model_version VARCHAR(50)
- anger, joy, anxiety, embarrassment, sadness, hurt DECIMAL(4,3)
- dominant ENUM('anger','joy','anxiety','embarrassment','sadness','hurt')

## rag
**rag_documents (RAG문서)**: id BIGINT, title VARCHAR(200), source VARCHAR(500), created_at DATETIME

**rag_chunks (RAG chunk)**: id BIGINT, document_id BIGINT, content TEXT, embedding BLOB, metadata JSON

## checklist
**checklist_items (체크리스트 목록)**
- id BIGINT, item_key VARCHAR(64), label VARCHAR(100), instruction TEXT
- answer_type ENUM('boolean','number','scale','choice','text')
- options JSON, is_active BOOLEAN
- instrument ENUM('phq9','gad7','isi','bdi2')
- item_no INT -- 척도 문항 번호

**session_checklist (세션 체크리스트)**
- id BIGINT, session_id BIGINT, item_id BIGINT, required BOOLEAN, sort_order INT
- status ENUM('pending','done','skipped')
- skip_reason ENUM('user_declined','not_applicable','unclear')
- value JSON, evidence_message_id BIGINT -- 근거 메시지, ask_count INT

**checklist_events (체크리스트 호출 기록)**: id BIGINT, checklist_id BIGINT, from_status ENUM('pending','done','skipped'), to_status ENUM('pending','done','skipped'), value JSON, created_at DATETIME

**assessment_results (척도 결과)**
- id BIGINT, user_id BIGINT, session_id BIGINT
- instrument ENUM('phq9','gad7','isi','bdi2')
- total_score INT, severity VARCHAR(20)
- source ENUM('ai_intake','self','clinic')
- assessed_at DATETIME

## risk
**risk_events (위험분석)**
- id BIGINT, message_id BIGINT
- level ENUM('low','medium','high')
- source ENUM('rule','llm','emotion','classifier','guard')
- evidence TEXT
- status ENUM('open','reviewed','escalated')
- user_id BIGINT
- origin ENUM('chat','diary','assessment','trend','inactive')
- origin_id CHAR(36) -- 출처 행 ID
- category VARCHAR(50), score DECIMAL(4,3), model_version VARCHAR(50), matched_terms JSON, context_judgement TEXT
- reviewed_by BIGINT, reviewed_at DATETIME, created_at DATETIME

**risk_event_actions (위험 조치 이력)**
- id BIGINT, risk_event_id BIGINT
- actor_type ENUM('ai','system','doctor'), actor_id BIGINT
- action ENUM('safety_question','notify_doctor','review','escalate','note')
- memo VARCHAR(500), created_at DATETIME

**daily_risk_scores (일별 위험 점수)**
- id BIGINT, user_id BIGINT, base_date DATETIME, score DECIMAL(5,2)
- trend_flag ENUM('none','rising','medium_3days','inactive_7days')
- detail JSON, created_at DATETIME

## record
**diaries (일기)**: diary_id BIGINT, user_id BIGINT, diary_date DATETIME, content TEXT, created_at, updated_at, deleted_at DATETIME

**diary_analyses (일기 분석)**: id BIGINT, diary_id BIGINT, model_version VARCHAR(50), anger·joy·anxiety·embarrassment·sadness·hurt DECIMAL(4,3), dominant ENUM(감정 6종), topics JSON, created_at DATETIME

**emotion_records (감정기록)**: emotion_id BIGINT, user_id BIGINT, record_date DATETIME, mood_score TINYINT, mood_tag VARCHAR(20), memo VARCHAR(255), created_at, updated_at DATETIME

**sleep_records (수면기록)**: sleep_id BIGINT, user_id BIGINT, record_date DATETIME, sleep_at DATETIME, wake_at DATETIME, sleep_minutes INT, source ENUM('manual','auto'), created_at, updated_at DATETIME

**exercise_records (운동기록)**: exercise_id BIGINT, user_id BIGINT, record_date DATETIME, exercise_type VARCHAR(255), duration_minutes INT, memo VARCHAR(255), created_at, updated_at DATETIME

## hospital
**hospitals (병원)**: hospital_id BIGINT, name VARCHAR(100), phone VARCHAR(20), address VARCHAR(255), sido VARCHAR(20), sigungu VARCHAR(30), latitude DECIMAL(10,7), longitude DECIMAL(10,7), is_accepting BOOLEAN -- 요청 받기 여부, created_at, updated_at DATETIME

**rooms (진료실)**: id BIGINT, hospital_id BIGINT, name VARCHAR(30), room_type ENUM('consult','exam'), is_active BOOLEAN

**patient_charts (환자 차트번호)**: id BIGINT, patient_id BIGINT, hospital_id BIGINT, chart_no VARCHAR(20), created_at DATETIME

**doctor_memos (관리 메모)**: id BIGINT, patient_id BIGINT, doctor_id BIGINT, category ENUM('clinic','counsel'), content VARCHAR(1000), is_pinned BOOLEAN, created_at, updated_at, deleted_at DATETIME

## care_request
**care_requests (진료요청)**
- request_id BIGINT, patient_id BIGINT
- request_mode ENUM('nearby','direct'), target_doctor_id BIGINT -- direct일 때
- request_type ENUM('consult','treatment')
- address VARCHAR(255), sido VARCHAR(20), sigungu VARCHAR(30), latitude DECIMAL(10,7), longitude DECIMAL(10,7)
- preferred_time VARCHAR(100), memo VARCHAR(255)
- status ENUM('requested','contacting','connected','booked','cancelled','expired','crisis')
- matched_hospital_id BIGINT, created_at, updated_at DATETIME

**request_contacts (병원연락내역)**: contact_id BIGINT, request_id BIGINT, hospital_id BIGINT, responded_by BIGINT, status ENUM('sent','available','declined','no_response'), sent_at DATETIME, responded_at DATETIME

**request_messages (예약채팅)**: message_id BIGINT, request_id BIGINT, sender_id BIGINT, content VARCHAR(1000), created_at DATETIME, read_at DATETIME

## appointment
**appointments (진료예약)**
- appointment_id BIGINT, request_id BIGINT, patient_id BIGINT, doctor_id BIGINT
- hospital_id CHAR(36) ⚠
- contact_method ENUM('phone','chat')
- scheduled_at DATETIME, end_at DATETIME
- status ENUM('booked','completed','cancelled','no_show','waiting','in_progress')
- completed_at DATETIME
- kind ENUM('treatment','psych_test'), tests JSON
- visit_type ENUM('first','return')
- room_id BIGINT, insurance_type VARCHAR(20)
- booking_source ENUM('patient_app','auto_after_visit','doctor')
- patient_note VARCHAR(255), created_by BIGINT, created_at, updated_at DATETIME

**appointment_changes (예약 변경 이력)**: id BIGINT, appointment_id BIGINT, from_at DATETIME, to_at DATETIME, change_type ENUM('reschedule','cancel'), reason VARCHAR(100), requested_by ENUM('patient','doctor'), changed_by BIGINT, created_at DATETIME

**schedules (일정)**: schedule_id BIGINT, user_id BIGINT, created_by BIGINT, schedule_type ENUM('counseling','appointment','exam','notice','personal'), title VARCHAR(100), memo VARCHAR(255), start_at, end_at, remind_at DATETIME, appointment_id BIGINT, created_at, updated_at DATETIME

## notification
**notifications (알림)**
- notification_id CHAR(36)
- user_id CHAR(36) ⚠
- notification_type ENUM('schedule','notice','system','request','appointment','chat','crisis')
- title VARCHAR(100), content VARCHAR(255)
- schedule_id CHAR(36) ⚠, risk_event_id CHAR(36) ⚠, request_id CHAR(36) ⚠, appointment_id CHAR(36) ⚠
- sent_at, read_at, created_at DATETIME

## reward
**items (아이템)**: item_id BIGINT, name VARCHAR(50), category ENUM('outfit','accessory','furniture','background'), price INT, image_url VARCHAR(255), is_active BOOLEAN, ownership_type ENUM('unique','stackable'), created_at DATETIME

**user_items_stackable (보유_아이템(중복))**: user_item_stackable_id BIGINT, item_id BIGINT, user_id BIGINT, quantity BIGINT

**user_items_unique (보유_아이템(유일))**: holding_item_id CHAR(36), item_id CHAR(36) ⚠, user_id CHAR(36) ⚠, acquired_at DATETIME

**myroom_entities (마이룸_배치물)**: user_id BIGINT, holding_item_id BIGINT, created_at DATETIME

**missions (미션)**: mission_id BIGINT, name VARCHAR(50), mission_type ENUM('daily_goal','all_clear_bonus','etc'), reward_point INT, daily_limit TINYINT, is_active BOOLEAN, sort_order INT, created_at DATETIME

**point_histories (포인트내역)**: history_id BIGINT, user_id BIGINT, history_type ENUM('earn','spend','cancel'), amount INT, balance_after INT, mission_id BIGINT -- 적립일 때, item_id BIGINT -- 사용일 때, reason VARCHAR(50), base_date DATETIME, created_at DATETIME

## collection (도감 / 캐릭터)
ERD에서 `Untitled` 테이블과 `Key` 컬럼에는 아래 이름을 붙여서 쓴다.
- **flowers (꽃)**: flower_id BIGINT, flower_description TEXT, flower_img VARCHAR(255)
- **moods (캐릭터_기본, 표정 마스터)**: mood_id BIGINT, mood_description TEXT, mood_img VARCHAR(255)
- **characters (캐릭터)**: character_id BIGINT, user_id BIGINT, name VARCHAR(30), hunger TINYINT -- 포만감, dirtiness TINYINT -- 청결도, flower_id BIGINT, mood_id BIGINT, updated_at DATETIME
- **flower_collections (도감_꽃)**: user_id BIGINT, flower_id BIGINT
- **mood_collections (도감_표정)**: user_id BIGINT, mood_id BIGINT, created_at DATETIME
- **item_collections (도감_아이템)**: user_id BIGINT, item_id BIGINT, created_at DATETIME


# FK 정의
형식: `컬럼 → 참조테이블.컬럼 (ondelete)`

## user
- users.doctor_id → users.id (SET NULL)
- doctor_profiles.user_id → users.id (CASCADE, 1:1, 이 컬럼이 PK)
- doctor_profiles.hospital_id → hospitals.hospital_id (CASCADE)
- care_relations.patient_id → users.id (CASCADE)
- care_relations.doctor_id → users.id (CASCADE)
- attendances.user_id → users.id (CASCADE)

## chat
- chat_sessions.user_id → users.id (CASCADE)
- chat_sessions.prev_session_id → chat_sessions.id (SET NULL)
- chat_sessions.summary_id → session_summaries.id (SET NULL, use_alter=True)
- messages.session_id → chat_sessions.id (CASCADE)
- session_summaries.session_id → chat_sessions.id (CASCADE, 1:1)
- session_documents.session_id → chat_sessions.id (CASCADE)
- session_documents.document_id → rag_documents.id (CASCADE)
- llm_calls.message_id → messages.id (CASCADE)
- guard_checks.message_id → messages.id (CASCADE)
- emotion_analyses.message_id → messages.id (CASCADE) ⚠

## rag
- rag_chunks.document_id → rag_documents.id (CASCADE)

## checklist
- session_checklist.session_id → chat_sessions.id (CASCADE)
- session_checklist.item_id → checklist_items.id (CASCADE)
- session_checklist.evidence_message_id → messages.id (SET NULL)
- checklist_events.checklist_id → session_checklist.id (CASCADE)
- assessment_results.user_id → users.id (CASCADE)
- assessment_results.session_id → chat_sessions.id (SET NULL)

## risk
- risk_events.user_id → users.id (CASCADE)
- risk_events.message_id → messages.id (SET NULL)
- risk_events.reviewed_by → users.id (SET NULL)
- risk_events.origin_id: FK 없음 (origin에 따라 다른 테이블을 가리키는 값. ERD대로 String(36) 유지)
- risk_event_actions.risk_event_id → risk_events.id (CASCADE)
- risk_event_actions.actor_id: FK 없음 (actor_type이 ai/system이면 비어 있음)
- daily_risk_scores.user_id → users.id (CASCADE)

## record
- diaries.user_id → users.id (CASCADE)
- diary_analyses.diary_id → diaries.diary_id (CASCADE, 1:1)
- emotion_records.user_id → users.id (CASCADE)
- sleep_records.user_id → users.id (CASCADE)
- exercise_records.user_id → users.id (CASCADE)

## hospital
- rooms.hospital_id → hospitals.hospital_id (CASCADE)
- patient_charts.patient_id → users.id (CASCADE)
- patient_charts.hospital_id → hospitals.hospital_id (CASCADE)
- doctor_memos.patient_id → users.id (CASCADE)
- doctor_memos.doctor_id → users.id (CASCADE)

## care_request
- care_requests.patient_id → users.id (CASCADE)
- care_requests.target_doctor_id → users.id (SET NULL)
- care_requests.matched_hospital_id → hospitals.hospital_id (SET NULL)
- request_contacts.request_id → care_requests.request_id (CASCADE)
- request_contacts.hospital_id → hospitals.hospital_id (CASCADE)
- request_contacts.responded_by → users.id (SET NULL)
- request_messages.request_id → care_requests.request_id (CASCADE)
- request_messages.sender_id → users.id (CASCADE)

## appointment
- appointments.patient_id → users.id (CASCADE)
- appointments.doctor_id → users.id (CASCADE)
- appointments.hospital_id → hospitals.hospital_id (CASCADE) ⚠
- appointments.request_id → care_requests.request_id (SET NULL)
- appointments.room_id → rooms.id (SET NULL)
- appointments.created_by → users.id (SET NULL)
- appointment_changes.appointment_id → appointments.appointment_id (CASCADE)
- appointment_changes.changed_by → users.id (SET NULL)
- schedules.user_id → users.id (CASCADE)
- schedules.created_by → users.id (SET NULL)
- schedules.appointment_id → appointments.appointment_id (SET NULL)

## notification
- notifications.user_id → users.id (CASCADE) ⚠
- notifications.schedule_id → schedules.schedule_id (SET NULL) ⚠
- notifications.risk_event_id → risk_events.id (SET NULL) ⚠
- notifications.request_id → care_requests.request_id (SET NULL) ⚠
- notifications.appointment_id → appointments.appointment_id (SET NULL) ⚠

## reward
- user_items_stackable.user_id → users.id (CASCADE)
- user_items_stackable.item_id → items.item_id (CASCADE)
- user_items_unique.user_id → users.id (CASCADE) ⚠
- user_items_unique.item_id → items.item_id (CASCADE) ⚠
- myroom_entities.user_id → users.id (CASCADE)
- myroom_entities.holding_item_id → user_items_unique.holding_item_id (CASCADE) ⚠ (ERD는 BIGINT지만 참조 PK가 CHAR(36)이므로 String(36)으로 맞춤)
- point_histories.user_id → users.id (CASCADE)
- point_histories.mission_id → missions.mission_id (SET NULL)
- point_histories.item_id → items.item_id (SET NULL)

## collection
- characters.user_id → users.id (CASCADE)
- characters.flower_id → flowers.flower_id (SET NULL)
- characters.mood_id → moods.mood_id (SET NULL)
- flower_collections.user_id → users.id (CASCADE)
- flower_collections.flower_id → flowers.flower_id (CASCADE)
- mood_collections.user_id → users.id (CASCADE)
- mood_collections.mood_id → moods.mood_id (CASCADE)
- item_collections.user_id → users.id (CASCADE)
- item_collections.item_id → items.item_id (CASCADE)

## 복합 PK
- session_documents (session_id, document_id)
- myroom_entities (user_id, holding_item_id)
- flower_collections (user_id, flower_id)
- mood_collections (user_id, mood_id)
- item_collections (user_id, item_id)

## 유니크 제약
- users (social_provider, social_id)
- attendances (user_id, attend_date): 하루 한 번 출석
- messages (session_id, seq)
- messages (client_message_id): 중복 전송 방지
- session_checklist (session_id, item_id)
- checklist_items (item_key)
- daily_risk_scores (user_id, base_date)
- patient_charts (hospital_id, chart_no)
- patient_charts (patient_id, hospital_id)
- user_items_stackable (user_id, item_id)

# 출력 형식
- 아래 순서로 파일마다 `### app/models/user_model.py`처럼 경로를 제목으로 쓰고, 바로 아래에 전체 코드를 코드 블록으로 출력해 줘.
  1. 다른 테이블이 많이 참조하는 테이블: users, hospitals, rag_documents, checklist_items, items, missions, flowers, moods
  2. 나머지 테이블을 [테이블 정의]의 도메인 순서대로
  3. 마지막으로 `app/models/__init__.py`
- 코드를 생략하지 마("... 나머지도 동일" 금지). 한 번에 다 못 쓰면 파일 단위로 끊고, 내가 "계속"이라고 하면 이어서 써 줘.
- 다 쓰고 나면 아래 두 가지를 정리해 줘.
  1. ⚠ 표시한 컬럼을 ERD와 다르게 바꾼 목록
  2. relationship 이름이 서로 맞는지(back_populates 짝) 점검한 결과
