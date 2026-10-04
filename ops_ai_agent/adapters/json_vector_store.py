"""軽量JSONベクタストア（コサイン類似度検索・JSON永続）。"""

import math
from pathlib import Path

from pydantic import BaseModel, Field

from ops_ai_agent.domain.models import KnowledgeChunk, SearchHit


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """コサイン類似度。ゼロベクトル場合は 0.0 を返す。"""
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (norm_a * norm_b)


def search_chunks(
    chunks: list[KnowledgeChunk], query_embedding: list[float], top_k: int
) -> list[SearchHit]:
    """類似度降順（同率は id 昇順）に上位 top_k 件を返す。"""
    scored = [
        SearchHit(
            chunk=chunk, score=cosine_similarity(query_embedding, chunk.embedding)
        )
        for chunk in chunks
    ]
    scored.sort(key=lambda hit: (-hit.score, hit.chunk.id))
    return scored[:top_k]


class _IndexFile(BaseModel):
    version: int = 1
    chunks: list[KnowledgeChunk] = Field(default_factory=list)


class JsonVectorStore:
    """data/index.json の永続を担うアダプタ。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def save(self, chunks: list[KnowledgeChunk]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = _IndexFile(chunks=chunks)
        self._path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")

    def load(self) -> list[KnowledgeChunk]:
        if not self._path.exists():
            return []
        try:
            payload = _IndexFile.model_validate_json(
                self._path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            msg = f"index ファイル {self._path} の読み込みに失敗しました: {exc}"
            raise ValueError(msg) from exc
        return payload.chunks
