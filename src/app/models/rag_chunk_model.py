from sqlalchemy import BigInteger, Text, Identity, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

# PostgreSQL의 Base를 상속받아서 서버가 켜질 때 동기화시킨다.
from app.infrastructure.postgresql import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.rag_document_model import RagDocument

EMBEDDING_DIM = 768

class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)  # PK
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rag_documents.id", ondelete="RESTRICT"), nullable=False
    )  # 원문 문서
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 조각 본문
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)  # pgvector vector(N)
    # metadata는 Declarative 예약어라 속성 이름만 chunk_metadata로 두고, DB 컬럼 이름은 metadata
    chunk_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)  # 메타데이터

    # 관계
    document: Mapped["RagDocument"] = relationship("RagDocument")
