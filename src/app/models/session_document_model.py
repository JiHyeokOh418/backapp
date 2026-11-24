from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chat_session_model import ChatSession
    from app.models.rag_document_model import RagDocument

class SessionDocument(Base):
    __tablename__ = "session_documents"

    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), primary_key=True
    )  # 상담 세션
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rag_documents.id", ondelete="RESTRICT"), primary_key=True
    )  # 이 세션에서 검색할 RAG 문서

    # 관계
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="session_documents")
    document: Mapped["RagDocument"] = relationship("RagDocument")
