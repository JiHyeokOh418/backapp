from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.flower_model import Flower

class UserFlower(Base):
    __tablename__ = "user_flowers"

    user_flower_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 꽃 도감 ID
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 회원 ID
    flower_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("flowers.flower_id", ondelete="RESTRICT"), nullable=False
    )  # 꽃 ID
    bloomed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 만개한 날 (최근 값 = 레벨 초기화일)

    __table_args__ = (
        UniqueConstraint("user_id", "flower_id", name="uq_user_flowers_user_id_flower_id"),
    )

    # 관계
    user: Mapped["User"] = relationship("User", back_populates="user_flowers")
    flower: Mapped["Flower"] = relationship("Flower")
