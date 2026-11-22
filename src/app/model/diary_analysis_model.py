from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, String, Numeric, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.common_enum import Emotion

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.diary_model import Diary

KST = timezone(timedelta(hours=9)) # UTC+9

# 일기 분석 (diaries와 1:1)
class DiaryAnalysis(Base):
    __tablename__ = "diary_analyses"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    diary_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("diaries.diary_id", ondelete="CASCADE"), nullable=False, unique=True
    )
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
    topics: Mapped[dict | list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    diary: Mapped["Diary"] = relationship("Diary", back_populates="analysis")
