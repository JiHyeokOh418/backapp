from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.appointment_enum import ChangeType, RequestedBy

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.appointment_model import Appointment

KST = timezone(timedelta(hours=9)) # UTC+9

# 예약 변경 이력
class AppointmentChange(Base):
    __tablename__ = "appointment_changes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    appointment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("appointments.appointment_id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    to_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_type: Mapped[ChangeType] = mapped_column(
        SQLEnum(ChangeType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(100))
    requested_by: Mapped[RequestedBy] = mapped_column(
        SQLEnum(RequestedBy, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    changed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    appointment: Mapped["Appointment"] = relationship("Appointment", back_populates="changes")
