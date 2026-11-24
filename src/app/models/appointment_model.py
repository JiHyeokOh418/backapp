from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.appointment_enum import (
    AppointmentContactMethod, AppointmentStatus, AppointmentKind,
    AppointmentVisitType, AppointmentBookingSource
)

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.care_request_model import CareRequest
    from app.models.user_model import User
    from app.models.hospital_model import Hospital
    from app.models.room_model import Room
    from app.models.appointment_change_model import AppointmentChange
    from app.models.schedule_model import Schedule
    from app.models.notification_model import Notification

KST = timezone(timedelta(hours=9)) # UTC+9

class Appointment(Base):
    __tablename__ = "appointments"

    appointment_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 예약 ID
    request_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("care_requests.request_id", ondelete="SET NULL")
    )  # 요청 ID
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 환자 ID
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 의사 ID
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False
    )  # 병원 ID
    room_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("rooms.id", ondelete="SET NULL")
    )  # 진료실
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )  # 등록자
    contact_method: Mapped[AppointmentContactMethod] = mapped_column(
        SQLEnum(AppointmentContactMethod, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 예약 연락 방식
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 진료 일시
    status: Mapped[AppointmentStatus] = mapped_column(
        SQLEnum(AppointmentStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 예약 상태
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 진료 완료 시각
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 예약 시각
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(KST)
    )  # 수정 시각
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 종료 시각
    kind: Mapped[AppointmentKind] = mapped_column(
        SQLEnum(AppointmentKind, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AppointmentKind.TREATMENT
    )  # 예약 종류
    tests: Mapped[list | None] = mapped_column(JSONB)  # psych_test일 때. 예: ["phq9","gad7","bdi2"]
    visit_type: Mapped[AppointmentVisitType | None] = mapped_column(
        SQLEnum(AppointmentVisitType, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )  # 초진·재진
    insurance_type: Mapped[str | None] = mapped_column(String(20))  # 보험 구분
    booking_source: Mapped[AppointmentBookingSource] = mapped_column(
        SQLEnum(AppointmentBookingSource, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 예약 경로
    patient_note: Mapped[str | None] = mapped_column(String(255))  # 요청 사항

    # 관계
    # cascade: Appointment가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    request: Mapped["CareRequest | None"] = relationship("CareRequest", back_populates="appointments")
    patient: Mapped["User"] = relationship(
        "User", back_populates="patient_appointments", foreign_keys=[patient_id]
    )
    doctor: Mapped["User"] = relationship(
        "User", back_populates="doctor_appointments", foreign_keys=[doctor_id]
    )
    creator: Mapped["User | None"] = relationship(
        "User", back_populates="created_appointments", foreign_keys=[created_by]
    )
    hospital: Mapped["Hospital"] = relationship("Hospital")
    room: Mapped["Room | None"] = relationship("Room", back_populates="appointments")
    changes: Mapped[list["AppointmentChange"]] = relationship(
        "AppointmentChange", back_populates="appointment",
        cascade="all, delete-orphan", passive_deletes=True
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="appointment"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="appointment"
    )
