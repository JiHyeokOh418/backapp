from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Integer, SmallInteger, Boolean, DateTime, Identity, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.enum.reward_enum import MissionType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base

KST = timezone(timedelta(hours=9)) # UTC+9

# 미션
# point_histories.mission_id는 SET NULL FK라서 relationship을 두지 않는다.
class Mission(Base):
    __tablename__ = "missions"

    mission_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    mission_type: Mapped[MissionType] = mapped_column(
        SQLEnum(MissionType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    reward_point: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_limit: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )
