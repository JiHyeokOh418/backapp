from datetime import timedelta, timezone
from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.chat_session_model import ChatSession
    from app.model.rag_document_model import RagDocument

KST = timezone(timedelta(hours=9)) # UTC+9

# 세션 내 상담문서 (연결 테이블, 복합 PK)
class SessionDocument(Base):
    __tablename__ = "session_documents"

    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rag_documents.id", ondelete="CASCADE"), primary_key=True
    )

    # 관계
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="session_documents")
    document: Mapped["RagDocument"] = relationship("RagDocument", back_populates="session_documents")
