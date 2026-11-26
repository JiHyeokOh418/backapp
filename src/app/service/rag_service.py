import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

from fastapi import Depends

from app.llm_call import rag
from app.models.rag_chunk_model import RagChunk
from app.repository.rag_repository import RagRepository, get_rag_repository

# 검색 기본값
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
# 코사인 거리(0~2, 작을수록 가깝다) 상한. 비워 두면 거리로 거르지 않는다.
# TODO: 임시값. 실제 데이터로 검색해 보고 확정 필요
_max_distance_env = os.getenv("RAG_MAX_DISTANCE")
RAG_MAX_DISTANCE = float(_max_distance_env) if _max_distance_env else None


# 적재 결과 (source 목록)
@dataclass
class IngestResult:
    created: list[str] = field(default_factory=list)  # 새로 적재
    replaced: list[str] = field(default_factory=list)  # 지우고 다시 적재 (replace=True)
    skipped: list[str] = field(default_factory=list)  # 이미 있어서 건너뜀
    pruned: list[str] = field(default_factory=list)  # 폴더에 없어서 삭제 (prune=True)


# 검색 결과 1건 (프롬프트 구성용)
# - ORM 객체 대신 값만 넘겨서, 호출하는 쪽이 세션/지연 로딩을 신경 쓰지 않게 한다.
@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    title: str  # 문서 제목 (출처 표시용)
    source: str | None
    content: str
    distance: float  # 코사인 거리, 작을수록 가깝다


# RAG 적재 / 검색
# - 문서 읽기, 분할, 임베딩은 app.llm_call.rag, DB 저장과 검색은 RagRepository가 한다. 여기서는 순서와 트랜잭션을 정한다.
# - 임베딩(외부 API 호출)은 트랜잭션 밖에서 끝낸 뒤, 저장만 짧은 트랜잭션으로 묶는다.
#
# 적재 규칙
# - 중복 판별 키는 source(datas/ 기준 상대 경로). 모델에 unique 제약이 없으므로 코드로 보장한다.
# - 기본: 없는 source만 적재하고 이미 있으면 건너뛴다.
# - replace=True: 이미 있는 source도 청크 -> 문서 순으로 지우고 다시 넣는다. (삭제와 재적재를 한 트랜잭션으로)
# - prune=True: DB에는 있는데 폴더에 없는 source의 문서와 청크를 지운다. (파일 이름 변경, 삭제 반영)
#   prune은 datas/ 폴더를 기준 데이터로 본다. 다른 경로로 넣는 문서가 생기면 범위를 다시 정해야 한다.
# - 임베딩 모델이나 청크 설정이 바뀌면 replace=True로 전체 재적재한다. (청크 metadata에 설정값이 남아 있다)
class RagService:

    def __init__(self, repo: RagRepository):
        self.repo = repo


    # 예외가 나면 rollback하고 다시 던진다.
    async def _rollback_and_raise(self, error: Exception) -> NoReturn:
        await self.repo.rollback()
        raise error


    # 1. 적재 (별도 스크립트에서 호출. 서버 시작 시 자동 실행하지 않는다)
    # - 문서 1건마다 트랜잭션을 따로 둔다. 중간에 실패하면 그 문서만 되돌리고 예외를 다시 던진다.
    #   (이미 commit된 앞 문서는 남는다. 다시 실행하면 남은 문서부터 이어서 적재된다)
    async def ingest(
        self,
        replace: bool = False,
        prune: bool = False,
        data_dir: Path = rag.DATA_DIR,
    ) -> IngestResult:
        result = IngestResult()

        # 1-1. 폴더의 문서 읽기 (파일 I/O라 스레드에서 실행)
        documents = await asyncio.to_thread(rag.load_documents, data_dir)

        # 폴더를 못 읽었거나 비어 있는데 prune하면 DB 문서가 전부 지워진다. 그 경우는 멈춘다.
        if prune and not documents:
            raise ValueError(f"{data_dir}에서 적재할 문서를 찾지 못해 prune을 중단합니다.")

        # 1-2. DB의 기존 문서 (source -> 문서 id 목록. 중복이 있으면 id가 여러 개)
        existing_ids_by_source: dict[str, list[int]] = {}
        try:
            for document in await self.repo.find_all_documents():
                if document.source is None:
                    continue  # 이 적재 경로로 들어온 문서가 아니다. 건드리지 않는다.
                existing_ids_by_source.setdefault(document.source, []).append(document.id)
        except Exception as error:
            await self._rollback_and_raise(error)

        # 조회로 열린 트랜잭션을 닫는다. (임베딩 API를 기다리는 동안 트랜잭션을 잡고 있지 않는다)
        await self.repo.rollback()

        # 1-3. 문서별 적재
        for document in documents:
            existing_ids = existing_ids_by_source.get(document.source, [])
            if existing_ids and not replace:
                result.skipped.append(document.source)
                continue

            # 임베딩은 트랜잭션 밖에서 (실패하면 DB는 그대로)
            chunk_data = await rag.build_chunks(document)
            if not chunk_data:
                result.skipped.append(document.source)
                continue

            try:
                if existing_ids:
                    await self.repo.delete_documents(existing_ids)

                created = await self.repo.create_document(source=document.source, title=document.title)
                await self.repo.create_chunks([
                    RagChunk(
                        document_id=created.id,
                        content=chunk.content,
                        embedding=chunk.embedding,
                        chunk_metadata=chunk.metadata,
                    )
                    for chunk in chunk_data
                ])
                await self.repo.commit()
            except Exception as error:
                await self._rollback_and_raise(error)

            (result.replaced if existing_ids else result.created).append(document.source)

        # 1-4. 폴더에 없는 source 정리
        if prune:
            folder_sources = {document.source for document in documents}
            stale_sources = sorted(set(existing_ids_by_source) - folder_sources)
            if stale_sources:
                stale_ids = [
                    document_id
                    for source in stale_sources
                    for document_id in existing_ids_by_source[source]
                ]
                try:
                    await self.repo.delete_documents(stale_ids)
                    await self.repo.commit()
                except Exception as error:
                    await self._rollback_and_raise(error)
                result.pruned.extend(stale_sources)

        return result


    # 2. 검색 (상담 턴에서 프롬프트 구성 전에 호출)
    # - 질의는 문서와 같은 임베딩 모델로 만든다. (rag.embed_query)
    # - commit / rollback하지 않는다. 같은 요청의 다른 service와 DB 세션을 함께 쓰므로,
    #   여기서 rollback하면 그쪽에서 flush해 둔 변경까지 되돌아간다. 트랜잭션은 호출한 쪽이 정한다.
    # - 임베딩 API 오류는 그대로 던진다. 검색 실패를 어떻게 처리할지(RAG 없이 진행할지)는 호출한 쪽이 정한다.
    # - document_ids: 검색 범위. None이면 전체 문서, 목록이면 그 문서들만 (세션에 지정된 문서, session_documents)
    # - 반환: 가까운 순. 질의가 비어 있으면 빈 목록
    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        max_distance: float | None = None,
        document_ids: list[int] | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            return []

        query_embedding = await rag.embed_query(query)
        rows = await self.repo.search_chunks(
            query_embedding,
            top_k=top_k or RAG_TOP_K,
            max_distance=max_distance if max_distance is not None else RAG_MAX_DISTANCE,
            document_ids=document_ids,
        )

        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                title=chunk.document.title,
                source=chunk.document.source,
                content=chunk.content,
                distance=distance,
            )
            for chunk, distance in rows
        ]



# 레포지토리 주입 팩토리 함수
def get_rag_service(repo: RagRepository = Depends(get_rag_repository)):
    return RagService(repo)
