from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Text, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.chat_enum import GuardGate, GuardResult

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.message_model import Message

KST = timezone(timedelta(hours=9)) # UTC+9

# 안전 필터 결과
class GuardCheck(Base):
    __tablename__ = "guard_checks"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gate: Mapped[GuardGate] = mapped_column(
        SQLEnum(GuardGate, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    result: Mapped[GuardResult] = mapped_column(
        SQLEnum(GuardResult, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    category: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    original_text: Mapped[str | None] = mapped_column(Text) # 차단된 원래 답변
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    message: Mapped["Message"] = relationship("Message", back_populates="guard_checks")
