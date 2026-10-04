"""Voyage AI 埋め込みアダプタ（REST直呼び・httpx使用）。"""

import time
from collections.abc import Callable

import httpx

from ops_ai_agent.config import Settings

_BASE_URL = "https://api.voyageai.com/v1"
_MAX_BATCH = 32
_MAX_RETRIES = 2
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class EmbeddingAuthError(Exception):
    """Voyage APIキーが無効（401）。"""


class VoyageEmbedder:
    """EmbeddingPort の Voyage AI 実装。"""

    def __init__(
        self,
        client: httpx.Client,
        api_key: str,
        *,
        model: str = "voyage-3.5-lite",
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model
        self._sleeper = sleeper

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for start in range(0, len(texts), _MAX_BATCH):
            batch = texts[start : start + _MAX_BATCH]
            results.extend(self._request(batch, "document"))
        return results

    def embed_query(self, text: str) -> list[float]:
        return self._request([text], "query")[0]

    def _request(self, inputs: list[str], input_type: str) -> list[list[float]]:
        for attempt in range(_MAX_RETRIES + 1):
            response = self._client.post(
                f"{_BASE_URL}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "input": inputs,
                    "input_type": input_type,
                },
            )
            if response.status_code == 401:
                raise EmbeddingAuthError("Voyage APIキーが無効です（401）")
            if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                self._sleeper(0.5 * (2**attempt))
                continue
            response.raise_for_status()
            payload = response.json()
            data = sorted(payload["data"], key=lambda item: item["index"])
            return [item["embedding"] for item in data]
        raise RuntimeError("到達不能: 再試行ループを抜けました")


def create_voyage_embedder(settings: Settings) -> VoyageEmbedder:
    """設定から VoyageEmbedder を構築する（キー未設定時は ValueError）。"""
    return VoyageEmbedder(
        httpx.Client(timeout=30.0),
        settings.require_voyage_key(),
        model=settings.embedding_model,
    )
