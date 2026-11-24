from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, Numeric, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.daily_risk_score_enum import DailyRiskScoreTrendFlag

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class DailyRiskScore(Base):
    __tablename__ = "daily_risk_scores"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 환자
    base_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 기준 날짜
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)  # 일 점수
    trend_flag: Mapped[DailyRiskScoreTrendFlag] = mapped_column(
        SQLEnum(DailyRiskScoreTrendFlag, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=DailyRiskScoreTrendFlag.NONE
    )  # 추세 표시
    detail: Mapped[dict | None] = mapped_column(JSONB)  # 계산 근거
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 생성 시각

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="daily_risk_scores")
