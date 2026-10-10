"""Markdownのチャンク化（frontmatter保持・見出し分割）。"""

from pathlib import Path

import frontmatter
from pydantic import BaseModel


class ChunkDraft(BaseModel):
    """埋め込み前のチャンク。"""

    id: str
    source: str
    title: str
    text: str
    metadata: dict[str, str]


def _metadata_lines(metadata: dict[str, str]) -> str:
    return "\n".join(
        f"{key}: {value}" for key, value in sorted(metadata.items()) if key != "title"
    )


def chunk_markdown(
    text: str, *, source: str, max_chars: int = 1500
) -> list[ChunkDraft]:
    """Markdownを frontmatter メタデータ付きのチャンク列へ分割する。"""
    post = frontmatter.loads(text)
    metadata = {
        str(key): ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        for key, value in post.metadata.items()
    }
    body = post.content.strip()

    title = metadata.get("title") or _first_heading(body) or Path(source).stem

    sections = _split_sections(body)
    header = _metadata_lines(metadata)
    drafts: list[ChunkDraft] = []
    for index, section in enumerate(sections):
        chunk_text = f"{header}\n\n{section}".strip()[:max_chars]
        drafts.append(
            ChunkDraft(
                id=f"{Path(source).name}#{index}",
                source=source,
                title=title,
                text=chunk_text,
                metadata=metadata,
            )
        )
    return drafts


def _first_heading(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _split_sections(body: str) -> list[str]:
    """`## ` 見出し単位に分割。

    最初の `## ` 見出しより前の序文（文書タイトル部）は破棄する。
    見出しが無ければ本文全体を1セクションにする。
    """
    if not any(line.startswith("## ") for line in body.splitlines()):
        return [body] if body.strip() else []
    sections: list[str] = []
    current: list[str] | None = None
    for line in body.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections.append("\n".join(current).strip())
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        sections.append("\n".join(current).strip())
    return [section for section in sections if section]
