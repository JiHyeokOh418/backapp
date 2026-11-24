from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

class CareRelation(Base):
    __tablename__ = "care_relations"

    relation_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # 담당 관계 ID
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 환자 ID
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 담당 의사 ID
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 담당 시작일
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 담당 종료일
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 생성 시각

    # 관계
    patient: Mapped["User"] = relationship(
        "User", back_populates="patient_care_relations", foreign_keys=[patient_id]
    )
    doctor: Mapped["User"] = relationship(
        "User", back_populates="doctor_care_relations", foreign_keys=[doctor_id]
    )
