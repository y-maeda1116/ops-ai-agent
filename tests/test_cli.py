"""CLI (index / triage) のテスト。triage は FakeLlm でend-to-end。"""

import json
from pathlib import Path

from typer.testing import CliRunner

import ops_ai_agent.cli as cli_module
from ops_ai_agent.cli import app
from ops_ai_agent.domain.models import KnowledgeChunk, SearchHit, TriageReport
from ops_ai_agent.ports.llm import LlmResponse, Message, TextBlock, ToolSpec

runner = CliRunner()

_VALID_REPORT = {
    "severity": "high",
    "summary": "アップストリームタイムアウトの疑い。",
    "possible_causes": [
        {"description": "アップストリーム遅延", "evidence": "timeout 多発"}
    ],
    "recommended_actions": [
        {"order": 1, "description": "ロールバック判断", "owner_hint": "app チーム"}
    ],
    "referenced_incidents": ["INC-001"],
    "confidence": "medium",
    "requires_human_escalation": False,
}


class FakeFinalLlm:
    """end_turn で即レポートを返す LlmPort 実装。"""

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        output_schema: dict | None = None,
    ) -> LlmResponse:
        return LlmResponse(
            stop_reason="end_turn",
            content=[TextBlock(text=json.dumps(_VALID_REPORT, ensure_ascii=False))],
        )


class StubRetriever:
    def search(self, query: str, *, top_k: int = 3) -> list[SearchHit]:
        return []

    def get_runbook(self, service: str) -> str | None:
        return None


def _patch_factories(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_module, "_build_llm", lambda settings: FakeFinalLlm())
    monkeypatch.setattr(
        cli_module, "_build_retriever", lambda settings: StubRetriever()
    )
    monkeypatch.chdir(tmp_path)


def _write_log(tmp_path: Path) -> Path:
    log = tmp_path / "app.jsonl"
    line = (
        '{"ts":"2026-10-03T12:00:00Z","level":"error",'
        '"service":"api-gateway","message":"upstream timeout"}\n'
    )
    log.write_text(line, encoding="utf-8")
    return log


def test_help_shows_app_description():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Ops AI Agent" in result.output


def test_triage_command_outputs_report(tmp_path, monkeypatch):
    _patch_factories(monkeypatch, tmp_path)
    log = _write_log(tmp_path)
    result = runner.invoke(app, ["triage", "--log", str(log)])
    assert result.exit_code == 0
    assert "障害一次切り分けレポート" in result.stdout
    assert "アップストリームタイムアウト" in result.stdout


def test_triage_with_alert_only(tmp_path, monkeypatch):
    _patch_factories(monkeypatch, tmp_path)
    result = runner.invoke(app, ["triage", "--alert", "ALERT: 5xx急増"])
    assert result.exit_code == 0
    assert "障害一次切り分けレポート" in result.stdout


def test_triage_requires_log_or_alert(tmp_path, monkeypatch):
    _patch_factories(monkeypatch, tmp_path)
    result = runner.invoke(app, ["triage"])
    assert result.exit_code != 0


def test_triage_empty_log_fails(tmp_path, monkeypatch):
    _patch_factories(monkeypatch, tmp_path)
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n\n", encoding="utf-8")
    result = runner.invoke(app, ["triage", "--log", str(empty)])
    assert result.exit_code != 0
    assert "有効なログ" in result.output


def test_triage_unparseable_only_log_fails(tmp_path, monkeypatch):
    _patch_factories(monkeypatch, tmp_path)
    garbage = tmp_path / "garbage.jsonl"
    garbage.write_text(" Plain garbage without any structure \n", encoding="utf-8")
    result = runner.invoke(app, ["triage", "--log", str(garbage)])
    # unknown レコードになるため解析可能レコード0件扱いで失敗する
    assert result.exit_code != 0


def test_triage_missing_api_key_exits_with_message(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = runner.invoke(app, ["triage", "--alert", "ALERT: x"])
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output


def test_triage_slack_notify_also_echoes_report_to_stdout(tmp_path, monkeypatch):
    """slack通知時もレポート本文をstdoutへ出力し喪失しない（spec §8、回帰）。"""
    _patch_factories(monkeypatch, tmp_path)
    sent: list[TriageReport] = []

    class SpyNotifier:
        def send_report(self, report: TriageReport, *, context: str = "") -> None:
            sent.append(report)

    monkeypatch.setattr(cli_module, "_build_notifier", lambda kind: SpyNotifier())
    result = runner.invoke(
        app, ["triage", "--alert", "ALERT: 5xx急増", "--notify", "slack"]
    )
    assert result.exit_code == 0
    assert "アップストリームタイムアウト" in result.stdout
    assert sent[0].severity == "high"


def test_triage_slack_missing_token_reports_clean_error(tmp_path, monkeypatch):
    """SLACK_BOT_TOKEN未設定も生tracebackでなく構造化エラーになる（回帰）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.setattr(cli_module, "_build_llm", lambda settings: FakeFinalLlm())
    monkeypatch.setattr(
        cli_module, "_build_retriever", lambda settings: StubRetriever()
    )
    result = runner.invoke(app, ["triage", "--alert", "ALERT: x", "--notify", "slack"])
    assert result.exit_code == 1
    assert "エラー:" in result.output
    assert "SLACK_BOT_TOKEN" in result.output


class FakeAnswerLlm:
    """ヒット文書を引用して答える LlmPort 実装。"""

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        output_schema: dict | None = None,
    ) -> LlmResponse:
        self.requests.append({"system": system, "messages": messages})
        return LlmResponse(
            stop_reason="end_turn",
            content=[TextBlock(text="過去にINC-001で同様事象があります。")],
        )


class StubRichRetriever:
    def search(self, query: str, *, top_k: int = 3) -> list[SearchHit]:
        chunk = KnowledgeChunk(
            id="inc-001.md#0",
            source="incidents/inc-001.md",
            title="api-gateway 5xx急増",
            text="症状: 5xx急増",
            metadata={"id": "INC-001"},
            embedding=[0.1],
        )
        return [SearchHit(chunk=chunk, score=0.9)]

    def get_runbook(self, service: str) -> str | None:
        return None


def test_ask_answers_from_hits(tmp_path, monkeypatch):
    fake_llm = FakeAnswerLlm()
    monkeypatch.setattr(cli_module, "_build_llm", lambda settings: fake_llm)
    monkeypatch.setattr(
        cli_module, "_build_retriever", lambda settings: StubRichRetriever()
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["ask", "5xx急増の過去事例は？"])
    assert result.exit_code == 0
    assert "INC-001" in result.stdout
    # ヒット文書がデリミタでラップされている
    first_user = fake_llm.requests[0]["messages"][0]
    text = next(b.text for b in first_user.content if isinstance(b, TextBlock))
    assert any(line.startswith("<knowledge-") for line in text.splitlines())


def test_ask_no_hits_reports_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_module, "_build_llm", lambda settings: FakeAnswerLlm())
    monkeypatch.setattr(
        cli_module, "_build_retriever", lambda settings: StubRetriever()
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["ask", "無関係な質問"])
    assert result.exit_code == 0
    assert "一致する文書" in result.stdout


def test_help_lists_webhook_command():
    result = runner.invoke(app, ["webhook", "--help"])
    assert result.exit_code == 0
    assert "Webhook" in result.stdout


def test_build_webhook_on_alert_triages_and_notifies(tmp_path, monkeypatch):
    from ops_ai_agent.config import Settings
    from ops_ai_agent.domain.webhook import NormalizedAlert

    _patch_factories(monkeypatch, tmp_path)
    sent: list[TriageReport] = []

    class SpyNotifier:
        def send_report(self, report: TriageReport, *, context: str = "") -> None:
            sent.append(report)

    monkeypatch.setattr(cli_module, "_build_notifier", lambda kind: SpyNotifier())
    settings = Settings(
        _env_file=None,
        anthropic_api_key="sk-test",  # type: ignore[call-arg]
        voyage_api_key="pa-test",
    )
    on_alert = cli_module.build_webhook_on_alert(settings, notify="console")
    alert = NormalizedAlert(
        source="alertmanager",
        title="HighErrorRate",
        description="5xx急増",
        severity="critical",
        status="firing",
    )
    report = on_alert(alert)
    assert report.summary == "アップストリームタイムアウトの疑い。"
    assert len(sent) == 1


def _seed_feedback(tmp_path: Path):
    from datetime import UTC, datetime

    from ops_ai_agent.adapters.feedback_store import JsonFeedbackStore
    from ops_ai_agent.domain.feedback import FeedbackRecord

    store = JsonFeedbackStore(tmp_path / "data" / "feedback.json")
    store.add(
        FeedbackRecord(
            id="fb-001",
            helpful=True,
            severity="high",
            summary="アップストリームタイムアウトの疑い。",
            possible_causes=["遅延"],
            recommended_actions=["ロールバック"],
            context="slack:C1",
            created_at=datetime(2026, 10, 22, 9, 0, tzinfo=UTC),
        )
    )


def test_feedback_list_shows_pending(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_feedback(tmp_path)
    result = runner.invoke(app, ["feedback", "list"])
    assert result.exit_code == 0
    assert "fb-001" in result.stdout
    assert "アップストリームタイムアウトの疑い。" in result.stdout


def test_feedback_accept_writes_knowledge_and_marks_accepted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed_feedback(tmp_path)
    result = runner.invoke(app, ["feedback", "accept", "fb-001"])
    assert result.exit_code == 0
    knowledge = tmp_path / "knowledge" / "incidents" / "fb-001.md"
    assert knowledge.exists()
    content = knowledge.read_text(encoding="utf-8")
    assert "アップストリームタイムアウトの疑い。" in content
    from ops_ai_agent.adapters.feedback_store import JsonFeedbackStore

    record = JsonFeedbackStore(tmp_path / "data" / "feedback.json").get("fb-001")
    assert record.status == "accepted"


def test_feedback_accept_unknown_id_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["feedback", "accept", "missing"])
    assert result.exit_code != 0
    assert "見つかりません" in result.output
