from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from pydantic import PlainSerializer, Field, field_validator, model_validator, AwareDatetime
from app.enums.appointment_enum import AppointmentStatus, AppointmentKind, AppointmentVisitType, AppointmentContactMethod
from app.enums.appointment_change_enum import AppointmentChangeType
from app.enums.common_enum import Instrument, EmotionType, ChecklistStatus, RequestedBy
from app.enums.room_enum import RoomType
from app.enums.risk_event_enum import RiskEventLevel, RiskEventStatus, RiskEventOrigin, RiskEventSource
from app.enums.risk_event_action_enum import RiskEventActionAction, RiskEventActionActorType
from app.enums.user_enum import UserGender
from app.enums.chat_session_enum import ChatSessionType, ChatSessionStatus, ChatSessionSummaryStatus, ChatSessionEndReason
from app.enums.message_enum import MessageRole
from app.enums.checklist_item_enum import ChecklistItemAnswerType
from app.enums.session_checklist_enum import SessionChecklistSkipReason
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
    gender: UserGender | None = None
    birth_date: date | None = None
    risk_level: RiskEventLevel | None = None             # 확인 안 한 알림 중 가장 높은 등급 (없으면 null)
    appointment: PatientAppointmentDTO | None = None  # 그날 예약 (없으면 null)


# 4. 오늘 예약 일정
class DoctorAppointmentResponseDTO(BaseDTO):
    appointment_id: int
    scheduled_at: KstDateTime
    end_at: KstDateTime | None = None
    patient: DoctorPatientBriefDTO
    visit_type: AppointmentVisitType | None = None
    kind: AppointmentKind
    contact_method: AppointmentContactMethod   # phone: 전화 / chat: 채팅
    room_id: int | None = None
    status: AppointmentStatus


# 5. 위험 환자 알림
class RiskEventResponseDTO(BaseDTO):
    id: int
    level: RiskEventLevel
    patient: DoctorPatientBriefDTO
    evidence: str | None = None     # 사유
    origin: RiskEventOrigin
    status: RiskEventStatus
    is_repeated: bool = False         # 같은 신호가 되풀이됨 (판단-05)
    is_uncertain: bool = False        # 판단이 확실하지 않음 (판단-06)
    due_at: KstDateTime | None = None  # 처리 기한 (medium: 감지 + 24시간)
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
    session_type: ChatSessionType          # counseling: 상담 / intake: 사전 문진
    status: ChatSessionStatus
    started_at: KstDateTime | None = None
    ended_at: KstDateTime | None = None
    summary_status: ChatSessionSummaryStatus | None = None  # 요약 상태 (요약을 만들기 전이면 null일 수 있음)
    preview: str | None = None         # 요약 앞부분 (session_summaries.context_summary)
    topics: dict | list | None = None  # 요약 태그
    has_risk: bool                     # 이 세션 대화에서 위험 감지가 있었는지


# ===== F-06 AI 상담 내역 팝업 (Figma: Doctor_detailCounsil) =====
# - 세션 목록은 PageResponseDTO[ChatRecordResponseDTO]를 그대로 쓴다.

# 세션 입력 방식: 환자 메시지가 모두 text / 모두 voice / 섞임 (임의 결정 D-43)
# - 상담 상세(F-06)와 설문 결과(F-03)에서 같이 쓴다.
SessionInputType = Literal["text", "voice", "mixed"]

# 메시지 1건의 감정 분석 (0~1 점수, dominant = 가장 강한 감정)
# - DB는 Numeric(Decimal)이지만 JSON에서 문자열이 되지 않도록 float로 내려준다.
class MessageEmotionDTO(BaseDTO):
    dominant: EmotionType
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
    risk_level: RiskEventLevel | None = None       # 이 메시지에서 위험이 감지됐으면 가장 높은 등급


# 세션 사후 요약
class ChatSummaryDTO(BaseDTO):
    context_summary: str | None = None
    mood_summary: dict | list | None = None
    topics: dict | list | None = None     # 요약 태그
    chief_complaint: str | None = None    # 주호소
    findings: dict | list | None = None   # AI 참고 소견


# 이전·다음 세션 링크 ("‹ 이전 세션 11.05")
class ChatSessionBriefDTO(BaseDTO):
    id: int
    started_at: KstDateTime


# 세션 감정 변화 ("불안 → 기쁨"): 감정 분석이 있는 첫 환자 메시지 -> 마지막 환자 메시지의 dominant
class EmotionChangeDTO(BaseDTO):
    start: EmotionType
    end: EmotionType


# 세션 상세 (세션 정보 + 요약·태그 + 감정 변화 + 대화 전문)
# - 감정 변화는 messages[].emotion을 순서대로 그리면 된다.
class ChatSessionDetailResponseDTO(BaseDTO):
    id: int
    patient: DoctorPatientBriefDTO
    session_type: ChatSessionType
    status: ChatSessionStatus
    end_reason: ChatSessionEndReason | None = None
    started_at: KstDateTime | None = None
    ended_at: KstDateTime | None = None
    summary_status: ChatSessionSummaryStatus | None = None
    summary: ChatSummaryDTO | None = None
    messages: list[ChatMessageResponseDTO]
    session_code: str                       # 세션 번호 "A-MMDD" (임의 결정 D-41)
    duration_minutes: int | None = None     # 소요 시간(분, 버림). 시작·종료 중 하나라도 없으면 null
    prev_session: ChatSessionBriefDTO | None = None  # 같은 환자·같은 종류의 바로 앞 세션 (임의 결정 D-42)
    next_session: ChatSessionBriefDTO | None = None  # 바로 뒤 세션
    input_type: SessionInputType | None = None       # 환자 메시지가 없으면 null (임의 결정 D-43)
    emotion_change: EmotionChangeDTO | None = None   # 분석된 환자 메시지가 1개 이하면 null
    risk_count: int = 0                              # 이 세션 메시지에서 감지된 위험 알림 수
    max_risk_level: RiskEventLevel | None = None     # 그중 가장 높은 등급 (없으면 null)
    turn_count: int = 0                              # 환자 메시지 수 (환자 1 + AI 1 = 1턴, 임의 결정 D-44)


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
    actor_type: RiskEventActionActorType           # ai / system / doctor
    actor_id: int | None = None
    actor_name: str | None = None   # 의사가 한 조치면 의사 이름
    action: RiskEventActionAction
    memo: str | None = None
    created_at: KstDateTime


# 이전 유사 기록 ("최근 30일 유사 표현 1회 (10.17 "…")", 임의 결정 D-48)
class RiskSimilarHistoryDTO(BaseDTO):
    count: int                              # 최근 30일 같은 category(없으면 같은 origin) 알림 수 (이 알림 제외)
    latest_id: int | None = None            # 그중 가장 최근 알림
    latest_at: KstDateTime | None = None
    latest_evidence: str | None = None


# 감지 상세
class RiskEventDetailResponseDTO(BaseDTO):
    id: int
    patient: DoctorPatientBriefDTO
    level: RiskEventLevel
    status: RiskEventStatus
    source: RiskEventSource                      # rule / llm / emotion / classifier / guard
    origin: RiskEventOrigin                      # chat / diary / assessment / trend / inactive
    category: str | None = None
    score: float | None = None
    evidence: str | None = None             # 사유
    matched_terms: dict | list | None = None  # 걸린 단어
    context_judgement: str | None = None    # AI 문맥 판단
    model_version: str | None = None
    is_repeated: bool = False
    is_uncertain: bool = False
    due_at: KstDateTime | None = None
    created_at: KstDateTime
    reviewed_at: KstDateTime | None = None
    session_id: int | None = None           # 대화에서 감지됐으면 그 세션 (상담 내역 팝업으로 이동용)
    context: list[RiskContextMessageDTO]    # 앞뒤 6개 메시지 (대화가 아니면 빈 목록)
    actions: list[RiskEventActionResponseDTO]  # 조치 이력 (오래된 순)
    session_code: str | None = None         # 출처 "AI 상담 · 세션 #A-1022" (대화가 아니면 null, 임의 결정 D-41)
    doctor_name: str | None = None          # 지금 담당 의사 (여러 명이면 담당 시작이 가장 이른 1명, 임의 결정 D-47)
    similar_history: RiskSimilarHistoryDTO = RiskSimilarHistoryDTO(count=0)  # 이전 유사 기록


# 조치 기록 추가 요청
# - note: 메모만 남김 (상태 그대로)
# - hold: 보류 (open -> on_hold)
# - escalate: 위기 대응으로 올림 (open·reviewed·on_hold -> escalated)
# - 확인(review)은 POST /risk-events/{id}/review
class RiskEventActionCreateDTO(BaseDTO):
    action: Literal[RiskEventActionAction.NOTE, RiskEventActionAction.HOLD, RiskEventActionAction.ESCALATE]
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
        if self.action == RiskEventActionAction.NOTE and not self.memo:
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
    top_emotion: EmotionType | None = None    # AI 상담 대화에서 가장 많이 나온 감정
    joy_ratio: float | None = None        # AI 상담 감정 분석 중 joy 비율 (0~1, 소수 3자리). 분석이 없으면 null
    joy_change: float | None = None       # 직전 같은 길이 기간 joy_ratio와의 차이 (0.07 -> "▲ 7%p")


# 일별 기분 (감정 기록 체크인)
class DailyMoodDTO(BaseDTO):
    date: date
    mood_score: int
    mood_tag: str | None = None


# 주별 감정 비율 (AI 상담 대화의 환자 메시지 감정 분석, 기간 첫날부터 7일씩 - 임의 결정 D-46)
class WeeklyEmotionDTO(BaseDTO):
    week_start: date
    total: int                       # 그 주 분석된 메시지 수 (없는 주도 0으로 들어간다)
    ratios: dict[EmotionType, float]     # 감정별 비율 (합 1.0, total 0이면 모두 0)


# 키워드 (기분 태그 빈도)
class EmotionKeywordDTO(BaseDTO):
    keyword: str
    count: int


# 시간대별 기록 수
class TimeSlotCountDTO(BaseDTO):
    slot: Literal["dawn", "morning", "afternoon", "evening"]  # 0~6 / 6~12 / 12~18 / 18~24시
    count: int


# 그래프의 진료일 점선 ("진료일 · PHQ-9")
class VisitMarkerDTO(BaseDTO):
    date: date
    appointment_id: int
    phq9_score: int | None = None      # 그날(KST) 가장 늦은 PHQ-9 (없으면 null)
    phq9_severity: str | None = None


# 감정 리포트
class EmotionReportResponseDTO(BaseDTO):
    patient_id: int
    patient: DoctorPatientBriefDTO      # 부제 "김민준 · 2026.10.15 – 11.11"
    period: Literal["week", "month", "3months"]  # week 7일 / month 28일 / 3months 84일 (임의 결정 D-45)
    start_date: date    # 기간 첫날
    end_date: date      # 기간 마지막 날 (포함)
    summary: EmotionSummaryDTO
    daily_moods: list[DailyMoodDTO]
    weekly_emotions: list[WeeklyEmotionDTO]
    keywords: list[EmotionKeywordDTO]   # 많이 쓴 순 최대 10개
    time_slots: list[TimeSlotCountDTO]
    visit_markers: list[VisitMarkerDTO] = []   # 기간 안 내 진료(completed) 날짜순


# ===== F-03 설문조사 결과 팝업 (Figma: Doctor_detailsurvey) =====
# - 사전 문진 = session_type이 intake인 상담 세션 (임의 결정 D-18~D-20)

# 척도 점수 카드 1장 (그 문진에서 측정 안 됐으면 점수 null)
class IntakeScoreDTO(BaseDTO):
    instrument: Instrument
    total_score: int | None = None
    severity: str | None = None
    assessed_at: KstDateTime | None = None
    max_score: int                          # 만점 ("19 / 27점"), 결과가 없는 카드에도 넣는다


# 문항별 응답 1줄
class IntakeAnswerDTO(BaseDTO):
    item_key: str
    label: str                              # 문항 이름
    instrument: Instrument | None = None    # 척도 문항이면 척도 (일반 문진 문항이면 null)
    item_no: int | None = None              # 척도 문항 번호
    answer_type: ChecklistItemAnswerType
    options: dict | list | None = None      # 보기
    required: bool
    status: ChecklistStatus                 # pending: 안 물어봄 / done: 답함 / skipped: 건너뜀
    skip_reason: SessionChecklistSkipReason | None = None
    value: dict | list | int | float | str | bool | None = None  # 답 (JSONB 그대로)
    score: int | None = None                # 척도 문항 점수 (done일 때만, 일반 문항은 null, 임의 결정 D-50)


# 설문 결과 부제의 환자 정보 ("남 23세 · 113912")
class IntakePatientInfoDTO(BaseDTO):
    gender: UserGender | None = None
    birth_date: date | None = None
    age: int | None = None                  # 만 나이 (올해 생일 전이면 1 뺀다), 생년월일이 없으면 null
    chart_no: str | None = None             # 내 병원 차트번호 (없으면 null)


# 다른 문진으로 바꿔 보기 위한 목록 1건
class IntakeSessionBriefDTO(BaseDTO):
    id: int
    status: ChatSessionStatus
    started_at: KstDateTime | None = None


# 사전 문진 결과
class IntakeResultResponseDTO(BaseDTO):
    patient: DoctorPatientBriefDTO
    session_id: int
    status: ChatSessionStatus
    started_at: KstDateTime | None = None
    ended_at: KstDateTime | None = None
    scores: list[IntakeScoreDTO]            # phq9, gad7, isi 순서로 항상 3장
    answers: list[IntakeAnswerDTO]
    chief_complaint: str | None = None      # 주호소
    findings: dict | list | None = None     # AI 참고 소견
    context_summary: str | None = None
    history: list[IntakeSessionBriefDTO]    # 이 환자의 문진 목록 (최신순 최대 10개)
    patient_info: IntakePatientInfoDTO = IntakePatientInfoDTO()
    input_type: SessionInputType | None = None   # 환자 메시지 기준 (임의 결정 D-43)
    duration_minutes: int | None = None          # 소요 시간(분, 버림)
    completion_rate: int = 100                   # 필수 문항 중 done 비율 0~100 (임의 결정 D-49)


# ===== F-07 예약 일정 팝업 (Figma: Doctor_DetailReservation) =====
# - 임의 결정 D-21~D-28

# 예약 변경 이력 1건
class AppointmentChangeResponseDTO(BaseDTO):
    id: int
    change_type: AppointmentChangeType          # reschedule: 일정 변경 / cancel: 취소
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


# 다음 예약 (팝업 제목 아래 "다음 예약 D-13")
class NextAppointmentDTO(BaseDTO):
    appointment_id: int
    scheduled_at: KstDateTime
    d_day: int               # 예약 날짜 - 오늘 (KST 날짜 기준, 오늘이면 0)


# 환자별 예약 (월)
class PatientAppointmentsResponseDTO(BaseDTO):
    patient: DoctorPatientBriefDTO
    month: str
    reschedule_count: int    # 일정 변경 횟수 (전체 기간)
    cancel_count: int        # 취소 횟수 (전체 기간)
    no_show_count: int       # 노쇼 횟수 (전체 기간)
    items: list[AppointmentDetailResponseDTO]  # 그 달 예약 (취소 포함, 시각순)
    next_appointment: NextAppointmentDTO | None = None  # 지금 이후 가장 이른 booked·waiting 예약 (month와 무관)


# 예약 추가 요청 (시각은 +09:00 같은 시간대를 꼭 붙인다)
class AppointmentCreateDTO(BaseDTO):
    patient_id: int
    scheduled_at: AwareDatetime
    end_at: AwareDatetime | None = None      # 없으면 시작 + 30분 (임의 결정 D-22)
    kind: AppointmentKind = AppointmentKind.TREATMENT
    contact_method: AppointmentContactMethod = AppointmentContactMethod.PHONE  # 없으면 전화 (임의 결정 D-29)
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
