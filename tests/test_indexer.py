"""build_index のテスト。"""

from ops_ai_agent.adapters.json_vector_store import JsonVectorStore
from ops_ai_agent.rag.indexer import build_index
from tests.fakes import FakeEmbedder

_DOC = """---
id: INC-001
title: api-gateway 5xx急増
service: api-gateway
---

## 症状
5xx が急増。

## 原因
アップストリームタイムアウト。
"""


def test_build_index_chunks_embeds_and_saves(tmp_path):
    knowledge = tmp_path / "knowledge"
    (knowledge / "incidents").mkdir(parents=True)
    (knowledge / "incidents" / "inc-001.md").write_text(_DOC, encoding="utf-8")
    output = tmp_path / "data" / "index.json"

    count = build_index(knowledge, FakeEmbedder(), output)

    assert count == 2
    store = JsonVectorStore(output)
    chunks = store.load()
    assert len(chunks) == 2
    assert chunks[0].metadata["id"] == "INC-001"
    assert len(chunks[0].embedding) == 16
    assert chunks[0].source.endswith("inc-001.md")


def test_build_index_empty_dir_returns_zero(tmp_path):
    output = tmp_path / "index.json"
    assert build_index(tmp_path, FakeEmbedder(), output) == 0
    assert output.exists()
