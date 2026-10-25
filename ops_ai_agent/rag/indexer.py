"""ナレッジのインデックス構築ユースケース。"""

import hashlib
from pathlib import Path

from ops_ai_agent.adapters.json_vector_store import JsonVectorStore
from ops_ai_agent.domain.models import KnowledgeChunk
from ops_ai_agent.ports.embeddings import EmbeddingPort
from ops_ai_agent.rag.chunking import chunk_markdown


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_chunks(
    md_path: Path, embedder: EmbeddingPort, content_hash: str
) -> list[KnowledgeChunk]:
    drafts = chunk_markdown(md_path.read_text(encoding="utf-8"), source=str(md_path))
    embeddings = embedder.embed_documents([draft.text for draft in drafts])
    return [
        KnowledgeChunk(
            id=draft.id,
            source=draft.source,
            title=draft.title,
            text=draft.text,
            metadata={**draft.metadata, "content_hash": content_hash},
            embedding=embedding,
        )
        for draft, embedding in zip(drafts, embeddings, strict=True)
    ]


def build_index(knowledge_dir: Path, embedder: EmbeddingPort, output: Path) -> int:
    """knowledge_dir 配下の *.md を全件チャンク化・埋め込み・永続化する。"""
    chunks: list[KnowledgeChunk] = []
    for md_path in sorted(knowledge_dir.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        chunks.extend(_build_chunks(md_path, embedder, _content_hash(text)))
    JsonVectorStore(output).save(chunks)
    return len(chunks)


def update_index(knowledge_dir: Path, embedder: EmbeddingPort, output: Path) -> int:
    """差分だけ再埋め込みしてインデックスを更新する。

    ドキュメント単位の content_hash で変更を検出する。既存インデックスに
    ハッシュが無い（旧形式・全件）場合は全件再構築となる。
    """
    store = JsonVectorStore(output)
    existing = store.load()
    hash_by_source = {
        chunk.source: chunk.metadata.get("content_hash", "") for chunk in existing
    }

    chunks: list[KnowledgeChunk] = []
    for md_path in sorted(knowledge_dir.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        digest = _content_hash(text)
        source = str(md_path)
        if hash_by_source.get(source) == digest:
            # 無変更: 既存チャンク（埋め込み済み）をそのまま引き継ぐ
            chunks.extend(chunk for chunk in existing if chunk.source == source)
        else:
            chunks.extend(_build_chunks(md_path, embedder, digest))

    # 削除されたドキュメントのチャンクは、ディスクに無いソースを
    # 出力に含めないことで自然に落ちる
    store.save(chunks)
    return len(chunks)
