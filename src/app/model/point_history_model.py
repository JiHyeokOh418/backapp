from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Integer, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.reward_enum import PointHistoryType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

# 포인트내역
class PointHistory(Base):
    __tablename__ = "point_histories"

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    history_type: Mapped[PointHistoryType] = mapped_column(
        SQLEnum(PointHistoryType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    mission_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("missions.mission_id", ondelete="SET NULL")
    ) # 적립일 때
    item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("items.item_id", ondelete="SET NULL")
    ) # 사용일 때
    reason: Mapped[str | None] = mapped_column(String(50))
    base_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="point_histories")
