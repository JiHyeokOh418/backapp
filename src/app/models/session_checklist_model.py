from sqlalchemy import BigInteger, Integer, Boolean, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.common_enum import ChecklistStatus
from app.enums.session_checklist_enum import SessionChecklistSkipReason

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chat_session_model import ChatSession
    from app.models.checklist_item_model import ChecklistItem
    from app.models.message_model import Message
    from app.models.checklist_event_model import ChecklistEvent

class SessionChecklist(Base):
    __tablename__ = "session_checklist"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )  # 세션
    item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("checklist_items.id", ondelete="RESTRICT"), nullable=False
    )  # 원본 항목
    evidence_message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )  # 근거 메시지
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)  # 필수 여부 (복사본)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)  # 순서 (복사본)
    status: Mapped[ChecklistStatus] = mapped_column(
        SQLEnum(ChecklistStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ChecklistStatus.PENDING
    )  # 진행 상태
    skip_reason: Mapped[SessionChecklistSkipReason | None] = mapped_column(
        SQLEnum(SessionChecklistSkipReason, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )  # skipped일 때만
    value: Mapped[dict | None] = mapped_column(JSONB)  # 채운 값
    ask_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 질문 횟수

    # 관계
    # cascade: SessionChecklist가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="checklists")
    item: Mapped["ChecklistItem"] = relationship("ChecklistItem")
    evidence_message: Mapped["Message | None"] = relationship("Message", back_populates="evidence_checklists")
    events: Mapped[list["ChecklistEvent"]] = relationship(
        "ChecklistEvent", back_populates="checklist",
        cascade="all, delete-orphan", passive_deletes=True
    )
