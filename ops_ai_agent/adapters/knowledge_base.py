"""ナレッジベース（Retrieverポート実装）。"""

from pathlib import Path

import frontmatter

from ops_ai_agent.adapters.json_vector_store import JsonVectorStore, search_chunks
from ops_ai_agent.domain.models import SearchHit
from ops_ai_agent.ports.embeddings import EmbeddingPort


class KnowledgeBase:
    """JSONストア＋埋め込みによるナレッジ検索。"""

    def __init__(
        self, store: JsonVectorStore, embedder: EmbeddingPort, runbook_dir: Path
    ) -> None:
        self._chunks = store.load()
        self._embedder = embedder
        self._runbook_dir = runbook_dir

    def search(self, query: str, *, top_k: int = 3) -> list[SearchHit]:
        query_embedding = self._embedder.embed_query(query)
        return search_chunks(self._chunks, query_embedding, top_k)

    def get_runbook(self, service: str) -> str | None:
        for path in sorted(self._runbook_dir.glob("*.md")):
            post = frontmatter.load(path)
            if str(post.get("service", "")).lower() == service.lower():
                return path.read_text(encoding="utf-8")
        return None
