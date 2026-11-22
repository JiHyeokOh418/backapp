from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.user_item_unique_model import UserItemUnique

KST = timezone(timedelta(hours=9)) # UTC+9

# 마이룸_배치물 (복합 PK)
class MyroomEntity(Base):
    __tablename__ = "myroom_entities"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    holding_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user_items_unique.holding_item_id", ondelete="CASCADE"), primary_key=True
    ) # ERD: BIGINT -> 참조 PK(CHAR(36))에 맞춰 String(36)으로 변경
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="myroom_entities")
    holding_item: Mapped["UserItemUnique"] = relationship("UserItemUnique", back_populates="myroom_entities")
