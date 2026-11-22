from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.item_model import Item

KST = timezone(timedelta(hours=9)) # UTC+9

# 도감_아이템 (복합 PK)
class ItemCollection(Base):
    __tablename__ = "item_collections"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("items.item_id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="item_collections")
    item: Mapped["Item"] = relationship("Item", back_populates="collections")
