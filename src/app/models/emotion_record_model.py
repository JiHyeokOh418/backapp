from datetime import date, datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, SmallInteger, Boolean, Date, DateTime, Identity, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class EmotionRecord(Base):
    __tablename__ = "emotion_records"

    emotion_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 감정 기록 ID
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 회원 ID
    record_date: Mapped[date] = mapped_column(Date, nullable=False)  # 체크인한 날
    mood_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 기분 점수
    mood_tag: Mapped[str | None] = mapped_column(String(20))  # 기분 태그
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
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 기본값은 user_settings.share_report를 따름
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 삭제 시각

    __table_args__ = (
        UniqueConstraint("user_id", "record_date", name="uq_emotion_records_user_id_record_date"),
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="emotion_records")
