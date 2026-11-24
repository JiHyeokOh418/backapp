from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Boolean, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.doctor_memo_enum import DoctorMemoCategory

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class DoctorMemo(Base):
    __tablename__ = "doctor_memos"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 환자
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 작성 의사
    category: Mapped[DoctorMemoCategory] = mapped_column(
        SQLEnum(DoctorMemoCategory, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # clinic=진료, counsel=상담
    content: Mapped[str] = mapped_column(String(1000), nullable=False)  # 내용
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 고정
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 작성 시각
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(KST)
    )  # 수정 시각
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 삭제 시각

    # 관계
    patient: Mapped["User"] = relationship(
        "User", back_populates="patient_memos", foreign_keys=[patient_id]
    )
    doctor: Mapped["User"] = relationship(
        "User", back_populates="doctor_memos", foreign_keys=[doctor_id]
    )
