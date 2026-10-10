"""埋め込みポート。"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingPort(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...
