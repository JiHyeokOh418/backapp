from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, SmallInteger, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

# 캐릭터
class Character(Base):
    __tablename__ = "characters"

    character_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    hunger: Mapped[int | None] = mapped_column(SmallInteger) # 포만감
    dirtiness: Mapped[int | None] = mapped_column(SmallInteger) # 청결도
    flower_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("flowers.flower_id", ondelete="SET NULL")
    )
    mood_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("moods.mood_id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST)
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="characters")
