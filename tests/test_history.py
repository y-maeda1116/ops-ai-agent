"""triage 実行履歴（監査ログ）のテスト。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ops_ai_agent.adapters.history_store import JsonHistoryStore
from ops_ai_agent.cli import app
from ops_ai_agent.domain.history import TriageHistoryRecord
from ops_ai_agent.domain.models import TriageReport
from tests.test_cli import _patch_factories, _write_log

runner = CliRunner()


def _report(summary: str = "アップストリームタイムアウトの疑い。") -> TriageReport:
    return TriageReport.model_validate(
        {
            "severity": "high",
            "summary": summary,
            "possible_causes": [{"description": "遅延", "evidence": "timeout"}],
            "recommended_actions": [
                {"order": 1, "description": "ロールバック", "owner_hint": "app"}
            ],
            "referenced_incidents": [],
            "confidence": "medium",
            "requires_human_escalation": False,
        }
    )


def _record(
    rid: str = "th-1", context: str = "webhook:alertmanager"
) -> TriageHistoryRecord:
    return TriageHistoryRecord(
        id=rid,
        created_at="2026-10-22T00:00:00+00:00",
        context=context,
        report=_report(),
    )


def test_history_store_add_get_list_roundtrip(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    store = JsonHistoryStore(path)
    store.add(_record("th-1"))
    store.add(_record("th-2", context="slack:C123"))
    got = store.get("th-2")
    assert got.context == "slack:C123"
    assert got.report.severity == "high"
    records = store.list()
    assert [r.id for r in records] == ["th-2", "th-1"]  # 新しい順
    reloaded = JsonHistoryStore(path)
    assert [r.id for r in reloaded.list()] == ["th-2", "th-1"]


def test_history_store_missing_id_raises(tmp_path: Path):
    store = JsonHistoryStore(tmp_path / "history.jsonl")
    with pytest.raises(KeyError):
        store.get("th-none")


def test_history_store_list_limit(tmp_path: Path):
    store = JsonHistoryStore(tmp_path / "history.jsonl")
    for i in range(5):
        store.add(_record(f"th-{i}"))
    assert [r.id for r in store.list(limit=2)] == ["th-4", "th-3"]


def test_triage_command_saves_history_and_history_cli_shows(tmp_path, monkeypatch):
    _patch_factories(monkeypatch, tmp_path)
    log = _write_log(tmp_path)
    result = runner.invoke(app, ["triage", "--log", str(log)])
    assert result.exit_code == 0, result.output
    store = JsonHistoryStore(Path("data/history.jsonl"))
    records = store.list()
    assert len(records) == 1
    assert records[0].report.summary == "アップストリームタイムアウトの疑い。"

    listed = runner.invoke(app, ["history", "list"])
    assert listed.exit_code == 0
    assert records[0].id in listed.stdout

    shown = runner.invoke(app, ["history", "show", records[0].id])
    assert shown.exit_code == 0
    assert "障害一次切り分けレポート" in shown.stdout


def test_history_show_missing_id_exits_1(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["history", "show", "th-none"])
    assert result.exit_code == 1


def test_history_jsonl_lines_are_json(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    store = JsonHistoryStore(path)
    store.add(_record("th-1"))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["id"] == "th-1"
