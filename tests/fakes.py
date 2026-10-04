"""テスト用のポート実装ダブル。"""

import hashlib

from ops_ai_agent.ports.llm import LlmResponse, Message, ToolSpec


class FakeLlm:
    """スクリプト化された応答を順に返す LlmPort 実装。"""

    def __init__(self, responses: list[LlmResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        output_schema: dict[str, object] | None = None,
    ) -> LlmResponse:
        self.requests.append(
            {
                "system": system,
                "messages": [m.model_copy(deep=True) for m in messages],
                "tools": list(tools) if tools is not None else None,
                "output_schema": output_schema,
            }
        )
        if not self._responses:
            raise AssertionError("FakeLlm: 予期しない追加呼び出し（応答を使い切った）")
        return self._responses.pop(0)


class FakeEmbedder:
    """sha256ベースの決定論ベクトルを返す EmbeddingPort 実装。"""

    def _embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [byte / 255.0 for byte in digest[:16]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
