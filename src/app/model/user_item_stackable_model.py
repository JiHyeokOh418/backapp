from datetime import timedelta, timezone
from sqlalchemy import BigInteger, Identity, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.item_model import Item

KST = timezone(timedelta(hours=9)) # UTC+9

# 보유_아이템(중복)
class UserItemStackable(Base):
    __tablename__ = "user_items_stackable"

    user_item_stackable_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("items.item_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_user_items_stackable_user_id_item_id"),
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="stackable_items")
    item: Mapped["Item"] = relationship("Item", back_populates="stackable_holdings")
