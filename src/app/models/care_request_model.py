from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, String, Numeric, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.care_request_enum import CareRequestMode, CareRequestType, CareRequestStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.hospital_model import Hospital
    from app.models.request_contact_model import RequestContact
    from app.models.request_message_model import RequestMessage
    from app.models.appointment_model import Appointment
    from app.models.notification_model import Notification

KST = timezone(timedelta(hours=9)) # UTC+9

class CareRequest(Base):
    __tablename__ = "care_requests"

    request_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 요청 ID
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 환자 ID
    target_doctor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )  # 지정 의사 ID
    matched_hospital_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="SET NULL")
    )  # 연결된 병원 ID
    request_mode: Mapped[CareRequestMode] = mapped_column(
        SQLEnum(CareRequestMode, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 요청 방식
    request_type: Mapped[CareRequestType] = mapped_column(
        SQLEnum(CareRequestType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 요청 종류
    address: Mapped[str | None] = mapped_column(String(255))  # 요청 주소
    sido: Mapped[str | None] = mapped_column(String(20))  # 시·도
    sigungu: Mapped[str | None] = mapped_column(String(30))  # 시·군·구
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))  # 위도
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))  # 경도
    preferred_time: Mapped[str | None] = mapped_column(String(100))  # 희망 시간대
    memo: Mapped[str | None] = mapped_column(String(255))  # 요청 메모
    status: Mapped[CareRequestStatus] = mapped_column(
        SQLEnum(CareRequestStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 진행 상태
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 요청 시각
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(KST)
    )  # 수정 시각

    # 관계
    # cascade: CareRequest가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    patient: Mapped["User"] = relationship(
        "User", back_populates="patient_care_requests", foreign_keys=[patient_id]
    )
    target_doctor: Mapped["User | None"] = relationship(
        "User", back_populates="targeted_care_requests", foreign_keys=[target_doctor_id]
    )
    matched_hospital: Mapped["Hospital | None"] = relationship("Hospital")
    contacts: Mapped[list["RequestContact"]] = relationship(
        "RequestContact", back_populates="request",
        cascade="all, delete-orphan", passive_deletes=True
    )
    messages: Mapped[list["RequestMessage"]] = relationship(
        "RequestMessage", back_populates="request",
        cascade="all, delete-orphan", passive_deletes=True
    )
    appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment", back_populates="request"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="request"
    )
