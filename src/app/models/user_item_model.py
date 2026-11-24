from datetime import date, datetime, timedelta, timezone
from sqlalchemy import BigInteger, Integer, Date, DateTime, Identity, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.item_model import Item

KST = timezone(timedelta(hours=9)) # UTC+9

class UserItem(Base):
    __tablename__ = "user_items"

    user_item_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 보유 아이템 ID
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 회원 ID
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("items.item_id", ondelete="RESTRICT"), nullable=False
    )  # 아이템 ID
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # unique는 항상 1. stackable은 0이 돼도 줄 유지
    total_acquired: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 모은 개수
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 처음 얻은 시각
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(KST)
    )  # 수정 시각
    last_refilled_on: Mapped[date | None] = mapped_column(Date)  # 기본 제공 아이템만

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_user_items_user_id_item_id"),
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="user_items")
    item: Mapped["Item"] = relationship("Item")
