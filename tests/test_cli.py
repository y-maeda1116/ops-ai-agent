"""CLI (index / triage) のテスト。triage は FakeLlm でend-to-end。"""

import json
from pathlib import Path

from typer.testing import CliRunner

import ops_ai_agent.cli as cli_module
from ops_ai_agent.cli import app
from ops_ai_agent.domain.models import SearchHit
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
