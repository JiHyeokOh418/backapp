import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.item_model import Item
    from app.model.myroom_entity_model import MyroomEntity

KST = timezone(timedelta(hours=9)) # UTC+9

# 보유_아이템(유일)
class UserItemUnique(Base):
    __tablename__ = "user_items_unique"

    holding_item_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("items.item_id", ondelete="CASCADE"), nullable=False, index=True
    ) # ERD: CHAR(36) -> 참조 PK에 맞춰 BIGINT로 변경
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    ) # ERD: CHAR(36) -> 참조 PK에 맞춰 BIGINT로 변경
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    # cascade: UserItemUnique가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    user: Mapped["User"] = relationship("User", back_populates="unique_items")
    item: Mapped["Item"] = relationship("Item", back_populates="unique_holdings")
    myroom_entities: Mapped[list["MyroomEntity"]] = relationship(
        "MyroomEntity", back_populates="holding_item", cascade="all, delete-orphan"
    )
