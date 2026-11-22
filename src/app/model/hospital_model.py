from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, String, Numeric, Boolean, DateTime, Identity
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.doctor_profile_model import DoctorProfile
    from app.model.room_model import Room
    from app.model.patient_chart_model import PatientChart
    from app.model.request_contact_model import RequestContact
    from app.model.appointment_model import Appointment

KST = timezone(timedelta(hours=9)) # UTC+9

# 병원
class Hospital(Base):
    __tablename__ = "hospitals"

    hospital_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(String(255))
    sido: Mapped[str | None] = mapped_column(String(20), index=True)
    sigungu: Mapped[str | None] = mapped_column(String(30), index=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    is_accepting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True) # 요청 받기 여부
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST)
    )

    # 관계
    # cascade: Hospital이 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    doctor_profiles: Mapped[list["DoctorProfile"]] = relationship(
        "DoctorProfile", back_populates="hospital", cascade="all, delete-orphan"
    )
    rooms: Mapped[list["Room"]] = relationship(
        "Room", back_populates="hospital", cascade="all, delete-orphan"
    )
    patient_charts: Mapped[list["PatientChart"]] = relationship(
        "PatientChart", back_populates="hospital", cascade="all, delete-orphan"
    )
    request_contacts: Mapped[list["RequestContact"]] = relationship(
        "RequestContact", back_populates="hospital", cascade="all, delete-orphan"
    )
    appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment", back_populates="hospital", cascade="all, delete-orphan"
    )
