from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User

KST = timezone(timedelta(hours=9)) # UTC+9

# 담당관계
class CareRelation(Base):
    __tablename__ = "care_relations"

    relation_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계 (users를 2번 참조하므로 foreign_keys 지정)
    patient: Mapped["User"] = relationship(
        "User", back_populates="patient_care_relations", foreign_keys=[patient_id]
    )
    doctor: Mapped["User"] = relationship(
        "User", back_populates="doctor_care_relations", foreign_keys=[doctor_id]
    )
