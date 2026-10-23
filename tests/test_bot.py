"""Slack Bot ハンドラのテスト（fake say 使用、実Slack不使用）。"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pytest

from ops_ai_agent.bot import create_app, extract_log_text, handle_triage_request
from ops_ai_agent.config import Settings
from ops_ai_agent.ports.llm import LlmResponse, Message, TextBlock, ToolSpec

_VALID_REPORT = {
    "severity": "high",
    "summary": "アップストリームタイムアウトの疑い。",
    "possible_causes": [{"description": "遅延", "evidence": "timeout 多発"}],
    "recommended_actions": [
        {"order": 1, "description": "ロールバック", "owner_hint": "app チーム"}
    ],
    "referenced_incidents": ["INC-001"],
    "confidence": "medium",
    "requires_human_escalation": False,
}


class FakeBotLlm:
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
    def search(self, query: str, *, top_k: int = 3):
        return []

    def get_runbook(self, service: str) -> str | None:
        return None


def _service() -> object:
    from ops_ai_agent.domain.triage import TriageService

    return TriageService(FakeBotLlm(), StubRetriever())


def _make_say() -> tuple[list[dict], object]:
    calls: list[dict] = []

    def say(**kwargs) -> None:
        calls.append(kwargs)

    return calls, say


def _event(text: str, *, thread_ts: str | None = "1000.2000", ts: str = "1000.1000"):
    event: dict[str, object] = {"text": text, "ts": ts, "channel": "C1"}
    if thread_ts is not None:
        event["thread_ts"] = thread_ts
    return event


def test_extract_log_text_from_code_fence():
    text = "<@U999> 切り分けて\n```\n2026-10-03T12:00:00Z ERROR [api] timeout\n```"
    extracted = extract_log_text(text)
    assert "timeout" in extracted
    assert "<@" not in extracted
    assert "切り分けて" not in extracted


def test_extract_log_text_multiple_fences():
    text = '```json\n{"ts":"..."}\n```\n説明\n```\nplain\n```'
    extracted = extract_log_text(text)
    assert '{"ts"' in extracted
    assert "plain" in extracted
    assert "説明" not in extracted


def test_extract_log_text_no_fence_returns_all():
    assert "raw" in extract_log_text("<@U1> raw text")


def test_handle_triage_request_replies_in_thread():
    calls, say = _make_say()
    event = _event("<@U1> ```\n2026-10-03T12:00:00Z ERROR [api-gateway] timeout\n```")
    handle_triage_request(
        event, say, service=_service(), settings=Settings(_env_file=None)
    )
    assert len(calls) == 1
    assert calls[0]["thread_ts"] == "1000.2000"
    blocks = calls[0]["blocks"]
    assert "障害一次切り分けレポート" in str(blocks)


def test_handle_triage_request_falls_back_to_own_ts():
    calls, say = _make_say()
    event = _event(
        "<@U1> ```\n2026-10-03T12:00:00Z ERROR [api] timeout\n```",
        thread_ts=None,
        ts="1000.5000",
    )
    handle_triage_request(
        event, say, service=_service(), settings=Settings(_env_file=None)
    )
    assert calls[0]["thread_ts"] == "1000.5000"


def test_handle_triage_request_empty_text_replies_usage():
    calls, say = _make_say()
    handle_triage_request(
        _event("<@U1> こんにちは"),
        say,
        service=_service(),
        settings=Settings(_env_file=None),
    )
    assert len(calls) == 1
    assert "ログ" in str(calls[0].get("text", calls[0]))


def test_handle_triage_request_error_replies_fixed_message(monkeypatch):
    class BrokenService:
        def triage(self, records, *, alert_text=None):
            raise RuntimeError("llm down")

    calls, say = _make_say()
    handle_triage_request(
        _event("<@U1> ```\n2026-10-03T12:00:00Z ERROR [api] timeout\n```"),
        say,
        service=BrokenService(),
        settings=Settings(_env_file=None),
    )
    assert len(calls) == 1
    assert "失敗" in str(calls[0])
    # 例外が再送出されていない（Botプロセス継続）


def test_handle_triage_request_error_is_logged_with_traceback(caplog):
    """triage失敗は汎用返信としつつ、原因をスタックトレースごとログに残す。"""

    class BrokenService:
        def triage(self, records, *, alert_text=None):
            raise RuntimeError("llm down")

    calls, say = _make_say()
    with caplog.at_level(logging.ERROR, logger="ops_ai_agent.bot"):
        handle_triage_request(
            _event("<@U1> ```\n2026-10-03T12:00:00Z ERROR [api] timeout\n```"),
            say,
            service=BrokenService(),
            settings=Settings(_env_file=None),
        )
    error_records = [r for r in caplog.records if r.name == "ops_ai_agent.bot"]
    assert error_records
    assert error_records[0].levelno == logging.ERROR
    assert error_records[0].exc_info is not None
    assert error_records[0].exc_info[0] is RuntimeError


def test_create_app_registers_handlers():
    app = create_app("xoxb-test", service=_service(), settings=Settings(_env_file=None))
    assert app is not None


def test_handle_feedback_action_stores_record_and_replies(tmp_path):
    from ops_ai_agent.adapters.feedback_store import JsonFeedbackStore
    from ops_ai_agent.bot import handle_feedback_action

    store = JsonFeedbackStore(tmp_path / "feedback.json")
    calls: list[dict] = []

    def respond(**kwargs) -> None:
        calls.append(kwargs)

    body = {
        "actions": [
            {
                "action_id": "feedback_helpful",
                "value": json.dumps(
                    {
                        "summary": "アップストリームタイムアウトの疑い。",
                        "severity": "high",
                        "possible_causes": ["遅延"],
                        "recommended_actions": ["ロールバック"],
                        "context": "slack:C1",
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "user": {"id": "U1"},
        "message": {"ts": "1000.3000"},
    }
    handle_feedback_action(
        body,
        respond,
        store=store,
        id_factory=lambda: "fb-fixed",
        now_factory=lambda: datetime(2026, 10, 22, 9, 0),
    )
    record = store.get("fb-fixed")
    assert record.helpful is True
    assert record.summary == "アップストリームタイムアウトの疑い。"
    assert record.status == "pending"
    assert calls and calls[0]["thread_ts"] == "1000.3000"


def test_handle_feedback_action_invalid_value_replies_error(tmp_path):
    from ops_ai_agent.adapters.feedback_store import JsonFeedbackStore
    from ops_ai_agent.bot import handle_feedback_action

    store = JsonFeedbackStore(tmp_path / "feedback.json")
    calls: list[dict] = []

    def respond(**kwargs) -> None:
        calls.append(kwargs)

    body = {
        "actions": [{"action_id": "feedback_helpful", "value": "not-json"}],
        "user": {"id": "U1"},
        "message": {"ts": "1000.3000"},
    }
    handle_feedback_action(body, respond, store=store)
    assert store.list_pending() == []
    assert calls and "失敗" in calls[0]["text"]


def test_handle_triage_request_attaches_feedback_buttons():
    calls, say = _make_say()
    event = _event("<@U1> ```\n2026-10-03T12:00:00Z ERROR [api-gateway] timeout\n```")
    handle_triage_request(
        event, say, service=_service(), settings=Settings(_env_file=None)
    )
    blocks = calls[0]["blocks"]
    assert any(b.get("type") == "actions" for b in blocks)


@pytest.fixture(autouse=True)
def _tmp_cwd(tmp_path, monkeypatch):
    # 履歴保存（data/history.jsonl）がリポジトリ直下に漏れないよう各テストで隔離
    monkeypatch.chdir(tmp_path)


def test_handle_triage_request_saves_history_with_thread_ts(tmp_path):
    calls, say = _make_say()
    event = _event("<@U1> ```\n2026-10-03T12:00:00Z ERROR [api] timeout\n```")
    handle_triage_request(
        event, say, service=_service(), settings=Settings(_env_file=None)
    )
    from ops_ai_agent.adapters.history_store import JsonHistoryStore

    records = JsonHistoryStore(Path("data/history.jsonl")).list()
    assert len(records) == 1
    assert records[0].thread_ts == "1000.2000"
    assert records[0].context.startswith("slack:")
