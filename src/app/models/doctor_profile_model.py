from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.hospital_model import Hospital

KST = timezone(timedelta(hours=9)) # UTC+9

class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )  # 의사 회원 ID
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False
    )  # 소속 병원 ID
    specialty: Mapped[str | None] = mapped_column(String(50))  # 진료 분야
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 등록 시각

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="doctor_profile")
    hospital: Mapped["Hospital"] = relationship("Hospital")
