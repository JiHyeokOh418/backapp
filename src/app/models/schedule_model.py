from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.schedule_enum import ScheduleType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.appointment_model import Appointment
    from app.models.notification_model import Notification

KST = timezone(timedelta(hours=9)) # UTC+9

class Schedule(Base):
    __tablename__ = "schedules"

    schedule_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 일정 ID
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 회원 ID
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )  # 등록자 ID
    appointment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("appointments.appointment_id", ondelete="SET NULL")
    )  # 관련 예약 ID
    schedule_type: Mapped[ScheduleType] = mapped_column(
        SQLEnum(ScheduleType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 일정 종류
    title: Mapped[str] = mapped_column(String(100), nullable=False)  # 제목
    memo: Mapped[str | None] = mapped_column(String(255))  # 메모
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 시작 시각
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 종료 시각
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 알림 시각
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 생성 시각
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(KST)
    )  # 수정 시각

    # 관계
    user: Mapped["User"] = relationship(
        "User", back_populates="schedules", foreign_keys=[user_id]
    )
    creator: Mapped["User"] = relationship(
        "User", back_populates="created_schedules", foreign_keys=[created_by]
    )
    appointment: Mapped["Appointment | None"] = relationship("Appointment", back_populates="schedules")
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="schedule"
    )
