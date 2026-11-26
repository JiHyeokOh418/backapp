"""RAG 문서 적재 스크립트 (서버와 별도로 실행)

실행 위치: src/
    python -m app.llm_call.ingest                 # 새 문서만 적재 (이미 있는 source는 건너뜀)
    python -m app.llm_call.ingest --replace       # 이미 있는 source도 지우고 다시 적재
    python -m app.llm_call.ingest --prune         # datas/에 없는 source의 문서와 청크 삭제
    python -m app.llm_call.ingest --query "요즘 잠을 못 자요"   # 적재 후 검색 결과와 거리 확인

- 임베딩에 OPENAI_API_KEY 환경 변수가 필요하다.
- FastAPI의 Depends를 거치지 않으므로 DB 세션을 직접 열어 RagService에 넘긴다.
"""
import argparse
import asyncio
import sys
from pathlib import Path

import app.models  # noqa: F401  관계(relationship)가 걸린 모든 모델을 등록한다
from app.infrastructure.postgresql import AsyncSessionLocal, Base, engine
from app.llm_call import rag
from app.models.rag_chunk_model import RagChunk
from app.models.rag_document_model import RagDocument
from app.repository.rag_repository import RagRepository
from app.service.rag_service import IngestResult, RagService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG 문서를 rag_documents / rag_chunks에 적재한다.")
    parser.add_argument("--replace", action="store_true", help="이미 있는 source도 지우고 다시 적재")
    parser.add_argument("--prune", action="store_true", help="datas/에 없는 source의 문서와 청크 삭제")
    parser.add_argument("--data-dir", type=Path, default=rag.DATA_DIR, help="적재할 문서 폴더 (기본: llm_call/datas)")
    parser.add_argument("--query", help="적재 후 이 문장으로 검색해 결과와 거리를 출력")
    parser.add_argument("--top-k", type=int, default=None, help="--query 검색 개수 (기본: RAG_TOP_K)")
    parser.add_argument("--echo-sql", action="store_true", help="SQL 로그 출력 (기본은 끔. 임베딩 벡터가 그대로 찍힌다)")
    return parser.parse_args()


def _print_result(result: IngestResult) -> None:
    for label, sources in (
        ("적재", result.created),
        ("교체", result.replaced),
        ("건너뜀", result.skipped),
        ("삭제", result.pruned),
    ):
        print(f"{label} {len(sources)}건")
        for source in sources:
            print(f"  - {source}")


async def _run(args: argparse.Namespace) -> None:
    # postgresql.py의 엔진은 echo=True라 벡터 파라미터가 전부 로그에 찍힌다. 스크립트에서는 기본으로 끈다.
    engine.echo = args.echo_sql

    try:
        # 서버보다 먼저 실행해도 되도록 RAG 테이블만 만든다. (이미 있으면 건너뛴다)
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[RagDocument.__table__, RagChunk.__table__],
            )

        async with AsyncSessionLocal() as db:
            service = RagService(RagRepository(db))

            print(f"적재 폴더: {Path(args.data_dir).resolve()}")
            print(f"임베딩: {rag.EMBEDDING_MODEL} ({rag.EMBEDDING_DIM}차원), 청크 {rag.CHUNK_SIZE}/{rag.CHUNK_OVERLAP}")
            result = await service.ingest(replace=args.replace, prune=args.prune, data_dir=args.data_dir)
            _print_result(result)

            if args.query:
                print(f"\n검색: {args.query!r}")
                chunks = await service.retrieve(args.query, top_k=args.top_k, max_distance=None)
                await db.commit()
                if not chunks:
                    print("  결과 없음")
                for index, chunk in enumerate(chunks, start=1):
                    preview = chunk.content.replace("\n", " ")[:80]
                    print(f"  {index}. distance={chunk.distance:.4f} [{chunk.source}] {preview}")
    finally:
        await engine.dispose()


def main() -> None:
    # Windows 콘솔에서 한글이 깨지지 않게 출력 인코딩을 맞춘다. (--help 출력 전에)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
