from datetime import datetime, timedelta, timezone
from sqlalchemy import BigInteger, String, DateTime, Identity
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.session_document_model import SessionDocument
    from app.model.rag_chunk_model import RagChunk

KST = timezone(timedelta(hours=9)) # UTC+9

# RAG문서
class RagDocument(Base):
    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(KST)
    )

    # 관계
    # cascade: RagDocument가 삭제되면 참조된 테이블을 모두 같이 연쇄삭제
    session_documents: Mapped[list["SessionDocument"]] = relationship(
        "SessionDocument", back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["RagChunk"]] = relationship(
        "RagChunk", back_populates="document", cascade="all, delete-orphan"
    )
