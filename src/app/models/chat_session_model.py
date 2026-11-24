from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, DateTime, Identity, ForeignKey, Index, text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.chat_session_enum import (
    ChatSessionStatus, ChatSessionEndReason, ChatSessionSummaryStatus, ChatSessionType
)

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user_model import User
    from app.models.message_model import Message
    from app.models.session_summary_model import SessionSummary
    from app.models.session_document_model import SessionDocument
    from app.models.session_checklist_model import SessionChecklist
    from app.models.assessment_result_model import AssessmentResult

KST = timezone(timedelta(hours=9)) # UTC+9

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # 환자
    prev_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="SET NULL")
    )  # 직전 예정 세션 (참조용)
    status: Mapped[ChatSessionStatus] = mapped_column(
        SQLEnum(ChatSessionStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 세션 상태 (환자당 active 1개)
    end_reason: Mapped[ChatSessionEndReason | None] = mapped_column(
        SQLEnum(ChatSessionEndReason, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )  # 종료 사유
    summary_status: Mapped[ChatSessionSummaryStatus | None] = mapped_column(
        SQLEnum(ChatSessionSummaryStatus, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )  # 사후 요약 상태
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # 상담 예정 시각 (이후 접속 가능)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 접속 마감. 경과 시 missed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 시작 시각
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 종료 시각
    session_type: Mapped[ChatSessionType] = mapped_column(
        SQLEnum(ChatSessionType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ChatSessionType.COUNSELING
    )  # counseling=일반 AI 상담, intake=초진 전 사전 문진

    __table_args__ = (
        Index(
            "uix_chat_sessions_user_active", "user_id",
            unique=True, postgresql_where=text("status = 'active'")
        ),
    )

    # 관계
    # cascade: ChatSession이 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    user: Mapped["User"] = relationship("User", back_populates="chat_sessions")
    prev_session: Mapped["ChatSession | None"] = relationship(
        "ChatSession", remote_side="ChatSession.id"
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session",
        cascade="all, delete-orphan", passive_deletes=True
    )
    summary: Mapped["SessionSummary | None"] = relationship(
        "SessionSummary", back_populates="session", uselist=False,
        cascade="all, delete-orphan", passive_deletes=True
    )
    session_documents: Mapped[list["SessionDocument"]] = relationship(
        "SessionDocument", back_populates="session",
        cascade="all, delete-orphan", passive_deletes=True
    )
    checklists: Mapped[list["SessionChecklist"]] = relationship(
        "SessionChecklist", back_populates="session",
        cascade="all, delete-orphan", passive_deletes=True
    )
    assessment_results: Mapped[list["AssessmentResult"]] = relationship(
        "AssessmentResult", back_populates="session"
    )
