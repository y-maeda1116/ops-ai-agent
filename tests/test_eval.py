"""Eval（golden set回帰テスト）のテスト。FakeLlm でend-to-end。"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ops_ai_agent.cli import app
from ops_ai_agent.domain.eval import (
    GoldenCase,
    GoldenExpectation,
    load_golden_cases,
    score_report,
    summarize_eval,
)
from ops_ai_agent.domain.models import TriageReport
from tests.test_cli import _patch_factories, _write_log

runner = CliRunner()


def _report(severity: str, causes: list[str], actions: list[str]) -> TriageReport:
    return TriageReport.model_validate(
        {
            "severity": severity,
            "summary": "サマリ",
            "possible_causes": [{"description": c, "evidence": "ev"} for c in causes],
            "recommended_actions": [
                {"order": i + 1, "description": a, "owner_hint": "SRE"}
                for i, a in enumerate(actions)
            ],
            "referenced_incidents": [],
            "confidence": "high",
            "requires_human_escalation": False,
        }
    )


def _case() -> GoldenCase:
    return GoldenCase(
        name="db-pool",
        log_text="error db connection timeout",
        expected=GoldenExpectation(
            severity="high",
            cause_keywords=["コネクション", "プール"],
            action_keywords=["拡張"],
        ),
    )


def test_load_golden_cases_reads_json_files(tmp_path: Path):
    payload = _case().model_dump(mode="json")
    (tmp_path / "db-pool.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    cases = load_golden_cases(tmp_path)
    assert len(cases) == 1
    assert cases[0].name == "db-pool"
    assert cases[0].expected.severity == "high"


def test_score_report_severity_match_and_keyword_hit_rates():
    case = _case()
    report = _report(
        "high", ["DBコネクション枯渇（プール上限）"], ["プールサイズを拡張"]
    )
    score = score_report(report, case)
    assert score.severity_match is True
    assert score.cause_hit_rate == 1.0
    assert score.action_hit_rate == 1.0


def test_score_report_partial_hits_and_mismatch():
    case = _case()
    report = _report("low", ["コネクション切断"], ["再起動"])
    score = score_report(report, case)
    assert score.severity_match is False
    # 2キーワード中1個ヒット
    assert score.cause_hit_rate == 0.5
    assert score.action_hit_rate == 0.0


def test_score_report_no_keywords_means_full_score():
    case = GoldenCase(
        name="empty",
        log_text="x",
        expected=GoldenExpectation(
            severity="low", cause_keywords=[], action_keywords=[]
        ),
    )
    score = score_report(_report("low", [], []), case)
    assert score.cause_hit_rate == 1.0
    assert score.action_hit_rate == 1.0


def test_summarize_eval_aggregates():
    case = _case()
    scores = [
        score_report(_report("high", ["コネクション", "プール"], ["拡張"]), case),
        score_report(_report("low", ["コネクション"], []), case),
    ]
    summary = summarize_eval(scores)
    assert summary.total == 2
    assert summary.severity_accuracy == 0.5
    assert summary.mean_cause_hit_rate == pytest.approx(0.75)
    assert summary.mean_action_hit_rate == pytest.approx(0.5)


def test_eval_command_runs_live_pipeline(tmp_path, monkeypatch):
    _patch_factories(monkeypatch, tmp_path)
    result = runner.invoke(app, ["eval", "--cases", str(_golden_dir(tmp_path))])
    assert result.exit_code == 0, result.output
    assert "severity_accuracy" in result.stdout


def test_eval_command_fails_below_threshold(tmp_path, monkeypatch):
    _patch_factories(monkeypatch, tmp_path)
    result = runner.invoke(
        app,
        [
            "eval",
            "--cases",
            str(_golden_dir(tmp_path)),
            "--min-severity-accuracy",
            "1.1",
        ],
    )
    assert result.exit_code == 1


def _golden_dir(tmp_path: Path) -> Path:
    """テスト用の golden set を作る（FakeFinalLlm の出力に合わせる）。"""
    from tests.test_cli import _VALID_REPORT

    case = GoldenCase(
        name="fixture",
        log_text=_write_log(tmp_path).read_text(encoding="utf-8"),
        expected=GoldenExpectation(
            severity=_VALID_REPORT["severity"],
            cause_keywords=["アップストリーム"],
            action_keywords=["ロールバック"],
        ),
    )
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    (golden_dir / "fixture.json").write_text(
        json.dumps(case.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    return golden_dir


@pytest.mark.live
def test_eval_golden_set_live_regression():
    """実APIで golden set を実行し精度しきい値以上を検証する（CIでは除外）。"""
    result = runner.invoke(
        app,
        ["eval", "--cases", "eval/golden", "--min-severity-accuracy", "0.8"],
    )
    assert result.exit_code == 0, result.output
