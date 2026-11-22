from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.appointment_enum import ScheduleType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

# 일정
class Schedule(Base):
    __tablename__ = "schedules"

    schedule_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    schedule_type: Mapped[ScheduleType] = mapped_column(
        SQLEnum(ScheduleType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    memo: Mapped[str | None] = mapped_column(String(255))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    appointment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("appointments.appointment_id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST)
    )

    # 관계 (users를 2번 참조하므로 foreign_keys 지정)
    user: Mapped["User"] = relationship("User", back_populates="schedules", foreign_keys=[user_id])
