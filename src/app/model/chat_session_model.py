from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.chat_enum import SessionStatus, SessionEndReason, SummaryStatus, SessionType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.user_model import User
    from app.model.message_model import Message
    from app.model.session_summary_model import SessionSummary
    from app.model.session_document_model import SessionDocument
    from app.model.session_checklist_model import SessionChecklist

KST = timezone(timedelta(hours=9)) # UTC+9

# 채팅세션
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prev_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="SET NULL")
    ) # 이전 세션
    status: Mapped[SessionStatus] = mapped_column(
        SQLEnum(SessionStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SessionStatus.SCHEDULED
    )
    end_reason: Mapped[SessionEndReason | None] = mapped_column(
        SQLEnum(SessionEndReason, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    summary_status: Mapped[SummaryStatus] = mapped_column(
        SQLEnum(SummaryStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SummaryStatus.PENDING
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # session_summaries.session_id와 순환 참조라서 use_alter=True
    summary_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("session_summaries.id", ondelete="SET NULL", use_alter=True)
    )
    session_type: Mapped[SessionType] = mapped_column(
        SQLEnum(SessionType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SessionType.COUNSELLING
    )

    # 관계
    # cascade: ChatSession이 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    user: Mapped["User"] = relationship("User", back_populates="chat_sessions")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan"
    )
    # chat_sessions.summary_id도 session_summaries를 가리키므로 foreign_keys 지정
    summary: Mapped["SessionSummary | None"] = relationship(
        "SessionSummary", back_populates="session", foreign_keys="SessionSummary.session_id",
        uselist=False, cascade="all, delete-orphan"
    )
    session_documents: Mapped[list["SessionDocument"]] = relationship(
        "SessionDocument", back_populates="session", cascade="all, delete-orphan"
    )
    checklists: Mapped[list["SessionChecklist"]] = relationship(
        "SessionChecklist", back_populates="session", cascade="all, delete-orphan"
    )
