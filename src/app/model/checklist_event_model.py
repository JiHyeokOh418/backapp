from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.checklist_enum import ChecklistStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.session_checklist_model import SessionChecklist

KST = timezone(timedelta(hours=9)) # UTC+9

# 체크리스트 호출 기록
class ChecklistEvent(Base):
    __tablename__ = "checklist_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    checklist_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("session_checklist.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[ChecklistStatus | None] = mapped_column(
        SQLEnum(ChecklistStatus, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    to_status: Mapped[ChecklistStatus] = mapped_column(
        SQLEnum(ChecklistStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    value: Mapped[dict | list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    checklist: Mapped["SessionChecklist"] = relationship("SessionChecklist", back_populates="events")
