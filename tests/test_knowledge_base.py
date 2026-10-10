"""KnowledgeBase のテスト。"""

from ops_ai_agent.adapters.json_vector_store import JsonVectorStore
from ops_ai_agent.adapters.knowledge_base import KnowledgeBase
from tests.fakes import FakeEmbedder

_RUNBOOK = """---
service: api-gateway
title: api-gateway対応手順
---

1. アップストリーム確認
2. ロールバック判断
"""


def _base(tmp_path, with_runbook: bool = True):
    store = JsonVectorStore(tmp_path / "index.json")
    runbook_dir = tmp_path / "runbooks"
    runbook_dir.mkdir()
    if with_runbook:
        (runbook_dir / "api-gateway.md").write_text(_RUNBOOK, encoding="utf-8")
    return KnowledgeBase(store, FakeEmbedder(), runbook_dir)


def test_search_empty_index_returns_empty(tmp_path):
    base = _base(tmp_path)
    assert base.search("5xx 急増") == []


def test_search_returns_hits_for_indexed_text(tmp_path):
    store = JsonVectorStore(tmp_path / "index.json")
    from ops_ai_agent.domain.models import KnowledgeChunk

    text = "症状: 5xx急増 原因: アップストリームタイムアウト"
    embedding = FakeEmbedder().embed_query(text)
    store.save(
        [
            KnowledgeChunk(
                id="inc-001.md#0",
                source="incidents/inc-001.md",
                title="api-gateway 5xx急増",
                text=text,
                metadata={"id": "INC-001"},
                embedding=embedding,
            )
        ]
    )
    base = KnowledgeBase(store, FakeEmbedder(), tmp_path / "runbooks")
    hits = base.search(text, top_k=3)
    assert len(hits) == 1
    assert hits[0].chunk.metadata["id"] == "INC-001"
    assert hits[0].score > 0.9


def test_get_runbook_matches_service_case_insensitive(tmp_path):
    base = _base(tmp_path)
    runbook = base.get_runbook("API-Gateway")
    assert runbook is not None
    assert "アップストリーム確認" in runbook


def test_get_runbook_missing_returns_none(tmp_path):
    base = _base(tmp_path)
    assert base.get_runbook("no-such-service") is None
