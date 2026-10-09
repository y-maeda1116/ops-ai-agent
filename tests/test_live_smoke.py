"""実APIを使うスモークテスト（pytest -m live でのみ実行、CIではスキップ）。"""

import pytest

from ops_ai_agent.adapters.claude_llm import create_claude_llm
from ops_ai_agent.adapters.voyage_embeddings import create_voyage_embedder
from ops_ai_agent.config import Settings
from ops_ai_agent.ports.llm import Message, TextBlock

pytestmark = pytest.mark.live


def test_live_claude_end_turn():
    settings = Settings()
    llm = create_claude_llm(settings)
    response = llm.complete(
        system="1語で答えてください。",
        messages=[Message(role="user", content=[TextBlock(text="1+1は？")])],
    )
    assert response.stop_reason == "end_turn"
    assert any(isinstance(b, TextBlock) for b in response.content)


def test_live_voyage_embedding():
    embedder = create_voyage_embedder(Settings())
    vector = embedder.embed_query("api-gateway 5xx急増")
    assert len(vector) > 0
    assert all(isinstance(x, float) for x in vector)


def test_live_triage_tool_use_and_structured_output():
    """ツール利用→構造化出力（tools無しでの履歴再送を含む）の実API検証。

    max_iterations/max_tokens 回復時は tools パラメータ無しで tool_use/
    tool_result を含む会話履歴を再送する。この形状が実APIで受理されることを
    FakeLlm では検証できないため、ここで確認する。
    """
    from ops_ai_agent.domain.ingest import parse_log_text
    from ops_ai_agent.domain.triage import TriageService

    class NoopRetriever:
        def search(self, query: str, *, top_k: int = 3):
            return []

        def get_runbook(self, service: str) -> str | None:
            return None

    settings = Settings()
    service = TriageService(
        create_claude_llm(settings),
        NoopRetriever(),
        max_iterations=settings.max_iterations,
    )
    records = parse_log_text(
        "\n".join(
            f"2026-10-03T12:{minute:02d}:00Z ERROR api-gateway "
            f"upstream timeout after {5000 + minute}ms"
            for minute in range(5)
        )
    ).records
    report = service.triage(records, alert_text="ALERT: api-gateway 5xx急増")
    assert report.severity in {"critical", "high", "medium", "low"}
    assert report.recommended_actions
