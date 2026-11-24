from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.common_enum import ChecklistStatus

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.session_checklist_model import SessionChecklist

KST = timezone(timedelta(hours=9)) # UTC+9

class ChecklistEvent(Base):
    __tablename__ = "checklist_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    checklist_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("session_checklist.id", ondelete="CASCADE"), nullable=False
    )  # 체크리스트 행
    from_status: Mapped[ChecklistStatus] = mapped_column(
        SQLEnum(ChecklistStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 변경 전
    to_status: Mapped[ChecklistStatus] = mapped_column(
        SQLEnum(ChecklistStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 변경 후
    value: Mapped[dict | None] = mapped_column(JSONB)  # 변경 시점 값
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 변경 시각

    # 관계
    checklist: Mapped["SessionChecklist"] = relationship("SessionChecklist", back_populates="events")
