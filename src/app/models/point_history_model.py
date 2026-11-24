from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Integer, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.point_history_enum import PointHistoryType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.mission_model import Mission
    from app.models.item_model import Item
    from app.models.user_mission_log_model import UserMissionLog

KST = timezone(timedelta(hours=9)) # UTC+9

class PointHistory(Base):
    __tablename__ = "point_histories"

    history_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 내역 ID
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 회원 ID
    mission_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("missions.mission_id", ondelete="SET NULL")
    )  # 획득 미션 ID
    item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("items.item_id", ondelete="SET NULL")
    )  # 구매 아이템 ID
    history_type: Mapped[PointHistoryType] = mapped_column(
        SQLEnum(PointHistoryType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 구분
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # 포인트
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)  # 처리 후 잔액
    reason: Mapped[str | None] = mapped_column(String(50))  # 사유
    base_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 기준 날짜
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 처리 시각

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="point_histories")
    mission: Mapped["Mission | None"] = relationship("Mission")
    item: Mapped["Item | None"] = relationship("Item")
    mission_logs: Mapped[list["UserMissionLog"]] = relationship(
        "UserMissionLog", back_populates="history"
    )
