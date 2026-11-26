from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, defer
from app.infrastructure.postgresql import get_postgresql_db
from fastapi import Depends

# 모델, ORM
from app.models.rag_document_model import RagDocument
from app.models.rag_chunk_model import RagChunk


# RAG 문서/청크 DB 접근 (pgvector)
# - llm_repository와 같이 함수 안에서 commit하지 않는다. (flush까지만)
#   replace(삭제 후 재적재)를 한 트랜잭션으로 묶어야 해서, commit / rollback 시점은 service가 정한다.
# - source(datas/ 기준 상대 경로)가 중복 판별 키다. 모델에 unique 제약이 없으므로 조회는 항상 목록으로 받는다.
# - 임베딩 계산(외부 API)은 트랜잭션 밖에서 끝낸 뒤 넘긴다. 이 레포지토리는 저장과 검색만 한다.
class RagRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db


    # 트랜잭션
    # 0-1. 확정
    async def commit(self) -> None:
        await self.db.commit()


    # 0-2. 되돌리기
    async def rollback(self) -> None:
        await self.db.rollback()


    # 문서
    # 1. source로 문서 조회
    # - 정상이면 0건 또는 1건이지만, 제약이 없어 중복이 생겼을 수 있으므로 목록으로 반환한다.
    #   (replace 시 전부 지우면 중복도 함께 정리된다)
    async def find_documents_by_source(self, source: str) -> list[RagDocument]:
        query = (
            select(RagDocument)
            .where(RagDocument.source == source)
            .order_by(RagDocument.id)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 2. 전체 문서 조회 (prune 대상 계산용)
    # - service가 폴더의 source 목록과 비교해서, 폴더에 없는 문서의 id를 delete_documents에 넘긴다.
    async def find_all_documents(self) -> list[RagDocument]:
        query = select(RagDocument).order_by(RagDocument.id)
        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 3. 문서 생성
    # - flush하면 id가 채워져서, 같은 트랜잭션 안에서 바로 청크의 document_id로 쓸 수 있다.
    async def create_document(self, source: str, title: str) -> RagDocument:
        document = RagDocument(source=source, title=title)
        self.db.add(document)
        await self.db.flush()
        return document


    # 4. 문서 삭제 (청크 포함)
    # - rag_chunks.document_id가 ondelete="RESTRICT"라서 청크를 먼저 지우고 문서를 지운다.
    # - 반환: 지운 문서 수
    async def delete_documents(self, document_ids: list[int]) -> int:
        if not document_ids:
            return 0

        await self.db.execute(
            delete(RagChunk).where(RagChunk.document_id.in_(document_ids))
        )
        result = await self.db.execute(
            delete(RagDocument).where(RagDocument.id.in_(document_ids))
        )
        return result.rowcount


    # 청크
    # 5. 청크 일괄 생성
    # - service가 rag.build_chunks() 결과로 RagChunk(document_id, content, embedding, chunk_metadata)를 만들어 넘긴다.
    async def create_chunks(self, chunks: list[RagChunk]) -> list[RagChunk]:
        if not chunks:
            return []

        self.db.add_all(chunks)
        await self.db.flush()
        return chunks


    # 6. top-k 유사 청크 검색 (코사인 거리, 작을수록 가깝다)
    # - query_embedding은 문서와 같은 임베딩 모델로 만든 벡터여야 한다. (rag.embed_query)
    # - max_distance를 주면 그보다 먼 청크는 뺀다. (관련 없는 청크가 프롬프트에 들어가는 것을 막는다)
    # - 프롬프트에 출처(문서 제목)를 붙일 수 있도록 document를 함께 불러온다.
    # - document_ids를 주면 그 문서의 청크에서만 찾는다. None이면 전체 문서 (세션에 지정된 문서가 없을 때)
    # - 반환: [(청크, 거리)] 가까운 순
    async def search_chunks(
        self,
        query_embedding: list[float],
        top_k: int,
        max_distance: float | None = None,
        document_ids: list[int] | None = None,
    ) -> list[tuple[RagChunk, float]]:
        distance = RagChunk.embedding.cosine_distance(query_embedding)

        query = (
            select(RagChunk, distance.label("distance"))
            .options(
                selectinload(RagChunk.document),
                defer(RagChunk.embedding),  # 프롬프트에는 본문만 쓰므로 768차원 벡터는 읽지 않는다
            )
            .order_by(distance)
            .limit(top_k)
        )
        if max_distance is not None:
            query = query.where(distance <= max_distance)
        if document_ids is not None:
            query = query.where(RagChunk.document_id.in_(document_ids))

        result = await self.db.execute(query)
        return [(row.RagChunk, float(row.distance)) for row in result.all()]



# 주입 팩토리 메서드
def get_rag_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return RagRepository(db)
