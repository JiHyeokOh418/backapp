from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Text, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.guard_check_enum import GuardCheckGate, GuardCheckResult

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.message_model import Message

KST = timezone(timedelta(hours=9)) # UTC+9

class GuardCheck(Base):
    __tablename__ = "guard_checks"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )  # 검사한 메시지
    gate: Mapped[GuardCheckGate] = mapped_column(
        SQLEnum(GuardCheckGate, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # a=사용자 발화 검사, b=AI 답변 검사
    result: Mapped[GuardCheckResult] = mapped_column(
        SQLEnum(GuardCheckResult, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 결과
    category: Mapped[str | None] = mapped_column(String(50))  # 위험 유형
    model: Mapped[str] = mapped_column(String(100), nullable=False)  # 검사 모델
    original_text: Mapped[str | None] = mapped_column(Text)  # gate b 차단 시만
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 검사 시각

    # 관계
    message: Mapped["Message"] = relationship("Message", back_populates="guard_checks")
