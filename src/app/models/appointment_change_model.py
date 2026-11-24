from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.appointment_change_enum import AppointmentChangeType
from app.enums.common_enum import RequestedBy

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.appointment_model import Appointment
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class AppointmentChange(Base):
    __tablename__ = "appointment_changes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    appointment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("appointments.appointment_id", ondelete="CASCADE"), nullable=False
    )  # 예약
    changed_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )  # 처리자
    from_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 변경 전 일시
    to_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 변경 후 일시
    change_type: Mapped[AppointmentChangeType] = mapped_column(
        SQLEnum(AppointmentChangeType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 변경 종류
    reason: Mapped[str | None] = mapped_column(String(100))  # 사유
    requested_by: Mapped[RequestedBy] = mapped_column(
        SQLEnum(RequestedBy, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 요청자
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 변경 시각

    # 관계
    appointment: Mapped["Appointment"] = relationship("Appointment", back_populates="changes")
    changer: Mapped["User"] = relationship("User", back_populates="appointment_changes")
