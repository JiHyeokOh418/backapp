from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.request_contact_enum import RequestContactStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.care_request_model import CareRequest
    from app.models.hospital_model import Hospital
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class RequestContact(Base):
    __tablename__ = "request_contacts"

    contact_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 연락 ID
    request_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("care_requests.request_id", ondelete="CASCADE"), nullable=False
    )  # 요청 ID
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False
    )  # 병원 ID
    responded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )  # 응답한 의사 ID
    status: Mapped[RequestContactStatus] = mapped_column(
        SQLEnum(RequestContactStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 응답 상태
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 연락 보낸 시각
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 응답 시각

    # 관계
    request: Mapped["CareRequest"] = relationship("CareRequest", back_populates="contacts")
    hospital: Mapped["Hospital"] = relationship("Hospital")
    responder: Mapped["User | None"] = relationship("User", back_populates="responded_contacts")
