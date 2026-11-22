from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Text, DateTime, Identity, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.chat_session_model import ChatSession

KST = timezone(timedelta(hours=9)) # UTC+9

# 세션 사후 요약 (chat_sessions와 1:1)
class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    context_summary: Mapped[str | None] = mapped_column(Text)
    mood_summary: Mapped[dict | list | None] = mapped_column(JSONB)
    topics: Mapped[dict | list | None] = mapped_column(JSONB)
    chief_complaint: Mapped[str | None] = mapped_column(Text) # 주호소
    findings: Mapped[dict | list | None] = mapped_column(JSONB) # AI 참고 소견
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계 (chat_sessions.summary_id도 이 테이블을 가리키므로 foreign_keys 지정)
    session: Mapped["ChatSession"] = relationship(
        "ChatSession", back_populates="summary", foreign_keys=[session_id]
    )
