from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.appointment_enum import ContactMethod, AppointmentStatus, AppointmentKind, VisitType, BookingSource

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.hospital_model import Hospital
    from app.model.appointment_change_model import AppointmentChange

KST = timezone(timedelta(hours=9)) # UTC+9

# 진료예약
class Appointment(Base):
    __tablename__ = "appointments"

    appointment_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    request_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("care_requests.request_id", ondelete="SET NULL"), index=True
    )
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True
    ) # ERD: CHAR(36) -> 참조 PK에 맞춰 BIGINT로 변경
    contact_method: Mapped[ContactMethod | None] = mapped_column(
        SQLEnum(ContactMethod, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[AppointmentStatus] = mapped_column(
        SQLEnum(AppointmentStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AppointmentStatus.BOOKED
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kind: Mapped[AppointmentKind] = mapped_column(
        SQLEnum(AppointmentKind, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AppointmentKind.TREATMENT
    )
    tests: Mapped[dict | list | None] = mapped_column(JSONB)
    visit_type: Mapped[VisitType | None] = mapped_column(
        SQLEnum(VisitType, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    room_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("rooms.id", ondelete="SET NULL")
    )
    insurance_type: Mapped[str | None] = mapped_column(String(20))
    booking_source: Mapped[BookingSource | None] = mapped_column(
        SQLEnum(BookingSource, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    patient_note: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
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

    # 관계 (users를 3번 참조하므로 foreign_keys 지정)
    # cascade: Appointment가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    patient: Mapped["User"] = relationship(
        "User", back_populates="patient_appointments", foreign_keys=[patient_id]
    )
    doctor: Mapped["User"] = relationship(
        "User", back_populates="doctor_appointments", foreign_keys=[doctor_id]
    )
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="appointments")
    changes: Mapped[list["AppointmentChange"]] = relationship(
        "AppointmentChange", back_populates="appointment", cascade="all, delete-orphan"
    )
