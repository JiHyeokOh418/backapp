from datetime import timedelta, timezone
from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.flower_model import Flower

KST = timezone(timedelta(hours=9)) # UTC+9

# 도감_꽃 (복합 PK)
class FlowerCollection(Base):
    __tablename__ = "flower_collections"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    flower_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("flowers.flower_id", ondelete="CASCADE"), primary_key=True
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="flower_collections")
    flower: Mapped["Flower"] = relationship("Flower", back_populates="collections")
