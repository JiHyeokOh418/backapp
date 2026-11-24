from datetime import date, datetime, timedelta, timezone
from sqlalchemy import BigInteger, Date, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class Attendance(Base):
    __tablename__ = "attendances"

    attendance_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 출석 ID
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 회원 ID
    attend_date: Mapped[date] = mapped_column(Date, nullable=False)  # 출석한 날
    first_access_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 첫 접속 시각

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="attendances")
