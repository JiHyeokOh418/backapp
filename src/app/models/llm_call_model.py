from sqlalchemy import BigInteger, String, Text, Integer, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.llm_call_enum import LlmCallPurpose, LlmCallParseStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.message_model import Message

class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )  # 이 호출이 설명하는 assistant 메시지. 장애·사후 요약은 null
    purpose: Mapped[LlmCallPurpose] = mapped_column(
        SQLEnum(LlmCallPurpose, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 호출 목적
    model: Mapped[str] = mapped_column(String(100), nullable=False)  # 모델
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)  # 프롬프트 버전
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 재시도 회차
    parse_status: Mapped[LlmCallParseStatus] = mapped_column(
        SQLEnum(LlmCallParseStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 구조화 출력 파싱·검증
    validation_errors: Mapped[dict | None] = mapped_column(JSONB)  # 검증 실패 사유
    tokens_in: Mapped[int | None] = mapped_column(Integer)  # 입력 토큰
    tokens_out: Mapped[int | None] = mapped_column(Integer)  # 출력 토큰
    latency_ms: Mapped[int | None] = mapped_column(Integer)  # 지연(ms)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # 호출 상태
    error: Mapped[str | None] = mapped_column(Text)  # 오류 내용

    # 관계
    message: Mapped["Message | None"] = relationship("Message", back_populates="llm_calls")
