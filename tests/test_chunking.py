"""Markdownチャンク化のテスト。"""

from ops_ai_agent.rag.chunking import chunk_markdown

_SAMPLE = """---
id: INC-001
title: api-gateway 5xx急増
service: api-gateway
severity: critical
tags:
  - timeout
  - upstream
---

# api-gateway 5xx急増

## 症状
5xx レスポンスが急増した。

## 原因
アップストリームのタイムアウト。
"""


def test_chunk_markdown_splits_by_heading():
    drafts = chunk_markdown(_SAMPLE, source="knowledge/incidents/inc-001.md")
    assert len(drafts) == 2
    assert drafts[0].id == "inc-001.md#0"
    assert drafts[0].title == "api-gateway 5xx急増"
    assert "症状" in drafts[0].text
    assert "5xx レスポンスが急増した。" in drafts[0].text
    assert "原因" in drafts[1].text


def test_chunk_markdown_keeps_frontmatter_metadata():
    drafts = chunk_markdown(_SAMPLE, source="knowledge/incidents/inc-001.md")
    for draft in drafts:
        assert draft.metadata["id"] == "INC-001"
        assert draft.metadata["service"] == "api-gateway"
        assert draft.metadata["tags"] == "timeout, upstream"
        assert "service: api-gateway" in draft.text


def test_chunk_markdown_truncates_long_section():
    long_body = "あ" * 3000
    text = f"---\ntitle: t\n---\n\n# T\n\n## 症状\n{long_body}\n"
    drafts = chunk_markdown(text, source="x.md", max_chars=1500)
    assert len(drafts) == 1
    assert len(drafts[0].text) <= 1500


def test_chunk_markdown_plain_text_single_chunk():
    text = "---\ntitle: メモ\n---\n\nほげほげの内容。\n"
    drafts = chunk_markdown(text, source="memo.md")
    assert len(drafts) == 1
    assert "ほげほげの内容。" in drafts[0].text
    assert drafts[0].title == "メモ"


def test_chunk_markdown_fallback_title():
    text = "本文のみ。\n"
    drafts = chunk_markdown(text, source="notes.md")
    assert drafts[0].title == "notes"
