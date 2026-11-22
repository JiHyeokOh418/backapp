from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, Text, Integer, DateTime, Identity, ForeignKey, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.enum.chat_enum import MessageRole, SystemRecordStatus, InputType

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.chat_session_model import ChatSession
    from app.model.llm_call_model import LlmCall
    from app.model.guard_check_model import GuardCheck
    from app.model.emotion_analysis_model import EmotionAnalysis

KST = timezone(timedelta(hours=9)) # UTC+9

# 메시지
class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[MessageRole] = mapped_column(
        SQLEnum(MessageRole, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    expression: Mapped[str | None] = mapped_column(String(30)) # AI 답변일 때 캐릭터 표정
    client_message_id: Mapped[str | None] = mapped_column(String(36)) # 클라이언트 중복 전송 방지용
    system_record_status: Mapped[SystemRecordStatus | None] = mapped_column(
        SQLEnum(SystemRecordStatus, native_enum=False, values_callable=lambda e: [m.value for m in e])
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )
    input_type: Mapped[InputType] = mapped_column(
        SQLEnum(InputType, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=InputType.TEXT
    )

    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_messages_session_id_seq"),
        UniqueConstraint("client_message_id", name="uq_messages_client_message_id"), # 중복 전송 방지
    )

    # 관계
    # cascade: Message가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
    llm_calls: Mapped[list["LlmCall"]] = relationship(
        "LlmCall", back_populates="message", cascade="all, delete-orphan"
    )
    guard_checks: Mapped[list["GuardCheck"]] = relationship(
        "GuardCheck", back_populates="message", cascade="all, delete-orphan"
    )
    emotion_analyses: Mapped[list["EmotionAnalysis"]] = relationship(
        "EmotionAnalysis", back_populates="message", cascade="all, delete-orphan"
    )
