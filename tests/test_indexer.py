"""build_index のテスト。"""

from ops_ai_agent.adapters.json_vector_store import JsonVectorStore
from ops_ai_agent.rag.indexer import build_index, update_index
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


class CountingEmbedder:
    """埋め込み件数を記録する FakeEmbedder ラッパ。"""

    def __init__(self) -> None:
        self.embedded: list[str] = []
        self._fake = FakeEmbedder()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return self._fake.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._fake.embed_query(text)


def _write(path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_update_index_embeds_only_changed_docs(tmp_path):
    knowledge = tmp_path / "knowledge"
    (knowledge / "incidents").mkdir(parents=True)
    _write(knowledge / "incidents" / "a.md", _DOC)
    _write(knowledge / "incidents" / "b.md", _DOC.replace("INC-001", "INC-002"))
    output = tmp_path / "data" / "index.json"

    full_count = build_index(knowledge, FakeEmbedder(), output)
    embedder = CountingEmbedder()
    assert update_index(knowledge, embedder, output) == full_count
    assert embedder.embedded == []  # 変更なし→再埋め込みゼロ


def test_update_index_reembeds_only_modified_doc(tmp_path):
    knowledge = tmp_path / "knowledge"
    (knowledge / "incidents").mkdir(parents=True)
    path_a = knowledge / "incidents" / "a.md"
    _write(path_a, _DOC)
    _write(knowledge / "incidents" / "b.md", _DOC.replace("INC-001", "INC-002"))
    output = tmp_path / "data" / "index.json"
    build_index(knowledge, FakeEmbedder(), output)

    embedder = CountingEmbedder()
    modified = _DOC.replace("アップストリームタイムアウト。", "DBコネクション枯渇。")
    _write(path_a, modified)
    update_index(knowledge, embedder, output)
    # a.md のチャンク分のみ再埋め込み（無変更の症状チャンクも含む）
    assert len(embedder.embedded) == 2
    assert any("DBコネクション枯渇" in text for text in embedder.embedded)


def test_update_index_drops_deleted_docs(tmp_path):
    knowledge = tmp_path / "knowledge"
    (knowledge / "incidents").mkdir(parents=True)
    _write(knowledge / "incidents" / "a.md", _DOC)
    _write(knowledge / "incidents" / "b.md", _DOC.replace("INC-001", "INC-002"))
    output = tmp_path / "data" / "index.json"
    build_index(knowledge, FakeEmbedder(), output)

    (knowledge / "incidents" / "b.md").unlink()
    count = update_index(knowledge, CountingEmbedder(), output)
    assert count == 2  # a.md のチャンク2件のみ
    sources = {chunk.source for chunk in JsonVectorStore(output).load()}
    assert all(source.endswith("a.md") for source in sources)


def test_update_index_adds_only_new_docs(tmp_path):
    knowledge = tmp_path / "knowledge"
    (knowledge / "incidents").mkdir(parents=True)
    _write(knowledge / "incidents" / "a.md", _DOC)
    output = tmp_path / "data" / "index.json"
    build_index(knowledge, FakeEmbedder(), output)

    embedder = CountingEmbedder()
    _write(knowledge / "incidents" / "c.md", _DOC.replace("INC-001", "INC-003"))
    update_index(knowledge, embedder, output)
    assert len(embedder.embedded) == 2
    assert all("INC-003" in text for text in embedder.embedded)


def test_update_index_rebuilds_when_existing_index_has_no_hash(tmp_path):
    knowledge = tmp_path / "knowledge"
    (knowledge / "incidents").mkdir(parents=True)
    _write(knowledge / "incidents" / "a.md", _DOC)
    output = tmp_path / "data" / "index.json"
    build_index(knowledge, FakeEmbedder(), output)

    # 旧形式（content_hash無し）のインデックスを再現する
    index_file = output
    import json as _json

    payload = _json.loads(index_file.read_text(encoding="utf-8"))
    for chunk in payload["chunks"]:
        chunk["metadata"].pop("content_hash", None)
    index_file.write_text(_json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    embedder = CountingEmbedder()
    count = update_index(knowledge, embedder, output)
    assert count == 2
    assert len(embedder.embedded) == 2  # ハッシュ無し→全件再構築
