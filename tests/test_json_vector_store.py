"""JSONベクタストアのテスト。"""

import pytest

from ops_ai_agent.adapters.json_vector_store import (
    JsonVectorStore,
    cosine_similarity,
    search_chunks,
)
from ops_ai_agent.domain.models import KnowledgeChunk


def _chunk(cid: str, embedding: list[float]) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=cid,
        source=f"src/{cid}.md",
        title=cid,
        text="text",
        metadata={},
        embedding=embedding,
    )


def test_cosine_similarity_identical_and_orthogonal():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector_safe():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_search_chunks_orders_by_similarity():
    chunks = [
        _chunk("a", [1.0, 0.0]),
        _chunk("b", [0.9, 0.1]),
        _chunk("c", [0.0, 1.0]),
    ]
    hits = search_chunks(chunks, [1.0, 0.0], top_k=2)
    assert [h.chunk.id for h in hits] == ["a", "b"]
    assert hits[0].score == pytest.approx(1.0)


def test_search_chunks_topk_larger_than_pool():
    hits = search_chunks([_chunk("a", [1.0])], [1.0], top_k=5)
    assert len(hits) == 1


def test_store_roundtrip(tmp_path):
    store = JsonVectorStore(tmp_path / "index.json")
    chunks = [_chunk("a", [0.1, 0.2]), _chunk("b", [0.3])]
    store.save(chunks)
    loaded = store.load()
    assert loaded == chunks


def test_store_load_missing_file_returns_empty(tmp_path):
    store = JsonVectorStore(tmp_path / "absent.json")
    assert store.load() == []


def test_store_load_corrupt_file_raises(tmp_path):
    target = tmp_path / "index.json"
    target.write_text("{invalid json", encoding="utf-8")
    with pytest.raises(ValueError, match="index"):
        JsonVectorStore(target).load()
