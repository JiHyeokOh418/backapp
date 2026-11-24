from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, String, Numeric, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.common_enum import EmotionType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.diary_model import Diary

KST = timezone(timedelta(hours=9)) # UTC+9

class DiaryAnalysis(Base):
    __tablename__ = "diary_analyses"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    diary_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("diaries.diary_id", ondelete="CASCADE"), nullable=False
    )  # 일기
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)  # 모델 버전
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
    topics: Mapped[dict | None] = mapped_column(JSONB)  # 주제 키워드
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 분석 시각

    # 관계
    diary: Mapped["Diary"] = relationship("Diary", back_populates="analyses")
