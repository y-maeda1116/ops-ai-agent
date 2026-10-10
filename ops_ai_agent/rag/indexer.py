"""ナレッジのインデックス構築ユースケース。"""

from pathlib import Path

from ops_ai_agent.adapters.json_vector_store import JsonVectorStore
from ops_ai_agent.domain.models import KnowledgeChunk
from ops_ai_agent.ports.embeddings import EmbeddingPort
from ops_ai_agent.rag.chunking import chunk_markdown


def build_index(knowledge_dir: Path, embedder: EmbeddingPort, output: Path) -> int:
    """knowledge_dir 配下の *.md をチャンク化・埋め込み・永続化する。"""
    drafts = [
        draft
        for md_path in sorted(knowledge_dir.rglob("*.md"))
        for draft in chunk_markdown(
            md_path.read_text(encoding="utf-8"), source=str(md_path)
        )
    ]
    embeddings = embedder.embed_documents([draft.text for draft in drafts])
    chunks = [
        KnowledgeChunk(
            id=draft.id,
            source=draft.source,
            title=draft.title,
            text=draft.text,
            metadata=draft.metadata,
            embedding=embedding,
        )
        for draft, embedding in zip(drafts, embeddings, strict=True)
    ]
    JsonVectorStore(output).save(chunks)
    return len(chunks)
