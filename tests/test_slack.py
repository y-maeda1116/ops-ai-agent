"""Slack Notifier のテスト（WebClientスタブ使用）。"""

import pytest

from ops_ai_agent.adapters.slack import (
    SEVERITY_COLOR,
    SlackNotifier,
    create_slack_notifier,
    report_to_blocks,
)
from ops_ai_agent.domain.models import Action, Cause, TriageReport


def _report(**overrides: object) -> TriageReport:
    fields: dict[str, object] = {
        "severity": "high",
        "summary": "アップストリームタイムアウトの疑い。",
        "possible_causes": [Cause(description="遅延", evidence="timeout")],
        "recommended_actions": [
            Action(order=1, description="確認", owner_hint="app チーム")
        ],
        "referenced_incidents": ["INC-001"],
        "confidence": "medium",
        "requires_human_escalation": False,
    }
    return TriageReport(**{**fields, **overrides})


def test_severity_color_mapping():
    assert SEVERITY_COLOR["critical"] == "#dc2626"
    assert SEVERITY_COLOR["low"] == "#6b7280"


def test_report_to_blocks_structure():
    blocks = report_to_blocks(_report())
    types = [b["type"] for b in blocks]
    assert types[0] == "header"
    assert "section" in types
    header_text = blocks[0]["text"]["text"]
    assert "high" in header_text
    joined = str(blocks)
    assert "アップストリームタイムアウト" in joined
    assert "INC-001" in joined


def test_notifier_posts_blocks():
    posted: list[dict] = []

    class StubWebClient:
        def chat_postMessage(self, **kwargs) -> dict:  # noqa: N802
            posted.append(kwargs)
            return {"ok": True, "ts": "1234.5678"}

    notifier = SlackNotifier(StubWebClient(), "#ops-alerts")  # type: ignore[arg-type]
    notifier.send_report(_report(), context="api-gateway-5xx.jsonl")
    assert len(posted) == 1
    assert posted[0]["channel"] == "#ops-alerts"
    assert posted[0]["attachments"][0]["blocks"]
    assert "api-gateway-5xx.jsonl" in str(posted[0]["attachments"][0]["blocks"])


def test_notifier_colors_by_severity():
    """重要度に応じたattachments色を付与する（spec §7、回帰）。"""
    posted: list[dict] = []

    class StubWebClient:
        def chat_postMessage(self, **kwargs) -> dict:  # noqa: N802
            posted.append(kwargs)
            return {"ok": True, "ts": "1234.5678"}

    notifier = SlackNotifier(StubWebClient(), "#ops-alerts")  # type: ignore[arg-type]
    notifier.send_report(_report(severity="critical"))
    notifier.send_report(_report(severity="low"))
    assert posted[0]["attachments"][0]["color"] == SEVERITY_COLOR["critical"]
    assert posted[1]["attachments"][0]["color"] == SEVERITY_COLOR["low"]


def test_create_slack_notifier_requires_token(tmp_path, monkeypatch):
    from ops_ai_agent.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError, match="SLACK_BOT_TOKEN"):
        create_slack_notifier(settings)
