from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Integer, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class ExerciseRecord(Base):
    __tablename__ = "exercise_records"

    exercise_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 운동 기록 ID
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 회원 ID
    record_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 운동한 날
    exercise_type: Mapped[str] = mapped_column(String(255), nullable=False)  # 운동 종류
    duration_minutes: Mapped[int | None] = mapped_column(Integer)  # 운동 시간(분)
    memo: Mapped[str | None] = mapped_column(String(255))  # 메모
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 작성 시각
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(KST)
    )  # 수정 시각

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="exercise_records")
