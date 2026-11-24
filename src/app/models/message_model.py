from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Text, Integer, DateTime, Identity, ForeignKey, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enums.message_enum import MessageRole, MessageSystemRecordStatus, MessageInputType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chat_session_model import ChatSession
    from app.models.emotion_analysis_model import EmotionAnalysis
    from app.models.guard_check_model import GuardCheck
    from app.models.llm_call_model import LlmCall
    from app.models.session_checklist_model import SessionChecklist
    from app.models.risk_event_model import RiskEvent

KST = timezone(timedelta(hours=9)) # UTC+9

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )  # 소속 세션
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # 세션 내 순번
    role: Mapped[MessageRole] = mapped_column(
        SQLEnum(MessageRole, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )  # 발화자
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 사용자 문장 또는 user_reply.text
    expression: Mapped[str | None] = mapped_column(String(30))  # assistant만. 캐릭터 표정
    client_message_id: Mapped[str | None] = mapped_column(String(36))  # 멱등성 키
    system_record_status: Mapped[MessageSystemRecordStatus | None] = mapped_column(
        SQLEnum(MessageSystemRecordStatus, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )  # assistant만. system_record 검증 결과
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 생성 시각
    input_type: Mapped[MessageInputType] = mapped_column(
        SQLEnum(MessageInputType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=MessageInputType.TEXT
    )  # voice는 Whisper 변환 글을 content에 저장

    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_messages_session_id_seq"),
    )

    # 관계
    # cascade: Message가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
    emotion_analyses: Mapped[list["EmotionAnalysis"]] = relationship(
        "EmotionAnalysis", back_populates="message",
        cascade="all, delete-orphan", passive_deletes=True
    )
    guard_checks: Mapped[list["GuardCheck"]] = relationship(
        "GuardCheck", back_populates="message",
        cascade="all, delete-orphan", passive_deletes=True
    )
    llm_calls: Mapped[list["LlmCall"]] = relationship(
        "LlmCall", back_populates="message"
    )
    evidence_checklists: Mapped[list["SessionChecklist"]] = relationship(
        "SessionChecklist", back_populates="evidence_message"
    )
    risk_events: Mapped[list["RiskEvent"]] = relationship(
        "RiskEvent", back_populates="message"
    )
