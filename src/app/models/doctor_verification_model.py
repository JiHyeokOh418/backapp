from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Text, DateTime, Identity, ForeignKey, Index, text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.doctor_verification_enum import DoctorVerificationStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.hospital_model import Hospital
    from app.models.admin_model import Admin

KST = timezone(timedelta(hours=9)) # UTC+9

class DoctorVerification(Base):
    __tablename__ = "doctor_verifications"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 신청한 회원 ID (pending은 1명당 1건)
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False
    )  # 승인 시 doctor_profiles.hospital_id로 복사
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("admins.id", ondelete="SET NULL")
    )  # 승인·반려한 관리자 (대기 중 NULL)
    license_number: Mapped[str] = mapped_column(String(50), nullable=False)  # 의사 면허번호
    specialty: Mapped[str | None] = mapped_column(String(50))  # 승인 시 doctor_profiles.specialty로 복사
    license_file_url: Mapped[str | None] = mapped_column(String(500))  # 면허 사본 파일 경로
    status: Mapped[DoctorVerificationStatus] = mapped_column(
        SQLEnum(DoctorVerificationStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=DoctorVerificationStatus.PENDING
    )  # 대기·승인·반려
    reject_reason: Mapped[str | None] = mapped_column(Text)  # 반려 사유
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 승인·반려한 시각
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 신청 시각

    __table_args__ = (
        Index(
            "uix_doctor_verifications_user_pending", "user_id",
            unique=True, postgresql_where=text("status = 'pending'")
        ),
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="doctor_verifications")
    hospital: Mapped["Hospital"] = relationship("Hospital")
    reviewer: Mapped["Admin | None"] = relationship("Admin", back_populates="reviewed_verifications")
