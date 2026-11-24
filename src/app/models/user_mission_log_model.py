from datetime import date, datetime, timedelta, timezone
from sqlalchemy import BigInteger, Integer, Date, DateTime, Identity, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.mission_model import Mission
    from app.models.point_history_model import PointHistory

KST = timezone(timedelta(hours=9)) # UTC+9

class UserMissionLog(Base):
    __tablename__ = "user_mission_logs"

    log_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 기록 ID
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 회원 ID
    mission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("missions.mission_id", ondelete="RESTRICT"), nullable=False
    )  # 미션 ID
    history_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("point_histories.history_id", ondelete="SET NULL")
    )  # 지급된 포인트 내역
    log_date: Mapped[date] = mapped_column(Date, nullable=False)  # 수행일 ('하루' = 자정 기준)
    progress_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 진행 횟수
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 완료 시각
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 취소 시각
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 생성 시각

    __table_args__ = (
        UniqueConstraint(
            "user_id", "mission_id", "log_date",
            name="uq_user_mission_logs_user_id_mission_id_log_date"
        ),
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="user_mission_logs")
    mission: Mapped["Mission"] = relationship("Mission")
    history: Mapped["PointHistory | None"] = relationship("PointHistory", back_populates="mission_logs")
