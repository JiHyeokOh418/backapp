import uuid
from datetime import timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, String, Numeric, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.common_enum import Emotion

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.message_model import Message

KST = timezone(timedelta(hours=9)) # UTC+9

# 감정분석
class EmotionAnalysis(Base):
    __tablename__ = "emotion_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    ) # ERD: CHAR(36) -> 참조 PK에 맞춰 BIGINT로 변경
    model_version: Mapped[str | None] = mapped_column(String(50))
    anger: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    joy: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    anxiety: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    embarrassment: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    sadness: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    hurt: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    dominant: Mapped[Emotion] = mapped_column(
        SQLEnum(Emotion, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )

    # 관계
    message: Mapped["Message"] = relationship("Message", back_populates="emotion_analyses")
