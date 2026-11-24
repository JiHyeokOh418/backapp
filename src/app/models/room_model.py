from sqlalchemy import BigInteger, String, Boolean, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.room_enum import RoomType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.hospital_model import Hospital
    from app.models.appointment_model import Appointment

class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    hospital_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hospitals.hospital_id", ondelete="RESTRICT"), nullable=False
    )  # 병원
    name: Mapped[str] = mapped_column(String(30), nullable=False)  # 진료실 이름
    room_type: Mapped[RoomType] = mapped_column(
        SQLEnum(RoomType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # consult=진료·상담실, exam=심리검사실
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 사용 여부

    # 관계
    hospital: Mapped["Hospital"] = relationship("Hospital")
    appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment", back_populates="room"
    )
