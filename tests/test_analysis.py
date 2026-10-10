"""決定論的ログ解析のテスト。"""

from datetime import UTC, datetime

from ops_ai_agent.domain.analysis import (
    filter_records,
    format_summary,
    normalize_message,
    summarize,
)
from ops_ai_agent.domain.models import LogRecord


def _record(
    minute: int, level: str, service: str = "api", message: str = "msg"
) -> LogRecord:
    return LogRecord(
        timestamp=datetime(2026, 10, 3, 12, minute, tzinfo=UTC),
        level=level,
        service=service,
        message=message,
        raw="raw",
    )


def _records() -> list[LogRecord]:
    return [
        _record(0, "info"),
        _record(1, "error", message="upstream timeout after 5000ms"),
        _record(2, "error", message="upstream timeout after 6000ms"),
        _record(7, "error", message="connection refused to 10.0.0.5:5432"),
        _record(8, "warn", service="worker", message="queue backlog 1200"),
        _record(9, "unknown", message=""),
    ]


def test_summarize_counts_and_levels():
    summary = summarize(_records())
    assert summary.total == 6
    assert summary.unparsed == 1
    assert summary.by_level == {"info": 1, "error": 3, "warn": 1}
    assert summary.by_service == {"api": 5, "worker": 1}
    assert summary.first_timestamp == datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    assert summary.last_timestamp == datetime(2026, 10, 3, 12, 9, tzinfo=UTC)


def test_summarize_top_errors_normalizes_messages():
    summary = summarize(_records())
    patterns = {p.pattern: p.count for p in summary.top_errors}
    assert patterns["upstream timeout after Nms"] == 2
    assert patterns["connection refused to IP:N"] == 1
    sample = next(p for p in summary.top_errors if "upstream" in p.pattern)
    assert sample.sample.startswith("upstream timeout after")


def test_summarize_error_windows():
    summary = summarize(_records(), window_minutes=5)
    # 12:00-12:05 に2件、12:05-12:10 に1件のerror（unknown除く）
    assert len(summary.error_windows) == 2
    first = summary.error_windows[0]
    assert first.window_start == datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    assert first.total == 3
    assert first.errors == 2


def test_summarize_empty():
    summary = summarize([])
    assert summary.total == 0
    assert summary.first_timestamp is None
    assert summary.error_windows == []


def test_filter_records_by_level_and_service():
    records = _records()
    assert len(filter_records(records, level="error")) == 3
    assert len(filter_records(records, service="worker")) == 1
    assert filter_records(records, level="ERROR", service="API") != []


def test_filter_records_by_time_range():
    records = _records()
    start = datetime(2026, 10, 3, 12, 2, tzinfo=UTC)
    end = datetime(2026, 10, 3, 12, 8, tzinfo=UTC)
    filtered = filter_records(records, start=start, end=end)
    assert [r.timestamp.minute for r in filtered] == [2, 7]


def test_normalize_message():
    assert normalize_message("user 12345 logged in") == "user N logged in"
    assert (
        normalize_message("req 550e8400-e29b-41d4-a716-446655440000 failed")
        == "req UUID failed"
    )
    assert normalize_message("connect 10.0.0.5:5432 refused") == "connect IP:N refused"
    assert normalize_message("error at line N") == "error at line N"


def test_format_summary_renders_key_sections():
    text = format_summary(summarize(_records()))
    assert "総行数: 6" in text
    assert "error" in text
    assert "api" in text
