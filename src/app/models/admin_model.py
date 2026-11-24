from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.doctor_verification_model import DoctorVerification

KST = timezone(timedelta(hours=9)) # UTC+9

class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )  # 관리자인 회원 ID (회원 1명당 1행)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 관리자로 지정된 시각

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="admin")
    reviewed_verifications: Mapped[list["DoctorVerification"]] = relationship(
        "DoctorVerification", back_populates="reviewer"
    )
