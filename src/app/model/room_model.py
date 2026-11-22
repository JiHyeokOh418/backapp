from datetime import timedelta, timezone
from sqlalchemy import BigInteger, String, Boolean, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.hospital_enum import RoomType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.hospital_model import Hospital

KST = timezone(timedelta(hours=9)) # UTC+9

# 진료실
class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    room_type: Mapped[RoomType] = mapped_column(
        SQLEnum(RoomType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 관계
    hospital: Mapped["Hospital"] = relationship("Hospital", back_populates="rooms")
