from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Integer, Boolean, DateTime, Identity, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.reward_enum import ItemCategory, OwnershipType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_item_stackable_model import UserItemStackable
    from app.model.user_item_unique_model import UserItemUnique
    from app.model.item_collection_model import ItemCollection

KST = timezone(timedelta(hours=9)) # UTC+9

# 아이템
class Item(Base):
    __tablename__ = "items"

    item_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[ItemCategory] = mapped_column(
        SQLEnum(ItemCategory, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ownership_type: Mapped[OwnershipType] = mapped_column(
        SQLEnum(OwnershipType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    # cascade: Item이 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    stackable_holdings: Mapped[list["UserItemStackable"]] = relationship(
        "UserItemStackable", back_populates="item", cascade="all, delete-orphan"
    )
    unique_holdings: Mapped[list["UserItemUnique"]] = relationship(
        "UserItemUnique", back_populates="item", cascade="all, delete-orphan"
    )
    collections: Mapped[list["ItemCollection"]] = relationship(
        "ItemCollection", back_populates="item", cascade="all, delete-orphan"
    )
