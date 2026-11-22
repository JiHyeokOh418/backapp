from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, Numeric, DateTime, Identity, ForeignKey, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.risk_enum import TrendFlag

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

# 일별 위험 점수
class DailyRiskScore(Base):
    __tablename__ = "daily_risk_scores"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    base_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    trend_flag: Mapped[TrendFlag] = mapped_column(
        SQLEnum(TrendFlag, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=TrendFlag.NONE
    )
    detail: Mapped[dict | list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "base_date", name="uq_daily_risk_scores_user_id_base_date"),
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="daily_risk_scores")
