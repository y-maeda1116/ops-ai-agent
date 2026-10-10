"""ナレッジ検索ポート。"""

from typing import Protocol, runtime_checkable

from ops_ai_agent.domain.models import SearchHit


@runtime_checkable
class KnowledgeRetrieverPort(Protocol):
    def search(self, query: str, *, top_k: int = 3) -> list[SearchHit]: ...

    def get_runbook(self, service: str) -> str | None: ...
