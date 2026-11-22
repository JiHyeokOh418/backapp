from datetime import timedelta, timezone
from sqlalchemy import BigInteger, Text, LargeBinary, Identity, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.model.rag_document_model import RagDocument

KST = timezone(timedelta(hours=9)) # UTC+9

# RAG chunk
class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    # `metadata`는 SQLAlchemy Base가 예약한 속성명이라 속성명만 바꾸고 DB 컬럼명은 metadata로 유지
    chunk_metadata: Mapped[dict | list | None] = mapped_column("metadata", JSONB)

    # 관계
    document: Mapped["RagDocument"] = relationship("RagDocument", back_populates="chunks")
