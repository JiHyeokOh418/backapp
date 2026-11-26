import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding

# 차원은 rag_chunks.embedding 컬럼(Vector(N))과 반드시 같아야 하므로 모델 상수를 그대로 쓴다.
from app.models.rag_chunk_model import EMBEDDING_DIM

# RAG 준비 단계 (LlamaIndex 담당)
# - 문서 읽기 -> 청크 분할 -> 임베딩까지만 한다. DB 저장/검색은 rag_repository, 흐름 조합은 rag_service가 맡는다.
# - 저장소는 pgvector(rag_chunks)이며 ChromaDB, VectorStoreIndex는 쓰지 않는다.
#
# 적재 규칙 (rag_service에서 적용)
# - 중복 판별 키는 source(datas/ 기준 상대 경로). 이미 있으면 건너뛰고, replace=True일 때만 청크 -> 문서 순으로 지우고 다시 넣는다.
# - 임베딩 모델이나 청크 설정이 바뀌면 전체 재적재한다. 구분할 수 있게 청크 metadata에 설정값을 남긴다.

# 1. 설정값
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", Path(__file__).parent / "datas"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")  # dimensions를 지원하는 text-embedding-3 계열만 쓴다
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "512"))  # 토큰 기준
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
EMBEDDING_TIMEOUT = float(os.getenv("EMBEDDING_TIMEOUT", "30"))
EMBEDDING_MAX_RETRIES = int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))  # 라이브러리 기본값(10)은 요청 경로에서 너무 길다
SUPPORTED_EXTS = [".txt"]


# 2. 데이터 구조
@dataclass(frozen=True)
class LoadedDocument:
    source: str  # 중복 판별 키. datas/ 기준 상대 경로 (절대 경로는 PC마다 달라서 쓰지 않는다)
    title: str  # rag_documents.title
    text: str  # 원문 전체


@dataclass(frozen=True)
class ChunkData:
    content: str  # rag_chunks.content
    embedding: list[float]  # rag_chunks.embedding (EMBEDDING_DIM 차원)
    metadata: dict[str, Any] = field(default_factory=dict)  # rag_chunks.metadata (JSONB)


# 3. LlamaIndex 객체 (프로세스당 1개만 만든다)
@lru_cache(maxsize=1)
def get_embed_model() -> OpenAIEmbedding:
    # API 키는 OPENAI_API_KEY 환경 변수에서 자동으로 읽는다.
    return OpenAIEmbedding(
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIM,
        timeout=EMBEDDING_TIMEOUT,
        max_retries=EMBEDDING_MAX_RETRIES,
    )


@lru_cache(maxsize=1)
def get_splitter() -> SentenceSplitter:
    return SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


# 4. 문서 읽기
# - input_files를 주면 그 파일만, 없으면 data_dir 아래 지원 확장자 파일 전체를 읽는다.
# - 인코딩 오류를 조용히 무시하지 않도록 errors="strict"로 읽는다.
def load_documents(
    data_dir: Path = DATA_DIR,
    input_files: list[Path] | None = None,
) -> list[LoadedDocument]:
    data_dir = Path(data_dir).resolve()
    reader = SimpleDirectoryReader(
        input_dir=None if input_files else data_dir,
        input_files=[str(path) for path in input_files] if input_files else None,
        required_exts=SUPPORTED_EXTS,
        encoding="utf-8",
        errors="strict",
        raise_on_error=True,
    )

    # 리더가 한 파일을 여러 Document로 나눌 수 있으므로 파일 단위로 다시 합친다.
    texts_by_path: dict[Path, list[str]] = {}
    for document in reader.load_data():
        path = Path(document.metadata["file_path"]).resolve()
        texts_by_path.setdefault(path, []).append(document.text)

    loaded: list[LoadedDocument] = []
    for path in sorted(texts_by_path):
        text = "\n".join(texts_by_path[path]).strip()
        if not text:
            continue
        loaded.append(
            LoadedDocument(
                source=_to_source(path, data_dir),
                title=path.stem,
                text=text,
            )
        )
    return loaded


def _to_source(path: Path, data_dir: Path) -> str:
    # datas/ 밖의 파일이면 파일명만 쓴다.
    try:
        return path.relative_to(data_dir).as_posix()
    except ValueError:
        return path.name


# 5. 청크 분할
def split_text(text: str) -> list[str]:
    return [chunk.strip() for chunk in get_splitter().split_text(text) if chunk.strip()]


# 6. 임베딩
async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    embeddings = await get_embed_model().aget_text_embedding_batch(texts)
    for embedding in embeddings:
        _check_dim(embedding)
    return embeddings


async def embed_query(query: str) -> list[float]:
    # 질의는 문서와 같은 모델로 임베딩해야 거리 비교가 성립한다.
    embedding = await get_embed_model().aget_query_embedding(query)
    _check_dim(embedding)
    return embedding


def _check_dim(embedding: list[float]) -> None:
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"임베딩 차원이 {len(embedding)}입니다. rag_chunks.embedding은 {EMBEDDING_DIM}차원입니다."
        )


# 7. 적재용: 문서 1개 -> 청크 목록 (분할 + 임베딩 + 메타데이터)
# - metadata의 설정값은 재적재 대상을 가려내는 데 쓴다.
async def build_chunks(document: LoadedDocument) -> list[ChunkData]:
    contents = split_text(document.text)
    embeddings = await embed_texts(contents)
    return [
        ChunkData(
            content=content,
            embedding=embedding,
            metadata={
                "source": document.source,
                "chunk_index": index,
                "embedding_model": EMBEDDING_MODEL,
                "embedding_dim": EMBEDDING_DIM,
                "chunk_size": CHUNK_SIZE,
                "chunk_overlap": CHUNK_OVERLAP,
            },
        )
        for index, (content, embedding) in enumerate(zip(contents, embeddings))
    ]
