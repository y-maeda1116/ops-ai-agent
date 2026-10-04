"""コンソール出力のテスト。"""

from ops_ai_agent.adapters.console import ConsoleNotifier, report_to_markdown
from ops_ai_agent.domain.models import Action, Cause, TriageReport


def _report(**overrides: object) -> TriageReport:
    fields: dict[str, object] = {
        "severity": "critical",
        "summary": "DB接続枯渇の疑い。",
        "possible_causes": [
            Cause(description="接続リーク", evidence="too many clients")
        ],
        "recommended_actions": [
            Action(order=1, description="バッチ再起動", owner_hint="platform"),
            Action(order=2, description="ホットフィックス", owner_hint="app チーム"),
        ],
        "referenced_incidents": ["INC-002"],
        "confidence": "high",
        "requires_human_escalation": True,
    }
    return TriageReport(**{**fields, **overrides})


def test_report_to_markdown_sections():
    text = report_to_markdown(_report(), context="api-gateway-5xx.jsonl")
    assert "障害一次切り分けレポート" in text
    assert "critical" in text
    assert "接続リーク" in text
    assert "1. バッチ再起動" in text
    assert "INC-002" in text
    assert "api-gateway-5xx.jsonl" in text
    assert "要" in text  # エスカレーション表記


def test_report_to_markdown_escalation_false():
    text = report_to_markdown(_report(requires_human_escalation=False))
    assert "不要" in text


def test_console_notifier_prints(capsys):
    ConsoleNotifier().send_report(_report(), context="ctx")
    captured = capsys.readouterr()
    assert "障害一次切り分けレポート" in captured.out
