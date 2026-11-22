from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.care_request_enum import ContactStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.care_request_model import CareRequest
    from app.model.hospital_model import Hospital

KST = timezone(timedelta(hours=9)) # UTC+9

# 병원연락내역
class RequestContact(Base):
    __tablename__ = "request_contacts"

    contact_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("care_requests.request_id", ondelete="CASCADE"), nullable=False, index=True
    )
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True
    )
    responded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[ContactStatus] = mapped_column(
        SQLEnum(ContactStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ContactStatus.SENT
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 관계
    request: Mapped["CareRequest"] = relationship("CareRequest", back_populates="contacts")
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="request_contacts")
