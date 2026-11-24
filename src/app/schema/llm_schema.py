from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.enums.chat_session_enum import ChatSessionStatus, ChatSessionType, ChatExpression
from app.enums.message_enum import MessageRole, MessageInputType
from app.enums.session_checklist_enum import SessionChecklistSkipReason
from app.schema.common_schema import BaseDTO

KST = timezone(timedelta(hours=9)) # UTC+9


# ============================================================
# 1. LLM 출력 계약 (LLM <-> service)
# - structured outputs(output_format)에 그대로 넘기고, 응답을 이 모델로 파싱한다.
# - 프론트로 내려가는 DTO가 아니다. 체크리스트 값, evidence_seq 같은 내부 값이 들어 있다.
# - BaseDTO(camelCase)를 쓰지 않고 snake_case 그대로 쓴다.
# - extra="forbid": 정의하지 않은 속성이 오면 거절 (JSON Schema의 additionalProperties: false)
# - 기본값을 두지 않는다. LLM이 모든 속성을 반드시 채우게 하기 위함 (없는 값은 []/null/false로)
# ============================================================

# 체크리스트 항목 1건의 변경
# - status는 done / skipped만 보낸다. (pending으로 되돌리는 것은 허용하지 않는다)
# - 도메인 검사(item_id가 이 세션 항목인지, value가 answer_type에 맞는지, evidence_seq가 사용자 메시지인지)는 service가 한다.
class ChecklistChangeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(description="체크리스트 항목 id")
    status: Literal["done", "skipped"] = Field(description="done: 답을 받음, skipped: 건너뜀")
    value: str | int | float | bool | None = Field(description="사용자가 답한 값. skipped이면 null")
    skip_reason: SessionChecklistSkipReason | None = Field(description="skipped일 때만 사유, done이면 null")
    evidence_seq: int | None = Field(description="근거가 된 사용자 메시지의 seq")


# 한 턴에 대한 LLM 출력
class LlmReplyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reply_text: str = Field(description="사용자에게 보여줄 답변")
    expression: ChatExpression = Field(description="캐릭터 표정. 특별한 감정이 없으면 default")
    checklist_changes: list[ChecklistChangeOutput] = Field(description="이번 턴에 상태가 바뀐 항목. 없으면 빈 배열")
    asked_item_ids: list[int] = Field(description="이번 답변에서 질문한 체크리스트 항목 id. 없으면 빈 배열")
    counsel_end: bool = Field(description="체크리스트를 모두 채웠다고 판단하면 true. 최종 판단은 서버가 DB로 확인한다")
    end_reason: Literal["completed", "safety"] | None = Field(description="종료 요청일 때만 사유, 아니면 null")


# 세션 사후요약 LLM 출력 (session_summaries 1건)
# - 컬럼 형식은 session_summaries 모델을 따른다.
#   context_summary(text, 필수), mood_summary(JSONB, 필수), topics(JSONB), chief_complaint(text), findings(JSONB [{label, evidence}])
# - mood_summary = {dominant, distribution, intensity, evidence_seqs}
#   - dominant, distribution(6분류 평균)은 service가 emotion_analyses 점수로 직접 계산한다. LLM에게 받지 않는다.
#   - intensity, evidence_seqs만 LLM이 정한다. (아래 MoodOutput)
#   - 감정분석이 한 건도 없으면 mood는 null이어야 한다. (service가 한 번 더 강제한다)

# 감정 흐름에서 LLM이 정하는 값
# TODO: intensity 척도 확정 필요 (임시: 0~1 실수)
class MoodOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intensity: float = Field(ge=0, le=1, description="세션 전체 감정의 강도. 0(평온) ~ 1(매우 강함)")
    evidence_seqs: list[int] = Field(description="감정 판단의 근거가 된 사용자 메시지 seq 목록")


# AI 참고 소견 1건 (진단이 아님)
class FindingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="소견 이름")
    evidence: str = Field(description="근거 (대화 내용 요약)")


class LlmSummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_summary: str = Field(description="다음 세션에 넘길 상담 맥락 요약")
    mood: MoodOutput | None = Field(description="감정 강도와 근거 메시지. 감정분석 데이터가 없으면 null")
    topics: list[str] = Field(description="이번 세션에서 다룬 주제 키워드. 없으면 빈 배열")
    chief_complaint: str | None = Field(description="주호소 요약. 사전 문진(intake) 세션이 아니거나 없으면 null")
    findings: list[FindingOutput] = Field(description="AI 참고 소견 (진단이 아님). 없으면 빈 배열")


# ============================================================
# 2. 프론트 응답 DTO
# - LLM 출력 모델과 분리한다. 내부 값(체크리스트 값, evidence_seq 등)은 내려보내지 않는다.
# ============================================================

# 세션 1건 응답
class ChatSessionResponseDTO(BaseDTO):
    id: int
    status: ChatSessionStatus
    session_type: ChatSessionType
    scheduled_at: datetime | None = None
    expires_at: datetime | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None

    # 시각은 KST(+09:00)로 내려준다
    @field_serializer("scheduled_at", "expires_at", "started_at", "ended_at")
    def to_kst(self, value: datetime | None) -> datetime | None:
        return value.astimezone(KST) if value else None


# 상담 메인 응답 (진행 중 세션, 없으면 가장 가까운 예정 세션)
# - available: 지금 접속할 수 있는지 (진행 중이거나 scheduled_at이 지났고 마감 전)
class MainSessionResponseDTO(ChatSessionResponseDTO):
    available: bool


# 메시지 1건 응답
class MessageResponseDTO(BaseDTO):
    id: int
    seq: int
    role: MessageRole
    content: str
    expression: ChatExpression | None = None # 사용자 메시지는 None
    created_at: datetime

    @field_serializer("created_at")
    def to_kst(self, value: datetime) -> datetime:
        return value.astimezone(KST)


# 대화 기록 응답 (커서 방식)
# - next_cursor가 null이면 마지막 페이지
class MessageListResponseDTO(BaseDTO):
    items: list[MessageResponseDTO]
    next_cursor: int | None = None


# 메시지 전송 응답
# - session_status: 이번 턴에 세션이 종료됐는지 프론트가 알 수 있게 함께 내려준다.
class SendMessageResponseDTO(BaseDTO):
    message: MessageResponseDTO
    session_status: ChatSessionStatus


# ============================================================
# 3. 요청 DTO
# ============================================================

# 체크리스트 항목 선택 1건 (의사가 세션에 붙일 항목)
# - required: 필수 항목 여부 (세션 종료 판정에 쓰인다)
# - sort_order: 없으면 service가 요청 목록의 순서(1부터)로 채운다. (session_checklist.sort_order는 NOT NULL)
class ChecklistItemSelectDTO(BaseDTO):
    item_id: int
    required: bool = False
    sort_order: int | None = None


# 예정 세션 생성 요청 (한 번 호출에 세션 1건)
# - 시각은 타임존이 있는 값만 받는다. (KST/UTC 혼동 방지)
# - expires_at: 최초 접속 때 한 번 검증하는 마감 시각 (필수)
class ScheduledSessionCreateDTO(BaseDTO):
    user_id: int
    session_type: ChatSessionType = ChatSessionType.COUNSELING
    scheduled_at: datetime
    expires_at: datetime
    checklist_items: list[ChecklistItemSelectDTO] = Field(min_length=1)

    @field_validator("scheduled_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("타임존이 포함된 시각이어야 합니다.")
        return value

    @field_validator("checklist_items")
    @classmethod
    def no_duplicate_items(cls, value: list[ChecklistItemSelectDTO]) -> list[ChecklistItemSelectDTO]:
        item_ids = [item.item_id for item in value]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("체크리스트 항목이 중복되었습니다.")
        return value

    # 마감 시각 검증: 예정 시각보다 늦고, 이미 지난 시각이 아니어야 한다.
    @model_validator(mode="after")
    def check_period(self) -> "ScheduledSessionCreateDTO":
        if self.expires_at <= self.scheduled_at:
            raise ValueError("마감 시각은 예정 시각보다 늦어야 합니다.")
        if self.expires_at <= datetime.now(KST):
            raise ValueError("마감 시각이 이미 지났습니다.")
        return self


# 메시지 전송 요청
# - client_message_id: 중복 전송 방지용 (messages.client_message_id가 String(36))
class SendMessageRequestDTO(BaseDTO):
    client_message_id: str = Field(min_length=1, max_length=36)
    content: str = Field(max_length=2000) # TODO: 임시값. 확정 필요
    input_type: MessageInputType = MessageInputType.TEXT

    # 앞뒤 공백 제거, 빈 내용은 거절
    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("메시지 내용을 입력하세요.")
        return value
