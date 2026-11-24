from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, Text, DateTime, Identity, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chat_session_model import ChatSession

KST = timezone(timedelta(hours=9)) # UTC+9

class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )  # 세션 ID (세션 1개당 요약 1개)
    context_summary: Mapped[str] = mapped_column(Text, nullable=False)  # 세션 종료 후 1회 사후 요약
    mood_summary: Mapped[dict] = mapped_column(JSONB, nullable=False)  # dominant, distribution(6분류), intensity, evidence_seqs
    topics: Mapped[dict | None] = mapped_column(JSONB)  # 주제
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(KST)
    )  # 생성 시각
    chief_complaint: Mapped[str | None] = mapped_column(Text)  # 사전 문진 세션의 주호소 요약
    findings: Mapped[list | None] = mapped_column(JSONB)  # [{label, evidence}] 참고용. 진단 아님

    # 관계
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="summary")
