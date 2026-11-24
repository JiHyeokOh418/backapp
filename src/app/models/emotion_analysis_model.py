from decimal import Decimal
from sqlalchemy import BigInteger, String, Numeric, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.common_enum import EmotionType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.message_model import Message

class EmotionAnalysis(Base):
    __tablename__ = "emotion_analyses"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )  # user 메시지
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)  # 감정분석 모델 버전
    anger: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # 분노 0~1
    joy: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # 기쁨 0~1
    anxiety: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # 불안 0~1
    embarrassment: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # 당황 0~1
    sadness: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # 슬픔 0~1
    hurt: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)  # 상처 0~1
    dominant: Mapped[EmotionType] = mapped_column(
        SQLEnum(EmotionType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 최고 감정

    # 관계
    message: Mapped["Message"] = relationship("Message", back_populates="emotion_analyses")
