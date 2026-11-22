from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, String, Numeric, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.care_request_enum import RequestMode, RequestType, CareRequestStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.request_contact_model import RequestContact
    from app.model.request_message_model import RequestMessage

KST = timezone(timedelta(hours=9)) # UTC+9

# 진료요청
class CareRequest(Base):
    __tablename__ = "care_requests"

    request_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_mode: Mapped[RequestMode] = mapped_column(
        SQLEnum(RequestMode, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    target_doctor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    ) # direct일 때
    request_type: Mapped[RequestType] = mapped_column(
        SQLEnum(RequestType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    address: Mapped[str | None] = mapped_column(String(255))
    sido: Mapped[str | None] = mapped_column(String(20))
    sigungu: Mapped[str | None] = mapped_column(String(30))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    preferred_time: Mapped[str | None] = mapped_column(String(100))
    memo: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[CareRequestStatus] = mapped_column(
        SQLEnum(CareRequestStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=CareRequestStatus.REQUESTED
    )
    matched_hospital_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="SET NULL")
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
    # cascade: CareRequest가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    patient: Mapped["User"] = relationship(
        "User", back_populates="care_requests", foreign_keys=[patient_id]
    )
    contacts: Mapped[list["RequestContact"]] = relationship(
        "RequestContact", back_populates="request", cascade="all, delete-orphan"
    )
    messages: Mapped[list["RequestMessage"]] = relationship(
        "RequestMessage", back_populates="request", cascade="all, delete-orphan"
    )
