from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.hospital_model import Hospital

KST = timezone(timedelta(hours=9)) # UTC+9

# 의사정보 (users와 1:1, user_id가 PK)
class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True
    )
    specialty: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="doctor_profile")
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="doctor_profiles")
