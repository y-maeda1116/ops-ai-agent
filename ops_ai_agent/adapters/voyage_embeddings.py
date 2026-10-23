"""Voyage AI 埋め込みアダプタ（REST直呼び・httpx使用）。"""

import time
from collections.abc import Callable

import httpx

from ops_ai_agent.adapters.retry import call_with_retry
from ops_ai_agent.config import Settings

_BASE_URL = "https://api.voyageai.com/v1"
_MAX_BATCH = 32
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class EmbeddingAuthError(Exception):
    """Voyage APIキーが無効（401）。"""


class _RetryableStatusError(Exception):
    """再試行対象のHTTPステータス（429/5xx）を表す内部シグナル。"""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response


class VoyageEmbedder:
    """EmbeddingPort の Voyage AI 実装。"""

    def __init__(
        self,
        client: httpx.Client,
        api_key: str,
        *,
        model: str = "voyage-3.5-lite",
        max_retries: int = 2,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model
        self._max_retries = max_retries
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
        def call() -> list[list[float]]:
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
            if response.status_code in _RETRYABLE_STATUS:
                raise _RetryableStatusError(response)
            response.raise_for_status()
            payload = response.json()
            data = sorted(payload["data"], key=lambda item: item["index"])
            return [item["embedding"] for item in data]

        try:
            return call_with_retry(
                call,
                max_retries=self._max_retries,
                retryable=lambda exc: isinstance(exc, _RetryableStatusError),
                sleeper=self._sleeper,
            )
        except _RetryableStatusError as exc:
            # 再試行を使い切ったため、元のHTTPステータスエラーとして送出する
            exc.response.raise_for_status()
            raise  # pragma: no cover


def create_voyage_embedder(settings: Settings) -> VoyageEmbedder:
    """設定から VoyageEmbedder を構築する（キー未設定時は ValueError）。"""
    return VoyageEmbedder(
        httpx.Client(timeout=30.0),
        settings.require_voyage_key(),
        model=settings.embedding_model,
        max_retries=settings.max_retries,
    )
