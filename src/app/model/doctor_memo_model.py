from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Boolean, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.hospital_enum import MemoCategory

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

# 관리 메모
class DoctorMemo(Base):
    __tablename__ = "doctor_memos"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[MemoCategory] = mapped_column(
        SQLEnum(MemoCategory, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    content: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST),
        onupdate=lambda: datetime.now(KST)
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 관계 (users를 2번 참조하므로 foreign_keys 지정)
    patient: Mapped["User"] = relationship(
        "User", back_populates="patient_memos", foreign_keys=[patient_id]
    )
    doctor: Mapped["User"] = relationship(
        "User", back_populates="doctor_memos", foreign_keys=[doctor_id]
    )
