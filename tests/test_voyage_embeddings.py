"""Voyage埋め込みアダプタのテスト（MockTransport使用、実API不使用）。"""

import json

import httpx
import pytest

from ops_ai_agent.adapters.voyage_embeddings import (
    EmbeddingAuthError,
    VoyageEmbedder,
    create_voyage_embedder,
)


def _ok_response(indices: list[int]) -> httpx.Response:
    data = [{"index": i, "embedding": [float(i), 1.0]} for i in indices]
    return httpx.Response(200, json={"data": data})


def _embedder(handler) -> VoyageEmbedder:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return VoyageEmbedder(client, "pa-test", sleeper=lambda _s: None)


def test_embed_documents_maps_input_type_document():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content.decode())
        return _ok_response([0])

    embedder = _embedder(handler)
    vectors = embedder.embed_documents(["hello"])
    assert vectors == [[0.0, 1.0]]
    assert captured["url"] == "https://api.voyageai.com/v1/embeddings"
    assert captured["auth"] == "Bearer pa-test"
    assert captured["body"] == {
        "model": "voyage-3.5-lite",
        "input": ["hello"],
        "input_type": "document",
    }


def test_embed_query_uses_query_input_type():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["input_type"] == "query"
        return _ok_response([0])

    embedder = _embedder(handler)
    assert embedder.embed_query("q") == [0.0, 1.0]


def test_response_reordered_by_index():
    def handler(_request: httpx.Request) -> httpx.Response:
        return _ok_response([2, 0, 1])

    embedder = _embedder(handler)
    vectors = embedder.embed_documents(["a", "b", "c"])
    assert vectors == [[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]]


def test_batches_split_at_32():
    sizes: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        sizes.append(body["input"])
        return _ok_response(list(range(len(body["input"]))))

    embedder = _embedder(handler)
    vectors = embedder.embed_documents([f"t{i}" for i in range(70)])
    assert [len(batch) for batch in sizes] == [32, 32, 6]
    assert len(vectors) == 70


def test_retries_on_429_then_succeeds():
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, json={"error": "rate"})
        return _ok_response([0])

    embedder = _embedder(handler)
    assert embedder.embed_query("q") == [0.0, 1.0]
    assert len(calls) == 3


def test_gives_up_after_two_retries():
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, json={"error": "unavailable"})

    embedder = _embedder(handler)
    with pytest.raises(httpx.HTTPStatusError):
        embedder.embed_query("q")
    assert len(calls) == 3


def test_401_raises_auth_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    embedder = _embedder(handler)
    with pytest.raises(EmbeddingAuthError):
        embedder.embed_query("q")


def test_create_voyage_embedder_requires_key(tmp_path, monkeypatch):
    from ops_ai_agent.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError, match="VOYAGE_API_KEY"):
        create_voyage_embedder(settings)
