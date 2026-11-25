# 마음브릿지 backapp — SQLAlchemy 모델 작성 프롬프트

너는 FastAPI + SQLAlchemy 2.0 + PostgreSQL 백엔드를 작성한다.
아래 **[ERD 명세]**의 테이블 50개를 **[기준 코드]**와 같은 양식으로 SQLAlchemy 모델 코드로 작성해라.
ERD 명세에 없는 컬럼·테이블을 추가하거나, 있는 컬럼을 빼거나 이름을 바꾸지 마라.

---

## 1. 기준 코드 (이 양식을 그대로 따른다)

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

### 1-1. 자식(FK를 가진 쪽) 양식 — 기준 코드의 반대편

```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Text, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.member_model import Member

KST = timezone(timedelta(hours=9)) # UTC+9

class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    post_title: Mapped[str] = mapped_column(Text, nullable=False)
    post_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    member: Mapped["Member"] = relationship("Member", back_populates="posts")
```

---

## 2. 작성 규칙

### 2-1. 파일·클래스
- 테이블 1개 = 파일 1개. 파일·클래스 이름은 **4장 배치표**에 적힌 그대로 쓴다.
- import 순서와 모양은 기준 코드와 같게: 표준 라이브러리 → sqlalchemy → sqlalchemy.orm → app.enums → `Base` (주석 포함) → `TYPE_CHECKING` 블록 → `KST`.
- 다른 모델 클래스는 `TYPE_CHECKING` 블록 안에서만 import 하고, relationship에는 문자열 `"ClassName"`으로 적는다(순환 import 방지).
- `KST = timezone(timedelta(hours=9)) # UTC+9`는 날짜·시각 컬럼이 있는 파일마다 둔다.
- 컬럼 순서는 ERD 명세 순서(PK → FK → 나머지)를 따른다.
- 컬럼 뒤에 ERD 주석(`//` 뒤 내용)을 짧게 줄여 `# 한글 주석`으로 단다. 예: `level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)  # 1 새싹 2 생장 3 꽃봉오리 4 만개`

### 2-2. 타입 변환표 (ERD → SQLAlchemy / 파이썬 타입)
| ERD | mapped_column 타입 | Mapped[...] |
|---|---|---|
| BIGINT | `BigInteger` | `int` |
| INT | `Integer` | `int` |
| TINYINT | `SmallInteger` (PostgreSQL에 TINYINT 없음) | `int` |
| VARCHAR(n) | `String(n)` | `str` |
| CHAR(36) | `String(36)` | `str` |
| TEXT | `Text` | `str` |
| DECIMAL(p, s) | `Numeric(p, s)` | `Decimal` (`from decimal import Decimal`) |
| BOOLEAN | `Boolean` | `bool` |
| DATE | `Date` | `date` |
| DATETIME | `DateTime(timezone=True)` | `datetime` |
| JSON | `JSONB` (`from sqlalchemy.dialects.postgresql import JSONB`) | `dict` 또는 `list` (명세 주석에 배열 예시가 있으면 `list`) |
| BLOB (rag_chunks.embedding만) | `Vector(EMBEDDING_DIM)` (`from pgvector.sqlalchemy import Vector`, 파일 위쪽에 `EMBEDDING_DIM = 768` 상수) | `list[float]` |
| ENUM(...) | `SQLEnum(...)` — 2-3 참고 | 해당 Enum 클래스 |

### 2-3. ENUM
- ERD의 ENUM 컬럼마다 파이썬 Enum 클래스를 `app/enums/`에 만든다. 형식:
  ```python
  from enum import Enum

  class UserRole(str, Enum):
      PATIENT = "patient"
      DOCTOR = "doctor"
  ```
  멤버 이름은 대문자, 값은 ERD에 적힌 소문자 문자열 그대로.
- 파일 위치: 그 테이블의 enum 파일 `app/enums/<단수형>_enum.py` (예: `users` → `app/enums/user_enum.py`). 클래스 이름은 `<모델클래스><컬럼>` (예: `UserRole`, `UserSocialProvider`, `ChatSessionStatus`).
- **여러 테이블이 같은 값 집합을 쓰는 ENUM은 `app/enums/common_enum.py`에 한 번만** 만들고 같이 쓴다:
  - `Season` (spring·summer·autumn·winter) — flowers.season, items.season
  - `Instrument` (phq9·gad7·isi·bdi2) — assessment_results.instrument, checklist_items.instrument
  - `EmotionType` (anger·joy·anxiety·embarrassment·sadness·hurt) — emotion_analyses.dominant, diary_analyses.dominant
  - `ChecklistStatus` (pending·done·skipped) — session_checklist.status, checklist_events.from_status·to_status
  - `RequestedBy` (patient·doctor) — appointment_changes.requested_by
- 컬럼 선언은 기준 코드처럼 `native_enum=False`를 쓰되, **DB에 ERD 값(소문자)이 그대로 저장되도록 `values_callable`을 반드시 붙인다** (안 붙이면 `PATIENT` 같은 멤버 이름이 저장됨):
  ```python
  role: Mapped[UserRole] = mapped_column(
      SQLEnum(UserRole, native_enum=False, values_callable=lambda e: [m.value for m in e]),
      nullable=False
  )
  ```

### 2-4. PK
- 단일 BIGINT PK: `mapped_column(BigInteger, Identity(), primary_key=True)`. PK 컬럼 이름은 ERD 그대로(`id`, `diary_id`, `appointment_id` 등).
- **PK이면서 FK인 1:1 테이블** (`doctor_profiles.user_id`, `user_settings.user_id`): `Identity()` 없이 `ForeignKey("users.id", ondelete="CASCADE"), primary_key=True`.
- **복합 PK** (`session_documents`의 session_id+document_id, `user_expressions`의 user_id+expression_id): 두 컬럼 모두 `primary_key=True`, `Identity()` 없음.

### 2-5. NULL·기본값
- ERD `NOT NULL` → `Mapped[T]` + `nullable=False`. ERD `NULL` → `Mapped[T | None]` (nullable 생략).
- ERD `default=` 값은 `default=`로 넣는다. ENUM 기본값은 Enum 멤버로(예: `default=RiskEventStatus.OPEN`), BOOLEAN은 `True/False`.
- `created_at`, `first_access_at`, `acquired_at`, `first_seen_at`, `assessed_at`, `sent_at`(request_contacts) 등 "생성 순간 시각"은 `default=lambda: datetime.now(KST)`.
- `updated_at`은 `onupdate=lambda: datetime.now(KST)` (NULL 허용이므로 default는 두지 않는다).
- `characters.dirtiness_updated_at`, `characters.hunger_updated_at`은 NOT NULL이므로 `default=lambda: datetime.now(KST)`.
- 그 밖의 DATETIME/DATE에는 기본값을 넣지 않는다.

### 2-6. FK·ondelete
- FK는 `ForeignKey("테이블.컬럼", ondelete=...)`로 쓴다. 대상 컬럼은 명세의 `FK→` 그대로.
- ondelete 규칙:
  - **NOT NULL FK이고 부모에 소속된 기록**(일기·메시지·보유아이템 등) → `ondelete="CASCADE"`
  - **NULL 허용 FK**(참조만 하는 값: room_id, current_flower_id, outfit_item_id, request_id, history_id, evidence_message_id 등) → `ondelete="SET NULL"`
  - **처리자·행위자·작성자를 남기는 FK** (appointment_changes.changed_by, risk_event_actions.actor_id, risk_events.reviewed_by, schedules.created_by, appointments.created_by, doctor_verifications.reviewed_by, request_messages.sender_id, request_contacts.responded_by) → NOT NULL이면 `ondelete="RESTRICT"`, NULL이면 `"SET NULL"`
  - **기준 데이터를 가리키는 FK** (items, flowers, expressions, missions, hospitals, checklist_items, rag_documents를 가리키는 NOT NULL FK) → `ondelete="RESTRICT"`
- `risk_events.origin_id`는 여러 테이블을 가리키므로 **FK 없이** 일반 BigInteger 컬럼으로 둔다.
- `session_checklist.evidence_message_id`는 단일 FK(`messages.id`)로만 만든다(복합 FK는 만들지 않음).

### 2-7. relationship
- 자식 쪽: FK마다 `부모: Mapped["Parent"] = relationship("Parent", back_populates="...")` (NULL FK면 `Mapped["Parent | None"]`).
- 부모 쪽: `자식들: Mapped[list["Child"]] = relationship("Child", back_populates="...", cascade=...)`.
  - 자식 FK가 `ondelete="CASCADE"`면 `cascade="all, delete-orphan"` + `passive_deletes=True`.
  - 그 외(SET NULL·RESTRICT)는 cascade를 쓰지 않는다.
- **같은 부모 테이블을 FK 2개 이상으로 가리키면** 양쪽 모두 `foreign_keys=[...]`를 지정하고, 속성 이름을 컬럼 뜻대로 짓는다.
  - 예: appointments의 `patient_id`·`doctor_id`·`created_by` → `patient`, `doctor`, `creator` / User 쪽 `patient_appointments`, `doctor_appointments`, `created_appointments`
  - 해당 테이블: appointments, care_relations, care_requests, doctor_memos, schedules, characters(items 4개), risk_events(users 2개)
- **자기 참조** `chat_sessions.prev_session_id` → `prev_session: Mapped["ChatSession | None"] = relationship("ChatSession", remote_side="ChatSession.id")` (역방향 리스트는 만들지 않음).
- 1:1 (doctor_profiles, user_settings, session_summaries ↔ chat_sessions, admins ↔ users) → 부모 쪽은 `Mapped["Child | None"]`에 `uselist=False`.
- 기준 데이터 테이블(items, flowers, expressions, missions, checklist_items, rag_documents, hospitals)은 역방향 리스트 relationship을 만들지 않고, 자식 쪽 단방향만 둔다(`back_populates` 생략).

### 2-8. 제약조건·인덱스 (`__table_args__`)
명세 주석에 있는 UNIQUE를 아래 그대로 건다. 이름 규칙: `uq_<테이블>_<컬럼들>`, 부분 인덱스는 `uix_<테이블>_<설명>`.

| 테이블 | 제약 |
|---|---|
| users | `UniqueConstraint("social_provider", "social_id")` |
| admins | `user_id` → `unique=True` |
| user_settings / doctor_profiles | PK가 user_id라 따로 없음 |
| emotion_records | `UniqueConstraint("user_id", "record_date")` |
| patient_charts | `UniqueConstraint("hospital_id", "chart_no")` |
| session_summaries | `session_id` → `unique=True` |
| user_flowers | `UniqueConstraint("user_id", "flower_id")` |
| user_items | `UniqueConstraint("user_id", "item_id")` |
| user_mission_logs | `UniqueConstraint("user_id", "mission_id", "log_date")` |
| messages | `UniqueConstraint("session_id", "seq")` |
| diaries | 부분 UNIQUE: `Index("uix_diaries_user_date_alive", "user_id", "diary_date", unique=True, postgresql_where=text("deleted_at IS NULL"))` |
| care_action_logs | 부분 UNIQUE: `("user_id", "action_type", "action_date")`, `postgresql_where=text("action_type IN ('water','sunlight','pat','lullaby')")` |
| chat_sessions | 부분 UNIQUE: `("user_id",)`, `postgresql_where=text("status = 'active'")` (환자당 active 1개) |
| doctor_verifications | 부분 UNIQUE: `("user_id",)`, `postgresql_where=text("status = 'pending'")` (1명당 pending 1건) |

- `Index`, `text`는 `from sqlalchemy import Index, text`로 import.
- 그 밖에 인덱스는 추가하지 않는다.

### 2-9. 마지막에 함께 만들 파일
- `app/models/__init__.py`: 50개 모델 클래스를 모두 import 하고 `__all__`에 넣는다(서버 시작 시 `Base.metadata`가 모든 테이블을 알도록).
- `app/enums/__init__.py`: 비워 둔다.

---

## 3. 출력 방식
- 한 번에 다 쓰지 말고 **4장의 배치 순서대로 한 배치씩** 출력한다. 배치마다 ① 그 배치에서 새로 필요한 enum 파일 ② 모델 파일을 파일 경로 제목과 함께 코드 블록으로 낸다.
- enum 파일이 이미 앞 배치에서 만들어졌으면 추가되는 클래스만 "이어 붙일 부분"으로 표시한다.
- 앞 배치 모델에 역방향 relationship을 추가해야 하면, 해당 파일 경로와 **추가할 줄만** 따로 보여 준다.
- 코드 외 설명은 배치마다 3줄 이내.
- 내가 "다음"이라고 하면 다음 배치를 출력한다.

---

## 4. 배치 순서 · 파일·클래스 이름

**배치 1 — 회원·병원·권한**
| 테이블 | 클래스 | 파일 |
|---|---|---|
| users | User | app/models/user_model.py |
| admins | Admin | app/models/admin_model.py |
| user_settings | UserSetting | app/models/user_setting_model.py |
| hospitals | Hospital | app/models/hospital_model.py |
| rooms | Room | app/models/room_model.py |
| doctor_profiles | DoctorProfile | app/models/doctor_profile_model.py |
| doctor_verifications | DoctorVerification | app/models/doctor_verification_model.py |
| patient_charts | PatientChart | app/models/patient_chart_model.py |
| care_relations | CareRelation | app/models/care_relation_model.py |

**배치 2 — AI 상담**
| 테이블 | 클래스 | 파일 |
|---|---|---|
| chat_sessions | ChatSession | app/models/chat_session_model.py |
| messages | Message | app/models/message_model.py |
| session_summaries | SessionSummary | app/models/session_summary_model.py |
| rag_documents | RagDocument | app/models/rag_document_model.py |
| rag_chunks | RagChunk | app/models/rag_chunk_model.py |
| session_documents | SessionDocument | app/models/session_document_model.py |
| checklist_items | ChecklistItem | app/models/checklist_item_model.py |
| session_checklist | SessionChecklist | app/models/session_checklist_model.py |
| checklist_events | ChecklistEvent | app/models/checklist_event_model.py |
| llm_calls | LlmCall | app/models/llm_call_model.py |
| guard_checks | GuardCheck | app/models/guard_check_model.py |
| emotion_analyses | EmotionAnalysis | app/models/emotion_analysis_model.py |
| assessment_results | AssessmentResult | app/models/assessment_result_model.py |

**배치 3 — 위험 감지**
| 테이블 | 클래스 | 파일 |
|---|---|---|
| risk_events | RiskEvent | app/models/risk_event_model.py |
| risk_event_actions | RiskEventAction | app/models/risk_event_action_model.py |
| daily_risk_scores | DailyRiskScore | app/models/daily_risk_score_model.py |

**배치 4 — 진료 요청·예약·일정·알림**
| 테이블 | 클래스 | 파일 |
|---|---|---|
| care_requests | CareRequest | app/models/care_request_model.py |
| request_contacts | RequestContact | app/models/request_contact_model.py |
| request_messages | RequestMessage | app/models/request_message_model.py |
| appointments | Appointment | app/models/appointment_model.py |
| appointment_changes | AppointmentChange | app/models/appointment_change_model.py |
| schedules | Schedule | app/models/schedule_model.py |
| notifications | Notification | app/models/notification_model.py |
| doctor_memos | DoctorMemo | app/models/doctor_memo_model.py |

**배치 5 — 환자 기록**
| 테이블 | 클래스 | 파일 |
|---|---|---|
| diaries | Diary | app/models/diary_model.py |
| diary_analyses | DiaryAnalysis | app/models/diary_analysis_model.py |
| emotion_records | EmotionRecord | app/models/emotion_record_model.py |
| sleep_records | SleepRecord | app/models/sleep_record_model.py |
| exercise_records | ExerciseRecord | app/models/exercise_record_model.py |
| attendances | Attendance | app/models/attendance_model.py |

**배치 6 — 캐릭터·꽃·아이템·미션·포인트**
| 테이블 | 클래스 | 파일 |
|---|---|---|
| flowers | Flower | app/models/flower_model.py |
| expressions | Expression | app/models/expression_model.py |
| items | Item | app/models/item_model.py |
| characters | Character | app/models/character_model.py |
| user_flowers | UserFlower | app/models/user_flower_model.py |
| user_expressions | UserExpression | app/models/user_expression_model.py |
| user_items | UserItem | app/models/user_item_model.py |
| care_action_logs | CareActionLog | app/models/care_action_log_model.py |
| missions | Mission | app/models/mission_model.py |
| point_histories | PointHistory | app/models/point_history_model.py |
| user_mission_logs | UserMissionLog | app/models/user_mission_log_model.py |

마지막 배치 뒤에 `app/models/__init__.py`를 출력한다.

---

## 5. ERD 명세 (2026-11-24 확정본, 테이블 50개)
형식: `- 컬럼 | 타입 | PK | NULL 여부 | default | FK→대상 | // 주석`

### admins (관리자)
- id | BIGINT | PK | NOT NULL | // PK
- user_id | BIGINT | NOT NULL | FK→users.id | // 관리자인 회원 ID. UNIQUE (회원 1명당 1행)
- created_at | DATETIME | NOT NULL | // 관리자로 지정된 시각

### appointment_changes (예약 변경 이력)
- id | BIGINT | PK | NOT NULL | // uuid PK
- appointment_id | BIGINT | NOT NULL | FK→appointments.appointment_id | // 예약
- from_at | DATETIME | NOT NULL | // 변경 전 일시
- to_at | DATETIME | NULL | // 변경 후 일시
- change_type | ENUM('reschedule', 'cancel') | NOT NULL | // 변경 종류
- reason | VARCHAR(100) | NULL | // 사유
- requested_by | ENUM('patient', 'doctor') | NOT NULL | // 요청자
- changed_by | BIGINT | NOT NULL | FK→users.id | // 처리자
- created_at | DATETIME | NOT NULL | // 변경 시각

### appointments (진료예약)
- appointment_id | BIGINT | PK | NOT NULL | // 예약 ID
- request_id | BIGINT | NULL | FK→care_requests.request_id | // 요청 ID
- patient_id | BIGINT | NOT NULL | FK→users.id | // 환자 ID
- doctor_id | BIGINT | NOT NULL | FK→users.id | // 의사 ID
- hospital_id | BIGINT | NOT NULL | FK→hospitals.hospital_id | // 병원 ID
- contact_method | ENUM('phone', 'chat') | NOT NULL | // 예약 연락 방식
- scheduled_at | DATETIME | NOT NULL | // 진료 일시
- status | ENUM('booked', 'completed', 'cancelled', 'no_show', 'waiting', 'in_progress') | NOT NULL | // 예약 상태
- completed_at | DATETIME | NULL | // 진료 완료 시각
- created_at | DATETIME | NOT NULL | // 예약 시각
- updated_at | DATETIME | NULL | // 수정 시각
- end_at | DATETIME | NULL | // 종료 시각
- kind | ENUM('treatment', 'psych_test') | NOT NULL | default='treatment' | // 예약 종류
- tests | JSON | NULL | // psych_test일 때. 예: ["phq9","gad7","bdi2"]
- visit_type | ENUM('first', 'return') | NULL | // 초진·재진
- room_id | BIGINT | NULL | FK→rooms.id | // 진료실
- insurance_type | VARCHAR(20) | NULL | // 보험 구분
- booking_source | ENUM('patient_app', 'auto_after_visit', 'doctor') | NOT NULL | // 예약 경로
- patient_note | VARCHAR(255) | NULL | // 요청 사항
- created_by | BIGINT | NULL | FK→users.id | // 등록자

### assessment_results (척도 결과)
- id | BIGINT | PK | NOT NULL | // uuid PK
- user_id | BIGINT | NOT NULL | FK→users.id | // 환자
- session_id | BIGINT | NULL | FK→chat_sessions.id | // 문진 세션
- instrument | ENUM('phq9', 'gad7', 'isi', 'bdi2') | NOT NULL | // 척도
- total_score | INT | NOT NULL | // 총점
- severity | VARCHAR(20) | NOT NULL | // 예: 중등도
- source | ENUM('ai_intake', 'self', 'clinic') | NOT NULL | // 측정 방식
- assessed_at | DATETIME | NOT NULL | // 측정 시각

### attendances (출석)
- attendance_id | BIGINT | PK | NOT NULL | // 출석 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 회원 ID
- attend_date | DATE | NOT NULL | // 출석한 날
- first_access_at | DATETIME | NOT NULL | // 첫 접속 시각

### care_action_logs (돌봄 기록)
- log_id | BIGINT | PK | NOT NULL | // 기록 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 회원 ID
- action_type | ENUM('water', 'sunlight', 'pat', 'lullaby', 'snack', 'wash') | NOT NULL | // water·sunlight·pat = 무료, 종류마다 하루 1번. lullaby = 15P, 하루 1번. (user_id, action_type, action_date) UNIQUE는 water·sunlight·pat·lullaby만
- action_date | DATE | NOT NULL | // 재화를 쓰지 않는 돌봄은 하루 1번(D2) 확인용. '하루' = 자정
- item_id | BIGINT | NULL | FK→items.item_id | // 간식·씻기기처럼 아이템을 쓴 경우
- exp_gain | INT | NOT NULL | default=0 | // 오른 경험치
- point_spent | INT | NOT NULL | default=0 | // 쓴 포인트
- created_at | DATETIME | NOT NULL | // 기록 시각

### care_relations (담당관계)
- relation_id | BIGINT | PK | NOT NULL | // 담당 관계 ID
- patient_id | BIGINT | NOT NULL | FK→users.id | // 환자 ID
- doctor_id | BIGINT | NOT NULL | FK→users.id | // 담당 의사 ID
- started_at | DATETIME | NOT NULL | // 담당 시작일
- ended_at | DATETIME | NULL | // 담당 종료일
- created_at | DATETIME | NOT NULL | // 생성 시각

### care_requests (진료요청)
- request_id | BIGINT | PK | NOT NULL | // 요청 ID
- patient_id | BIGINT | NOT NULL | FK→users.id | // 환자 ID
- request_mode | ENUM('nearby', 'direct') | NOT NULL | // 요청 방식
- target_doctor_id | BIGINT | NULL | FK→users.id | // 지정 의사 ID
- request_type | ENUM('consult', 'treatment') | NOT NULL | // 요청 종류
- address | VARCHAR(255) | NULL | // 요청 주소
- sido | VARCHAR(20) | NULL | // 시·도
- sigungu | VARCHAR(30) | NULL | // 시·군·구
- latitude | DECIMAL(10, 7) | NULL | // 위도
- longitude | DECIMAL(10, 7) | NULL | // 경도
- preferred_time | VARCHAR(100) | NULL | // 희망 시간대
- memo | VARCHAR(255) | NULL | // 요청 메모
- status | ENUM('requested', 'contacting', 'connected', 'booked', 'cancelled', 'expired', 'crisis') | NOT NULL | // 진행 상태
- matched_hospital_id | BIGINT | NULL | FK→hospitals.hospital_id | // 연결된 병원 ID
- created_at | DATETIME | NOT NULL | // 요청 시각
- updated_at | DATETIME | NULL | // 수정 시각

### characters (캐릭터)
- character_id | BIGINT | PK | NOT NULL | // 캐릭터 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 주인 회원 ID
- name | VARCHAR(30) | NULL | // 캐릭터 이름
- dirtiness | TINYINT | NOT NULL | default=0 | // 꼬질함 0~100. 0에서 시작, 2일마다 +10(최대 100). 구간: 0~29 깨끗, 30~59 조금, 60~89 꼬질꼬질, 90~100 흙투성이 (임의 값)
- hunger | TINYINT | NOT NULL | default=0 | // 배고픔 0~100. 0에서 시작, 하루마다 +10(최대 100). 간식 효과로 회복 (임의 값)
- updated_at | DATETIME | NULL | // 상태 변경 시각
- current_flower_id | BIGINT | NULL | FK→flowers.flower_id | // 지금 키우는 꽃. 16종을 모두 피웠으면 마지막 꽃 그대로
- mood_expression_id | BIGINT | NULL | FK→expressions.expression_id | // 오늘의 기분. expressions.category = mood 중 랜덤
- mood_date | DATE | NULL | // 오늘 날짜와 다르면 다음 상호작용 때 새로 정함
- level | TINYINT | NOT NULL | default=1 | // 캐릭터 레벨 = 성장 단계. 1 새싹 2 생장 3 꽃봉오리 4 만개. 단계마다 경험치 400. 만개 → 꽃 도감 등록 후 1. 16종을 모두 피우면 4로 유지. 마이룸에서만 표시
- exp | INT | NOT NULL | default=0 | // 단계별 필요 값은 미정(결정-52)
- created_at | DATETIME | NOT NULL | // 만든 시각
- outfit_item_id | BIGINT | NULL | FK→items.item_id | // 적용한 의상
- accessory_item_id | BIGINT | NULL | FK→items.item_id | // 적용한 소품
- background_item_id | BIGINT | NULL | FK→items.item_id | // 적용한 배경
- dirtiness_updated_at | DATETIME | NOT NULL | // 마지막으로 씻겼거나 꼬질함이 늘어난 시각. 여기서 2일 지날 때마다 +10
- furniture_item_id | BIGINT | NULL | FK→items.item_id | // 마이룸에는 가구 1개만 놓음
- hunger_updated_at | DATETIME | NOT NULL | // 마지막으로 간식을 먹었거나 배고픔이 늘어난 시각

### chat_sessions (채팅세션)
- id | BIGINT | PK | NOT NULL | // uuid PK
- user_id | BIGINT | NOT NULL | FK→users.id | // 환자
- prev_session_id | BIGINT | NULL | FK→chat_sessions.id | // 직전 예정 세션 (참조용)
- status | ENUM('scheduled', 'active', 'ended', 'abandoned', 'missed', 'cancelled') | NOT NULL | // 환자당 active 1개 (부분 unique)
- end_reason | ENUM('user', 'completed', 'timeout', 'safety') | NULL | // 종료 사유
- summary_status | ENUM('pending', 'ready', 'failed', 'skipped') | NULL | // 사후 요약 상태
- scheduled_at | DATETIME | NOT NULL | // 상담 예정 시각 (이후 접속 가능)
- expires_at | DATETIME | NULL | // 접속 마감. 경과 시 missed
- started_at | DATETIME | NULL | // 시작 시각 (시작 전 null)
- ended_at | DATETIME | NULL | // 종료 시각
- session_type | ENUM('counseling', 'intake') | NOT NULL | default='counseling' | // counseling=일반 AI 상담, intake=초진 전 AI 사전 문진

### checklist_events (체크리스트 호출 기록)
- id | BIGINT | PK | NOT NULL | // uuid PK
- checklist_id | BIGINT | NOT NULL | FK→session_checklist.id | // 체크리스트 행
- from_status | ENUM('pending', 'done', 'skipped') | NOT NULL | // 변경 전
- to_status | ENUM('pending', 'done', 'skipped') | NOT NULL | // 변경 후
- value | JSON | NULL | // 변경 시점 값
- created_at | DATETIME | NOT NULL | // 변경 시각

### checklist_items (체크리스트 목록)
- id | BIGINT | PK | NOT NULL | // uuid PK
- item_key | VARCHAR(64) | NOT NULL | // 불변 식별자. 예: sleep_hours
- label | VARCHAR(100) | NOT NULL | // 화면·의사용 이름
- instruction | TEXT | NOT NULL | // LLM 질문 지침
- answer_type | ENUM('boolean', 'number', 'scale', 'choice', 'text') | NOT NULL | // 답 형태
- options | JSON | NULL | // choice·scale 보기와 범위
- is_active | BOOLEAN | NOT NULL | default=TRUE | // 사용 여부
- instrument | ENUM('phq9', 'gad7', 'isi', 'bdi2') | NULL | // 척도 문항일 때만. 보기별 점수는 options JSON에
- item_no | INT | NULL | // 척도 문항 번호

### daily_risk_scores (일별 위험 점수)
- id | BIGINT | PK | NOT NULL | // uuid PK
- user_id | BIGINT | NOT NULL | FK→users.id | // 환자
- base_date | DATETIME | NOT NULL | // 기준 날짜
- score | DECIMAL(5, 2) | NOT NULL | // 일 점수
- trend_flag | ENUM('none', 'rising', 'medium_3days', 'inactive_7days') | NOT NULL | default='none' | // 추세 표시
- detail | JSON | NULL | // 계산 근거
- created_at | DATETIME | NOT NULL | // 생성 시각

### diaries (일기)
- diary_id | BIGINT | PK | NOT NULL | // 일기 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 작성자 ID
- diary_date | DATETIME | NOT NULL | // 일기 날짜. (user_id, diary_date) UNIQUE는 deleted_at IS NULL인 줄에만 건다(지운 날 다시 쓰기 허용). 지난 날짜는 최근 7일까지
- content | TEXT | NOT NULL | // 본문
- created_at | DATETIME | NOT NULL | // 작성 시각
- updated_at | DATETIME | NULL | // 수정 시각
- deleted_at | DATETIME | NULL | // 삭제 시각

### diary_analyses (일기 분석)
- id | BIGINT | PK | NOT NULL | // uuid PK
- diary_id | BIGINT | NOT NULL | FK→diaries.diary_id | // 일기
- model_version | VARCHAR(50) | NOT NULL | // 모델 버전
- anger | DECIMAL(4, 3) | NOT NULL | // 분노 0~1
- joy | DECIMAL(4, 3) | NOT NULL | // 기쁨 0~1
- anxiety | DECIMAL(4, 3) | NOT NULL | // 불안 0~1
- embarrassment | DECIMAL(4, 3) | NOT NULL | // 당황 0~1
- sadness | DECIMAL(4, 3) | NOT NULL | // 슬픔 0~1
- hurt | DECIMAL(4, 3) | NOT NULL | // 상처 0~1
- dominant | ENUM('anger', 'joy', 'anxiety', 'embarrassment', 'sadness', 'hurt') | NOT NULL | // 최고 감정
- topics | JSON | NULL | // 주제 키워드
- created_at | DATETIME | NOT NULL | // 분석 시각

### doctor_memos (관리 메모)
- id | BIGINT | PK | NOT NULL | // uuid PK
- patient_id | BIGINT | NOT NULL | FK→users.id | // 환자
- doctor_id | BIGINT | NOT NULL | FK→users.id | // 작성 의사
- category | ENUM('clinic', 'counsel') | NOT NULL | // clinic=진료, counsel=상담
- content | VARCHAR(1000) | NOT NULL | // 내용
- is_pinned | BOOLEAN | NOT NULL | default=FALSE | // 고정
- created_at | DATETIME | NOT NULL | // 작성 시각
- updated_at | DATETIME | NULL | // 수정 시각
- deleted_at | DATETIME | NULL | // 삭제 시각

### doctor_profiles (의사정보)
- user_id | BIGINT | PK | NOT NULL | FK→users.id | // 의사 회원 ID
- hospital_id | BIGINT | NOT NULL | FK→hospitals.hospital_id | // 소속 병원 ID
- specialty | VARCHAR(50) | NULL | // 진료 분야
- created_at | DATETIME | NOT NULL | // 등록 시각

### doctor_verifications (의사 승인 신청)
- id | BIGINT | PK | NOT NULL | // PK
- user_id | BIGINT | NOT NULL | FK→users.id | // 신청한 회원 ID. 반려 후 재신청 가능, pending은 1명당 1건
- hospital_id | BIGINT | NOT NULL | FK→hospitals.hospital_id | // 승인 시 doctor_profiles.hospital_id로 복사
- reviewed_by | BIGINT | NULL | FK→admins.id | // 승인·반려한 관리자. 대기 중에는 NULL
- license_number | VARCHAR(50) | NOT NULL | // 의사 면허번호
- specialty | VARCHAR(50) | NULL | // 승인 시 doctor_profiles.specialty로 복사
- license_file_url | VARCHAR(500) | NULL | // 면허 사본 파일 경로 (저장 위치 미정)
- status | ENUM('pending', 'approved', 'rejected') | NOT NULL | default='pending' | // 대기·승인·반려
- reject_reason | TEXT | NULL | // 반려 시 관리자가 입력
- reviewed_at | DATETIME | NULL | // 승인·반려한 시각
- created_at | DATETIME | NOT NULL | // 신청 시각

### emotion_analyses (감정분석)
- id | BIGINT | PK | NOT NULL | // uuid PK
- message_id | BIGINT | NOT NULL | FK→messages.id | // user 메시지
- model_version | VARCHAR(50) | NOT NULL | // 감정분석 모델 버전
- anger | DECIMAL(4, 3) | NOT NULL | // 분노 0~1
- joy | DECIMAL(4, 3) | NOT NULL | // 기쁨 0~1
- anxiety | DECIMAL(4, 3) | NOT NULL | // 불안 0~1
- embarrassment | DECIMAL(4, 3) | NOT NULL | // 당황 0~1
- sadness | DECIMAL(4, 3) | NOT NULL | // 슬픔 0~1
- hurt | DECIMAL(4, 3) | NOT NULL | // 상처 0~1
- dominant | ENUM('anger', 'joy', 'anxiety', 'embarrassment', 'sadness', 'hurt') | NOT NULL | // 최고 감정

### emotion_records (감정기록)
- emotion_id | BIGINT | PK | NOT NULL | // 감정 기록 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 회원 ID
- record_date | DATE | NOT NULL | // 체크인한 날. (user_id, record_date) UNIQUE
- mood_score | TINYINT | NOT NULL | // 기분 점수
- mood_tag | VARCHAR(20) | NULL | // 기분 태그
- memo | VARCHAR(255) | NULL | // 메모
- created_at | DATETIME | NOT NULL | // 작성 시각
- updated_at | DATETIME | NULL | // 수정 시각
- is_shared | BOOLEAN | NOT NULL | default=TRUE | // 기본값은 user_settings.share_report를 따름 (P6)
- deleted_at | DATETIME | NULL | // 삭제 시각

### exercise_records (운동기록)
- exercise_id | BIGINT | PK | NOT NULL | // 운동 기록 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 회원 ID
- record_date | DATETIME | NOT NULL | // 운동한 날
- exercise_type | VARCHAR(255) | NOT NULL | // 운동 종류
- duration_minutes | INT | NULL | // 운동 시간(분)
- memo | VARCHAR(255) | NULL | // 메모
- created_at | DATETIME | NOT NULL | // 작성 시각
- updated_at | DATETIME | NULL | // 수정 시각

### expressions (표정)
- expression_id | BIGINT | PK | NOT NULL | // 표정 ID
- condition_text | VARCHAR(255) | NULL | // 나오는 조건
- image_url | VARCHAR(255) | NULL | // 이미지 주소
- name | VARCHAR(30) | NOT NULL | // 표정 이름
- category | ENUM('mood', 'care', 'season') | NOT NULL | // mood = 기분(오늘의 기분 후보), care = 돌볼 때, season = 계절

### flowers (꽃)
- flower_id | BIGINT | PK | NOT NULL | // 꽃 ID
- flower_language | TEXT | NULL | // 꽃말
- image_url | VARCHAR(255) | NULL | // 이미지 주소
- flower_no | INT | NOT NULL | // 도감 번호
- name | VARCHAR(50) | NOT NULL | // 꽃 이름
- season | ENUM('spring', 'summer', 'autumn', 'winter') | NOT NULL | // 다음 꽃은 오늘 날짜의 계절 꽃 중에서 고름

### guard_checks (안전 필터 결과)
- id | BIGINT | PK | NOT NULL | // uuid PK
- message_id | BIGINT | NOT NULL | FK→messages.id | // 검사한 메시지
- gate | ENUM('a', 'b') | NOT NULL | // a=사용자 발화 검사, b=AI 답변 검사
- result | ENUM('pass', 'safe_mode', 'blocked') | NOT NULL | // 결과
- category | VARCHAR(50) | NULL | // 위험 유형
- model | VARCHAR(100) | NOT NULL | // 검사 모델
- original_text | TEXT | NULL | // gate b 차단 시만
- created_at | DATETIME | NOT NULL | // 검사 시각

### hospitals (병원)
- hospital_id | BIGINT | PK | NOT NULL | // 병원 ID
- name | VARCHAR(100) | NOT NULL | // 병원 이름
- phone | VARCHAR(20) | NULL | // 전화번호
- address | VARCHAR(255) | NOT NULL | // 주소
- sido | VARCHAR(20) | NOT NULL | // 시·도
- sigungu | VARCHAR(30) | NOT NULL | // 시·군·구
- latitude | DECIMAL(10, 7) | NULL | // 위도
- longitude | DECIMAL(10, 7) | NULL | // 경도
- is_accepting | BOOLEAN | NOT NULL | default=TRUE | // 요청 받기 여부
- created_at | DATETIME | NOT NULL | // 등록 시각
- updated_at | DATETIME | NULL | // 수정 시각

### items (아이템)
- item_id | BIGINT | PK | NOT NULL | // 아이템 ID
- name | VARCHAR(50) | NOT NULL | // 아이템 이름
- category | ENUM('outfit', 'accessory', 'furniture', 'background', 'snack', 'care') | NOT NULL | // snack = 간식(음식류 소모성), care = 씻기기 등 돌봄 소모품(값 이름 팀 확인)
- price | INT | NOT NULL | // 가격
- image_url | VARCHAR(255) | NULL | // 이미지 주소
- is_active | BOOLEAN | NOT NULL | default=TRUE | // 판매 여부
- created_at | DATETIME | NOT NULL | // 등록 시각
- ownership_type | ENUM('unique','stackable') | NOT NULL | // stackable = 개수가 쌓임(간식·돌봄 소모품), unique = 한 번만 구매(가구 등)
- description | VARCHAR(255) | NULL | // 설명
- season | ENUM('spring', 'summer', 'autumn', 'winter') | NULL | // 계절 아이템만. NULL이면 항상 판매
- exp_gain | INT | NULL | // 소모성 아이템의 사용 효과
- hunger_restore | TINYINT | NULL | // 사용 시 배고픔 회복
- dirtiness_restore | TINYINT | NULL | // 사용 시 꼬질함 감소
- unlock_level | INT | NULL | // 계정 레벨 기준(D8). 값은 E1 확인 필요
- daily_refill | INT | NULL | // 기본 제공 아이템만. 매일 자정 이후 첫 사용 때 이 개수까지 채움(쌓이지 않음)

### llm_calls (llm호출)
- id | BIGINT | PK | NOT NULL | // uuid PK
- message_id | BIGINT | NULL | FK→messages.id | // 이 호출이 설명하는 assistant 메시지. 장애·사후 요약은 null
- purpose | ENUM('reply', 'summary') | NOT NULL | // 호출 목적
- model | VARCHAR(100) | NOT NULL | // 모델
- prompt_version | VARCHAR(50) | NOT NULL | // 프롬프트 버전
- attempt | INT | NOT NULL | default=1 | // 재시도 회차
- parse_status | ENUM('ok', 'retried_ok', 'failed') | NOT NULL | // 구조화 출력 파싱·검증
- validation_errors | JSON | NULL | // 검증 실패 사유
- tokens_in | INT | NULL | // 입력 토큰
- tokens_out | INT | NULL | // 출력 토큰
- latency_ms | INT | NULL | // 지연
- status | VARCHAR(20) | NOT NULL | // 호출 상태
- error | TEXT | NULL | // 오류 내용

### messages (메시지)
- id | BIGINT | PK | NOT NULL | // uuid PK
- session_id | BIGINT | NOT NULL | FK→chat_sessions.id | // 소속 세션
- seq | INT | NOT NULL | // 세션 내 순번
- role | ENUM('user', 'assistant') | NOT NULL | // 발화자
- content | TEXT | NOT NULL | // 사용자 문장 또는 user_reply.text
- expression | VARCHAR(30) | NULL | // assistant만. 캐릭터 표정
- client_message_id | CHAR(36) | NULL | // 멱등성 키
- system_record_status | ENUM('ok', 'partial', 'failed') | NULL | // assistant만. system_record 검증 결과
- created_at | DATETIME | NOT NULL | // 생성 시각
- input_type | ENUM('text', 'voice') | NOT NULL | default='text' | // voice는 Whisper로 바꾼 글을 content에 저장

### missions (미션)
- mission_id | BIGINT | PK | NOT NULL | // 미션 ID
- name | VARCHAR(50) | NOT NULL | // 미션 이름
- mission_type | ENUM('daily_goal', 'all_clear_bonus', 'etc') | NOT NULL | // 미션 종류
- reward_point | INT | NOT NULL | // 보상 포인트
- daily_limit | TINYINT | NOT NULL | default=1 | // 하루 최대 횟수
- is_active | BOOLEAN | NOT NULL | default=TRUE | // 사용 여부
- sort_order | INT | NOT NULL | default=0 | // 표시 순서
- created_at | DATETIME | NOT NULL | // 등록 시각
- description | VARCHAR(255) | NULL | // 설명
- target_count | INT | NOT NULL | default=1 | // 목표 횟수
- category | ENUM('body', 'habit', 'mind') | NULL | // 일일목표 분류: body = 몸, habit = 습관, mind = 마음. 보너스 등 분류 없는 미션은 NULL

### notifications (알림)
- notification_id | BIGINT | PK | NOT NULL | // 알림 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 받는 회원 ID
- notification_type | ENUM('schedule', 'notice', 'system', 'request', 'appointment', 'chat', 'crisis') | NOT NULL | // 알림 종류
- title | VARCHAR(100) | NOT NULL | // 제목
- content | VARCHAR(255) | NULL | // 내용
- schedule_id | BIGINT | NULL | FK→schedules.schedule_id | // 관련 일정 ID
- sent_at | DATETIME | NULL | // 보낸 시각
- read_at | DATETIME | NULL | // 읽은 시각
- created_at | DATETIME | NOT NULL | // 생성 시각
- risk_event_id | BIGINT | NULL | FK→risk_events.id | // 관련 위험 이벤트
- request_id | BIGINT | NULL | FK→care_requests.request_id | // 관련 진료 요청
- appointment_id | BIGINT | NULL | FK→appointments.appointment_id | // 관련 예약

### patient_charts (환자 차트번호)
- id | BIGINT | PK | NOT NULL | // uuid PK
- patient_id | BIGINT | NOT NULL | FK→users.id | // 환자
- hospital_id | BIGINT | NOT NULL | FK→hospitals.hospital_id | // 병원
- chart_no | VARCHAR(20) | NOT NULL | // (hospital_id, chart_no) UNIQUE
- created_at | DATETIME | NOT NULL | // 등록 시각

### point_histories (포인트내역)
- history_id | BIGINT | PK | NOT NULL | // 내역 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 회원 ID
- history_type | ENUM('earn', 'spend', 'cancel') | NOT NULL | // 구분
- amount | INT | NOT NULL | // 포인트
- balance_after | INT | NOT NULL | // 처리 후 잔액
- mission_id | BIGINT | NULL | FK→missions.mission_id | // 획득 미션 ID
- item_id | BIGINT | NULL | FK→items.item_id | // 구매 아이템 ID
- reason | VARCHAR(50) | NULL | // 사유
- base_date | DATETIME | NOT NULL | // 기준 날짜
- created_at | DATETIME | NOT NULL | // 처리 시각

### rag_chunks (RAG chunk)
- id | BIGINT | PK | NOT NULL | // uuid PK
- document_id | BIGINT | NOT NULL | FK→rag_documents.id | // 원문 문서
- content | TEXT | NOT NULL | // 조각 본문
- embedding | BLOB | NOT NULL | // pgvector vector(N)
- metadata | JSON | NULL | // 메타데이터

### rag_documents (RAG문서)
- id | BIGINT | PK | NOT NULL | // uuid PK
- title | VARCHAR(200) | NOT NULL | // 문서 제목
- source | VARCHAR(500) | NULL | // 출처
- created_at | DATETIME | NOT NULL | // 등록 시각

### request_contacts (병원연락내역)
- contact_id | BIGINT | PK | NOT NULL | // 연락 ID
- request_id | BIGINT | NOT NULL | FK→care_requests.request_id | // 요청 ID
- hospital_id | BIGINT | NOT NULL | FK→hospitals.hospital_id | // 병원 ID
- responded_by | BIGINT | NULL | FK→users.id | // 응답한 의사 ID
- status | ENUM('sent', 'available', 'declined', 'no_response') | NOT NULL | // 응답 상태
- sent_at | DATETIME | NOT NULL | // 연락 보낸 시각
- responded_at | DATETIME | NULL | // 응답 시각

### request_messages (예약채팅)
- message_id | BIGINT | PK | NOT NULL | // 메시지 ID
- request_id | BIGINT | NOT NULL | FK→care_requests.request_id | // 요청 ID
- sender_id | BIGINT | NOT NULL | FK→users.id | // 보낸 회원 ID
- content | VARCHAR(1000) | NOT NULL | // 내용
- created_at | DATETIME | NOT NULL | // 보낸 시각
- read_at | DATETIME | NULL | // 읽은 시각

### risk_event_actions (위험 조치 이력)
- id | BIGINT | PK | NOT NULL | // uuid PK
- risk_event_id | BIGINT | NOT NULL | FK→risk_events.id | // 위험 이벤트
- actor_type | ENUM('ai', 'system', 'doctor') | NOT NULL | // 행위자 종류
- actor_id | BIGINT | NULL | FK→users.id | // doctor일 때만
- action | ENUM('safety_question', 'notify_doctor', 'review', 'hold', 'escalate', 'note') | NOT NULL | // 조치
- memo | VARCHAR(500) | NULL | // 조치 메모
- created_at | DATETIME | NOT NULL | // 수정·삭제 불가(append-only)

### risk_events (위험분석)
- id | BIGINT | PK | NOT NULL | // uuid PK
- message_id | BIGINT | NULL | FK→messages.id | // 발생 메시지
- level | ENUM('low', 'medium', 'high') | NOT NULL | // 위험 단계
- source | ENUM('rule', 'classifier', 'guard') | NOT NULL | // 누가 감지했나: classifier = F6 KcELECTRA, guard = 게이트 A, rule = 규칙(규칙 사전, 판단-15 기록 기반 감지)
- evidence | TEXT | NULL | // 근거 문장
- status | ENUM('open', 'reviewed', 'on_hold', 'escalated') | NOT NULL | default='open' | // 처리 상태
- user_id | BIGINT | NOT NULL | FK→users.id | // 환자
- origin | ENUM('chat', 'assessment', 'trend', 'inactive') | NOT NULL | default='chat' | // 어디서 나왔나: chat = AI 상담(필터), assessment = 자가검사 점수 급상승(규칙, 판단-15), trend·inactive = F5. origin_id는 assessment일 때 assessment_results.id
- origin_id | BIGINT | NULL | // chat 외 출처의 행 ID(diaries, assessment_results 등)
- category | VARCHAR(50) | NULL | // 예: 무망감·소진
- score | DECIMAL(4, 3) | NULL | // 모델 신뢰도
- model_version | VARCHAR(50) | NULL | // 모델·규칙 버전
- matched_terms | JSON | NULL | // 감지 표현
- context_judgement | TEXT | NULL | // 문맥 판단
- reviewed_by | BIGINT | NULL | FK→users.id | // 확인한 의사
- reviewed_at | DATETIME | NULL | // 확인 시각
- created_at | DATETIME | NOT NULL | // 감지 시각
- due_at | DATETIME | NULL | // 중간(medium) 판정이면 감지 시각 + 24시간. 의사 위기 알림 목록을 기한 순으로 보여 줄 때 씀
- is_repeated | BOOLEAN | NOT NULL | default=FALSE | // 같은 환자에게 같은 category가 최근 30일 안 3번째 이상. 저장할 때 정하고 바꾸지 않음
- is_uncertain | BOOLEAN | NOT NULL | default=FALSE | // 모델 점수 0.4~0.6 (임의 값). F6 점수 계산 방식 확정 후 조정

### rooms (진료실)
- id | BIGINT | PK | NOT NULL | // uuid PK
- hospital_id | BIGINT | NOT NULL | FK→hospitals.hospital_id | // 병원
- name | VARCHAR(30) | NOT NULL | // 진료실 이름
- room_type | ENUM('consult', 'exam') | NOT NULL | // consult=진료·상담실, exam=심리검사실
- is_active | BOOLEAN | NOT NULL | default=TRUE | // 사용 여부

### schedules (일정)
- schedule_id | BIGINT | PK | NOT NULL | // 일정 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 회원 ID
- created_by | BIGINT | NOT NULL | FK→users.id | // 등록자 ID
- schedule_type | ENUM('counseling', 'appointment', 'exam', 'notice', 'personal') | NOT NULL | // 일정 종류
- title | VARCHAR(100) | NOT NULL | // 제목
- memo | VARCHAR(255) | NULL | // 메모
- start_at | DATETIME | NOT NULL | // 시작 시각
- end_at | DATETIME | NULL | // 종료 시각
- remind_at | DATETIME | NULL | // 알림 시각
- appointment_id | BIGINT | NULL | FK→appointments.appointment_id | // 관련 예약 ID
- created_at | DATETIME | NOT NULL | // 생성 시각
- updated_at | DATETIME | NULL | // 수정 시각

### session_checklist (세션 체크리스트)
- id | BIGINT | PK | NOT NULL | // uuid PK
- session_id | BIGINT | NOT NULL | FK→chat_sessions.id | // 세션
- item_id | BIGINT | NOT NULL | FK→checklist_items.id | // 원본 항목
- required | BOOLEAN | NOT NULL | // 복사본
- sort_order | INT | NOT NULL | // 복사본
- status | ENUM('pending', 'done', 'skipped') | NOT NULL | default='pending' | // 진행 상태
- skip_reason | ENUM('user_declined', 'not_applicable', 'unclear') | NULL | // skipped일 때만
- value | JSON | NULL | // 채운 값
- evidence_message_id | BIGINT | NULL | FK→messages.id | // 근거 메시지. 실제 DB는 (session_id, evidence_message_id) 복합 FK로 같은 세션 보장
- ask_count | INT | NOT NULL | default=0 | // 질문 횟수

### session_documents (세션 내 상담문서)
- session_id | BIGINT | PK | NOT NULL | FK→chat_sessions.id | // 상담 세션
- document_id | BIGINT | PK | NOT NULL | FK→rag_documents.id | // 이 세션에서 검색할 RAG 문서

### session_summaries (세션 사후 요약)
- id | BIGINT | PK | NOT NULL | // uuid PK
- context_summary | TEXT | NOT NULL | // 세션 종료 후 1회 사후 요약
- mood_summary | JSON | NOT NULL | // dominant, distribution(6분류), intensity, evidence_seqs
- topics | JSON | NULL | // text
- created_at | DATETIME | NOT NULL | // 생성 시각
- session_id | BIGINT | NOT NULL | FK→chat_sessions.id | // 세션 ID. UNIQUE (세션 1개당 요약 1개)
- chief_complaint | TEXT | NULL | // 사전 문진 세션의 주호소 요약
- findings | JSON | NULL | // [{label, evidence}] 참고용. 진단 아님

### sleep_records (수면기록)
- sleep_id | BIGINT | PK | NOT NULL | // 수면 기록 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 회원 ID
- record_date | DATETIME | NOT NULL | // 기상한 날
- sleep_at | DATETIME | NULL | // 잠든 시각
- wake_at | DATETIME | NULL | // 일어난 시각
- sleep_minutes | INT | NULL | // 수면 시간(분)
- source | ENUM('manual', 'auto') | NOT NULL | // 입력 방식
- created_at | DATETIME | NOT NULL | // 작성 시각
- updated_at | DATETIME | NULL | // 수정 시각

### user_expressions (표정 앨범)
- user_id | BIGINT | PK | NOT NULL | FK→users.id | // 회원 ID
- expression_id | BIGINT | PK | NOT NULL | FK→expressions.expression_id | // 표정 ID
- first_seen_at | DATETIME | NOT NULL | // 처음 본 날
- seen_count | INT | NOT NULL | default=1 | // 본 횟수

### user_flowers (꽃 도감)
- user_flower_id | BIGINT | PK | NOT NULL | // 꽃 도감 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 회원 ID
- flower_id | BIGINT | NOT NULL | FK→flowers.flower_id | // (user_id, flower_id) UNIQUE. 다음 꽃: 지금 계절의 안 피운 꽃 → 없으면 다른 계절의 안 피운 꽃 중 랜덤
- bloomed_at | DATETIME | NOT NULL | // 만개한 날. 가장 최근 값 = 캐릭터 레벨 초기화일('함께한 날' 기준, D12)

### user_items (보유 아이템)
- user_item_id | BIGINT | PK | NOT NULL | // 보유 아이템 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // (user_id, item_id) UNIQUE
- item_id | BIGINT | NOT NULL | FK→items.item_id | // 아이템 ID
- quantity | INT | NOT NULL | default=1 | // unique 아이템은 항상 1. stackable은 사용하면 줄고 0이 돼도 줄은 남김(계절 도감)
- total_acquired | INT | NOT NULL | default=1 | // 모은 개수
- acquired_at | DATETIME | NOT NULL | // 처음 얻은 시각
- updated_at | DATETIME | NULL | // 수정 시각
- last_refilled_on | DATE | NULL | // 기본 제공 아이템만

### user_mission_logs (미션 수행 기록)
- log_id | BIGINT | PK | NOT NULL | // 기록 ID
- user_id | BIGINT | NOT NULL | FK→users.id | // 회원 ID
- mission_id | BIGINT | NOT NULL | FK→missions.mission_id | // 미션 ID
- log_date | DATE | NOT NULL | // (user_id, mission_id, log_date) UNIQUE. '하루' = 자정 기준(P5)
- progress_count | INT | NOT NULL | default=0 | // 진행 횟수
- completed_at | DATETIME | NULL | // 완료 시각
- canceled_at | DATETIME | NULL | // 취소 시각
- history_id | BIGINT | NULL | FK→point_histories.history_id | // 지급된 포인트 내역. 취소되면 canceled_at
- created_at | DATETIME | NOT NULL | // 생성 시각

### user_settings (사용자 설정)
- user_id | BIGINT | PK | NOT NULL | FK→users.id | // 회원 1명당 1줄, 가입 시 기본값으로 생성
- share_report | BOOLEAN | NOT NULL | default=TRUE | // 기록별 공개는 emotion_records.is_shared (P6)
- share_diary | BOOLEAN | NOT NULL | default=FALSE | // 일기 의사 공개
- diary_ai_consent | BOOLEAN | NOT NULL | default=FALSE | // 보안-03: 동의한 경우에만 일기 분석
- hide_stats | BOOLEAN | NOT NULL | default=FALSE | // 통계 숨기기
- consent_updated_at | DATETIME | NULL | // 동의 변경 시각
- updated_at | DATETIME | NULL | // 수정 시각

### users (사용자)
- id | BIGINT | PK | NOT NULL | // 회원 PK (BIGINT)
- email | VARCHAR(255) | NULL | // 로그인 이메일. 소셜 제공처가 주지 않을 수 있어 NULL 허용
- nickname | VARCHAR(50) | NULL | // 화면 표시용
- role | ENUM('patient', 'doctor') | NOT NULL | // 역할. 상담사(counselor)는 나중에 doctor와 같은 권한으로 추가할 수 있음
- created_at | DATETIME | NOT NULL | // 가입 시각
- social_provider | ENUM('kakao', 'naver', 'google') | NOT NULL | // 소셜 제공처
- social_id | VARCHAR(100) | NOT NULL | // 소셜 사용자 번호. (social_provider, social_id) UNIQUE
- name | VARCHAR(50) | NOT NULL | // 이름. 소셜 제공처가 준 이름. 주지 않으면 '익명유저'+회원 id(예: 익명유저1024), 본인이 수정 가능
- gender | ENUM('male', 'female') | NULL | // 성별
- birth_date | DATE | NULL | // 생년월일
- point_balance | INT | NOT NULL | default=0 | // 현재 포인트
- updated_at | DATETIME | NULL | // 수정 시각
- deleted_at | DATETIME | NULL | // 탈퇴 시각
- account_level | INT | NOT NULL | default=1 | // 계정 레벨, 상한 없음. account_exp 50마다 +1 (임의 값). 마이룸에서만 표시
- account_exp | INT | NOT NULL | default=0 | // 돌봄·간식으로 얻은 경험치 누적. 50마다 계정 레벨 +1 (임의 값)