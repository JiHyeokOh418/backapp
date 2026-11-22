from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.mood_model import Mood

KST = timezone(timedelta(hours=9)) # UTC+9

# 도감_표정 (복합 PK)
class MoodCollection(Base):
    __tablename__ = "mood_collections"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    mood_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("moods.mood_id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="mood_collections")
    mood: Mapped["Mood"] = relationship("Mood", back_populates="collections")
