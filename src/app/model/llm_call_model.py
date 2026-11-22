from datetime import timedelta, timezone
from sqlalchemy import BigInteger, String, Text, Integer, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.chat_enum import LlmPurpose, ParseStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.message_model import Message

KST = timezone(timedelta(hours=9)) # UTC+9

# llm호출
class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[LlmPurpose] = mapped_column(
        SQLEnum(LlmPurpose, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parse_status: Mapped[ParseStatus | None] = mapped_column(
        SQLEnum(ParseStatus, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    validation_errors: Mapped[dict | list | None] = mapped_column(JSONB)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text)

    # 관계
    message: Mapped["Message"] = relationship("Message", back_populates="llm_calls")
