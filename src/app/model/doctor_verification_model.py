from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Text, DateTime, Identity, ForeignKey, Index, text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.user_enum import VerificationStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.hospital_model import Hospital

KST = timezone(timedelta(hours=9)) # UTC+9

# 의사 승인 신청 (관리자테이블추가 ERD)
# - 관리자가 면허를 확인하고 승인하면 users.role=doctor, doctor_profiles 생성
# - 반려 후 재신청 가능, 대기(pending) 신청은 1명당 1건 (부분 유니크 인덱스)
class DoctorVerification(Base):
    __tablename__ = "doctor_verifications"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admins.id", ondelete="SET NULL")
    )
    license_number: Mapped[str] = mapped_column(String(50), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(50))
    license_file_url: Mapped[str | None] = mapped_column(String(500)) # 저장 위치 미정
    status: Mapped[VerificationStatus] = mapped_column(
        SQLEnum(VerificationStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=VerificationStatus.PENDING
    )
    reject_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )

    __table_args__ = (
        Index(
            "uq_doctor_verifications_pending_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'")
        ),
    )

    # 관계 (조회용 단방향, 응답에 신청자·병원 이름을 채운다)
    user: Mapped["User"] = relationship("User")
    hospital: Mapped["Hospital"] = relationship("Hospital")
