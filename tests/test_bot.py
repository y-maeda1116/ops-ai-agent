"""Slack Bot ハンドラのテスト（fake say 使用、実Slack不使用）。"""

import json
import logging

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
