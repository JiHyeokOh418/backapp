from datetime import timedelta, timezone
from sqlalchemy import BigInteger, Integer, Boolean, Identity, ForeignKey, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.checklist_enum import ChecklistStatus, SkipReason

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.chat_session_model import ChatSession
    from app.model.checklist_item_model import ChecklistItem
    from app.model.checklist_event_model import ChecklistEvent

KST = timezone(timedelta(hours=9)) # UTC+9

# 세션 체크리스트
class SessionChecklist(Base):
    __tablename__ = "session_checklist"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("checklist_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ChecklistStatus] = mapped_column(
        SQLEnum(ChecklistStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ChecklistStatus.PENDING
    )
    skip_reason: Mapped[SkipReason | None] = mapped_column(
        SQLEnum(SkipReason, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    value: Mapped[dict | list | None] = mapped_column(JSONB)
    evidence_message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    ) # 근거 메시지
    ask_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("session_id", "item_id", name="uq_session_checklist_session_id_item_id"),
    )

    # 관계
    # cascade: SessionChecklist가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="checklists")
    item: Mapped["ChecklistItem"] = relationship("ChecklistItem", back_populates="session_checklists")
    events: Mapped[list["ChecklistEvent"]] = relationship(
        "ChecklistEvent", back_populates="checklist", cascade="all, delete-orphan"
    )
