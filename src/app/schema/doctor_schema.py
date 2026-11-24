from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from pydantic import PlainSerializer, Field, field_validator, model_validator, AwareDatetime
from app.enum.appointment_enum import AppointmentStatus, AppointmentKind, VisitType, ChangeType, RequestedBy
from app.enum.hospital_enum import RoomType
from app.enum.risk_enum import RiskLevel, RiskStatus, RiskOrigin, RiskSource, RiskAction, ActorType
from app.enum.user_enum import Gender
from app.enum.common_enum import Instrument, Emotion
from app.enum.chat_enum import SessionType, SessionStatus, SummaryStatus, SessionEndReason, MessageRole
from app.enum.checklist_enum import AnswerType, ChecklistStatus, SkipReason
from app.schema.common_schema import BaseDTO

KST = timezone(timedelta(hours=9)) # UTC+9

# 시각은 KST(+09:00)로 내려준다 (필드 타입으로 붙이면 직렬화할 때 자동 변환)
KstDateTime = Annotated[datetime, PlainSerializer(lambda v: v.astimezone(KST), return_type=datetime)]


# 응답 안에 들어가는 환자 요약 (이름 표시용)
class DoctorPatientBriefDTO(BaseDTO):
    id: int
    name: str | None = None


# 1. 상단 요약 바
class DashboardSummaryResponseDTO(BaseDTO):
    date: date
    today_count: int        # 오늘 예약 (취소 제외)
    completed_count: int    # 진료 완료
    waiting_count: int      # 대기 중
    open_risk_count: int    # 확인 안 한 위험 알림


# 2. 진료실
class RoomResponseDTO(BaseDTO):
    id: int
    name: str
    room_type: RoomType


# 3. 환자 목록 - 그날 예약
class PatientAppointmentDTO(BaseDTO):
    appointment_id: int
    scheduled_at: KstDateTime
    status: AppointmentStatus


# 3. 환자 목록 - 1행
class DoctorPatientResponseDTO(BaseDTO):
    id: int
    name: str | None = None
    gender: Gender | None = None
    birth_date: date | None = None
    risk_level: RiskLevel | None = None             # 확인 안 한 알림 중 가장 높은 등급 (없으면 null)
    appointment: PatientAppointmentDTO | None = None  # 그날 예약 (없으면 null)


# 4. 오늘 예약 일정
class DoctorAppointmentResponseDTO(BaseDTO):
    appointment_id: int
    scheduled_at: KstDateTime
    end_at: KstDateTime | None = None
    patient: DoctorPatientBriefDTO
    visit_type: VisitType | None = None
    kind: AppointmentKind
    room_id: int | None = None
    status: AppointmentStatus


# 5. 위험 환자 알림
class RiskEventResponseDTO(BaseDTO):
    id: int
    level: RiskLevel
    patient: DoctorPatientBriefDTO
    evidence: str | None = None     # 사유
    origin: RiskOrigin
    status: RiskStatus
    created_at: KstDateTime
    reviewed_at: KstDateTime | None = None


# 6. 월 캘린더 - 하루
class CalendarDayDTO(BaseDTO):
    date: date
    treatment_count: int     # 상담(진료)
    psych_test_count: int    # 검사


# 6. 월 캘린더
class CalendarResponseDTO(BaseDTO):
    month: str  # 2026-11
    days: list[CalendarDayDTO]  # 예약이 있는 날만


# ===== 2단계: 환자를 고르면 바뀌는 위젯 =====

# 7. 경과 그래프 - 측정 1회
class AssessmentPointDTO(BaseDTO):
    assessed_at: KstDateTime
    total_score: int
    severity: str | None = None


# 7. 경과 그래프
# - points: 기간 안의 측정 (오래된 순, 그래프 x축 순서)
# - latest / previous: 마지막 측정과 그 직전 측정 -> "단계 변화"(예: 중등도 -> 경도, -4점) 표시용
class AssessmentTrendResponseDTO(BaseDTO):
    patient_id: int
    instrument: Instrument
    months: int
    points: list[AssessmentPointDTO]
    latest: AssessmentPointDTO | None = None
    previous: AssessmentPointDTO | None = None


# 8. AI 상담 기록 위젯 - 세션 1건
class ChatRecordResponseDTO(BaseDTO):
    id: int
    session_type: SessionType          # counselling: 상담 / intake: 사전 문진
    status: SessionStatus
    started_at: KstDateTime | None = None
    ended_at: KstDateTime | None = None
    summary_status: SummaryStatus      # 요약이 아직 없으면 pending
    preview: str | None = None         # 요약 앞부분 (session_summaries.context_summary)
    topics: dict | list | None = None  # 요약 태그
    has_risk: bool                     # 이 세션 대화에서 위험 감지가 있었는지


# ===== F-06 AI 상담 내역 팝업 (Figma: Doctor_detailCounsil) =====
# - 세션 목록은 PageResponseDTO[ChatRecordResponseDTO]를 그대로 쓴다.

# 메시지 1건의 감정 분석 (0~1 점수, dominant = 가장 강한 감정)
# - DB는 Numeric(Decimal)이지만 JSON에서 문자열이 되지 않도록 float로 내려준다.
class MessageEmotionDTO(BaseDTO):
    dominant: Emotion
    anger: float
    joy: float
    anxiety: float
    embarrassment: float
    sadness: float
    hurt: float


# 대화 1줄
class ChatMessageResponseDTO(BaseDTO):
    id: int
    seq: int
    role: MessageRole                     # user: 환자 / assistant: AI
    content: str
    created_at: KstDateTime
    emotion: MessageEmotionDTO | None = None  # 감정 분석이 없으면 null
    risk_level: RiskLevel | None = None       # 이 메시지에서 위험이 감지됐으면 가장 높은 등급


# 세션 사후 요약
class ChatSummaryDTO(BaseDTO):
    context_summary: str | None = None
    mood_summary: dict | list | None = None
    topics: dict | list | None = None     # 요약 태그
    chief_complaint: str | None = None    # 주호소
    findings: dict | list | None = None   # AI 참고 소견


# 세션 상세 (세션 정보 + 요약·태그 + 감정 변화 + 대화 전문)
# - 감정 변화는 messages[].emotion을 순서대로 그리면 된다.
class ChatSessionDetailResponseDTO(BaseDTO):
    id: int
    patient: DoctorPatientBriefDTO
    session_type: SessionType
    status: SessionStatus
    end_reason: SessionEndReason | None = None
    started_at: KstDateTime | None = None
    ended_at: KstDateTime | None = None
    summary_status: SummaryStatus
    summary: ChatSummaryDTO | None = None
    messages: list[ChatMessageResponseDTO]


# ===== F-05 위험 감지 상세 팝업 (Figma: Doctor_detailRisk) =====
# - 환자별 감지 목록은 RiskEventResponseDTO 목록을 그대로 쓴다.

# 감지된 메시지 앞뒤 대화 1줄
class RiskContextMessageDTO(BaseDTO):
    id: int
    seq: int
    role: MessageRole
    content: str
    created_at: KstDateTime
    is_trigger: bool    # 위험이 감지된 바로 그 메시지면 true (빨간 강조)


# 조치 이력 1건
class RiskEventActionResponseDTO(BaseDTO):
    id: int
    actor_type: ActorType           # ai / system / doctor
    actor_id: int | None = None
    actor_name: str | None = None   # 의사가 한 조치면 의사 이름
    action: RiskAction
    memo: str | None = None
    created_at: KstDateTime


# 감지 상세
class RiskEventDetailResponseDTO(BaseDTO):
    id: int
    patient: DoctorPatientBriefDTO
    level: RiskLevel
    status: RiskStatus
    source: RiskSource                      # rule / llm / emotion / classifier / guard
    origin: RiskOrigin                      # chat / diary / assessment / trend / inactive
    category: str | None = None
    score: float | None = None
    evidence: str | None = None             # 사유
    matched_terms: dict | list | None = None  # 걸린 단어
    context_judgement: str | None = None    # AI 문맥 판단
    model_version: str | None = None
    created_at: KstDateTime
    reviewed_at: KstDateTime | None = None
    session_id: int | None = None           # 대화에서 감지됐으면 그 세션 (상담 내역 팝업으로 이동용)
    context: list[RiskContextMessageDTO]    # 앞뒤 6개 메시지 (대화가 아니면 빈 목록)
    actions: list[RiskEventActionResponseDTO]  # 조치 이력 (오래된 순)


# 조치 기록 추가 요청
# - note: 메모만 남김 (상태 그대로, "보류"도 이것으로 남긴다)
# - escalate: 위기 대응으로 올림 (상태 -> escalated)
class RiskEventActionCreateDTO(BaseDTO):
    action: Literal[RiskAction.NOTE, RiskAction.ESCALATE]
    memo: str | None = Field(default=None, max_length=500)

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None  # 공백만 보내면 메모 없음

    # note는 메모가 꼭 있어야 한다.
    @model_validator(mode="after")
    def require_memo_for_note(self):
        if self.action == RiskAction.NOTE and not self.memo:
            raise ValueError("메모를 입력하세요.")
        return self


# ===== F-04 감정 그래프 팝업 (Figma: Doctor_detailmind) =====
# - 임의 결정 D-13~D-17 (reference/의사웹_백엔드_임의결정_2026-11-24.md)

# 요약 4칸
class EmotionSummaryDTO(BaseDTO):
    avg_mood_score: float | None = None   # 기간 평균 기분 점수 (1~5)
    mood_change: float | None = None      # 직전 같은 길이 기간 평균과의 차이 (+면 좋아짐)
    recorded_days: int                    # 감정 기록이 있는 날 수
    total_days: int                       # 기간 일수
    top_emotion: Emotion | None = None    # AI 상담 대화에서 가장 많이 나온 감정


# 일별 기분 (감정 기록 체크인)
class DailyMoodDTO(BaseDTO):
    date: date
    mood_score: int
    mood_tag: str | None = None


# 주별 감정 비율 (AI 상담 대화의 환자 메시지 감정 분석, 월요일 시작 주)
class WeeklyEmotionDTO(BaseDTO):
    week_start: date
    total: int                       # 그 주 분석된 메시지 수
    ratios: dict[Emotion, float]     # 감정별 비율 (합 1.0)


# 키워드 (기분 태그 빈도)
class EmotionKeywordDTO(BaseDTO):
    keyword: str
    count: int


# 시간대별 기록 수
class TimeSlotCountDTO(BaseDTO):
    slot: Literal["dawn", "morning", "afternoon", "evening"]  # 0~6 / 6~12 / 12~18 / 18~24시
    count: int


# 감정 리포트
class EmotionReportResponseDTO(BaseDTO):
    patient_id: int
    period: Literal["week", "month", "3months"]
    start_date: date    # 기간 첫날
    end_date: date      # 기간 마지막 날 (포함)
    summary: EmotionSummaryDTO
    daily_moods: list[DailyMoodDTO]
    weekly_emotions: list[WeeklyEmotionDTO]
    keywords: list[EmotionKeywordDTO]   # 많이 쓴 순 최대 10개
    time_slots: list[TimeSlotCountDTO]


# ===== F-03 설문조사 결과 팝업 (Figma: Doctor_detailsurvey) =====
# - 사전 문진 = session_type이 intake인 상담 세션 (임의 결정 D-18~D-20)

# 척도 점수 카드 1장 (그 문진에서 측정 안 됐으면 점수 null)
class IntakeScoreDTO(BaseDTO):
    instrument: Instrument
    total_score: int | None = None
    severity: str | None = None
    assessed_at: KstDateTime | None = None


# 문항별 응답 1줄
class IntakeAnswerDTO(BaseDTO):
    item_key: str
    label: str                              # 문항 이름
    instrument: Instrument | None = None    # 척도 문항이면 척도 (일반 문진 문항이면 null)
    item_no: int | None = None              # 척도 문항 번호
    answer_type: AnswerType
    options: dict | list | None = None      # 보기
    required: bool
    status: ChecklistStatus                 # pending: 안 물어봄 / done: 답함 / skipped: 건너뜀
    skip_reason: SkipReason | None = None
    value: dict | list | int | float | str | bool | None = None  # 답 (JSONB 그대로)


# 다른 문진으로 바꿔 보기 위한 목록 1건
class IntakeSessionBriefDTO(BaseDTO):
    id: int
    status: SessionStatus
    started_at: KstDateTime | None = None


# 사전 문진 결과
class IntakeResultResponseDTO(BaseDTO):
    patient: DoctorPatientBriefDTO
    session_id: int
    status: SessionStatus
    started_at: KstDateTime | None = None
    ended_at: KstDateTime | None = None
    scores: list[IntakeScoreDTO]            # phq9, gad7, isi 순서로 항상 3장
    answers: list[IntakeAnswerDTO]
    chief_complaint: str | None = None      # 주호소
    findings: dict | list | None = None     # AI 참고 소견
    context_summary: str | None = None
    history: list[IntakeSessionBriefDTO]    # 이 환자의 문진 목록 (최신순 최대 10개)


# ===== F-07 예약 일정 팝업 (Figma: Doctor_DetailReservation) =====
# - 임의 결정 D-21~D-28

# 예약 변경 이력 1건
class AppointmentChangeResponseDTO(BaseDTO):
    id: int
    change_type: ChangeType          # reschedule: 일정 변경 / cancel: 취소
    from_at: KstDateTime | None = None
    to_at: KstDateTime | None = None
    reason: str | None = None
    requested_by: RequestedBy        # patient / doctor
    changed_by: int | None = None
    created_at: KstDateTime


# 예약 1건 (팝업용: 오늘 예약 일정 항목 + 검사·메모·변경 이력)
class AppointmentDetailResponseDTO(DoctorAppointmentResponseDTO):
    tests: dict | list | None = None
    patient_note: str | None = None
    completed_at: KstDateTime | None = None
    changes: list[AppointmentChangeResponseDTO]   # 오래된 순


# 환자별 예약 (월)
class PatientAppointmentsResponseDTO(BaseDTO):
    patient: DoctorPatientBriefDTO
    month: str
    reschedule_count: int    # 일정 변경 횟수 (전체 기간)
    cancel_count: int        # 취소 횟수 (전체 기간)
    no_show_count: int       # 노쇼 횟수 (전체 기간)
    items: list[AppointmentDetailResponseDTO]  # 그 달 예약 (취소 포함, 시각순)


# 예약 추가 요청 (시각은 +09:00 같은 시간대를 꼭 붙인다)
class AppointmentCreateDTO(BaseDTO):
    patient_id: int
    scheduled_at: AwareDatetime
    end_at: AwareDatetime | None = None      # 없으면 시작 + 30분 (임의 결정 D-22)
    kind: AppointmentKind = AppointmentKind.TREATMENT
    room_id: int | None = None
    tests: list[str] | None = None           # 검사 목록 (예: ["phq9", "gad7"])


# 일정 변경 요청
class AppointmentRescheduleDTO(BaseDTO):
    scheduled_at: AwareDatetime
    end_at: AwareDatetime | None = None      # 없으면 원래 길이 유지
    reason: str | None = Field(default=None, max_length=100)


# 예약 취소 요청
class AppointmentCancelDTO(BaseDTO):
    reason: str | None = Field(default=None, max_length=100)


# 진료 상태 변경 요청
class AppointmentStatusUpdateDTO(BaseDTO):
    status: Literal[
        AppointmentStatus.WAITING, AppointmentStatus.IN_PROGRESS,
        AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW
    ]
