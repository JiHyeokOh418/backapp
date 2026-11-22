from datetime import datetime, date, timedelta, timezone
from sqlalchemy import BigInteger, Date, DateTime, Identity, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

# 출석
class Attendance(Base):
    __tablename__ = "attendances"

    attendance_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attend_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    first_access_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "attend_date", name="uq_attendances_user_id_attend_date"), # 하루 한 번 출석
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="attendances")
