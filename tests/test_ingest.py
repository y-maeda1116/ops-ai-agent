"""ログ取り込みのテスト。"""

from datetime import UTC, datetime

from ops_ai_agent.domain.analysis import summarize
from ops_ai_agent.domain.ingest import parse_log_text, read_log_source


def test_parse_jsonl_with_canonical_keys():
    text = (
        '{"ts":"2026-10-03T12:00:00Z","level":"ERROR",'
        '"service":"api-gateway","message":"upstream timeout"}\n'
    )
    result = parse_log_text(text)
    assert len(result.records) == 1
    record = result.records[0]
    assert record.timestamp == datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    assert record.level == "error"
    assert record.service == "api-gateway"
    assert record.message == "upstream timeout"
    assert result.skipped_lines == []


def test_parse_jsonl_with_alternate_keys():
    text = (
        '{"timestamp":"2026-10-03T12:00:01+09:00","severity":"warn",'
        '"component":"worker","msg":"queue backlog 1200"}\n'
    )
    result = parse_log_text(text)
    record = result.records[0]
    assert record.level == "warn"
    assert record.service == "worker"
    assert record.message == "queue backlog 1200"
    assert record.timestamp.utcoffset().total_seconds() == 9 * 3600


def test_parse_plain_text_line():
    text = "2026-10-03T12:00:00Z ERROR [api-gateway] upstream timeout after 5000ms\n"
    result = parse_log_text(text)
    assert len(result.records) == 1
    record = result.records[0]
    assert record.level == "error"
    assert record.service == "api-gateway"
    assert record.message == "upstream timeout after 5000ms"


def test_parse_plain_text_with_comma_millis_and_no_brackets():
    text = "2026-10-03 12:00:00,123 WARN worker - retrying job\n"
    result = parse_log_text(text)
    record = result.records[0]
    assert record.level == "warn"
    assert record.service == "worker"
    assert record.message == "retrying job"


def test_unparseable_line_becomes_unknown_record():
    text = "unexpected garbage line without timestamp\n"
    result = parse_log_text(text)
    assert len(result.records) == 1
    record = result.records[0]
    assert record.level == "unknown"
    assert record.raw == "unexpected garbage line without timestamp"


def test_blank_lines_are_skipped():
    text = "\n\n2026-10-03T12:00:00Z INFO [api] ok\n\n"
    result = parse_log_text(text)
    assert len(result.records) == 1
    assert result.skipped_lines == ["", ""]


def test_mixed_content():
    text = (
        '{"ts":"2026-10-03T12:00:00Z","level":"error","service":"api","message":"x"}\n'
        "2026-10-03T12:00:01Z INFO [api] ok\n"
        "garbage\n"
    )
    result = parse_log_text(text)
    assert len(result.records) == 3
    assert [r.level for r in result.records] == ["error", "info", "unknown"]


def test_naive_and_aware_timestamp_mix_does_not_crash():
    """naive時刻とunknown行（aware now）の混在でクラッシュしない（回帰）。"""
    text = (
        "2026-10-03 12:00:00,123 WARN worker - retrying job\n"
        "unexpected garbage line without timestamp\n"
    )
    result = parse_log_text(text)
    assert result.records[0].timestamp.tzinfo is not None
    summary = summarize(result.records)
    assert summary.total == 2
    assert summary.unparsed == 1


def test_jsonl_mixing_naive_and_aware_ts_does_not_crash():
    text = (
        '{"ts":"2026-10-03T12:00:00","level":"error","service":"api","message":"x"}\n'
        '{"ts":"2026-10-03T12:01:00Z","level":"error","service":"api","message":"y"}\n'
    )
    result = parse_log_text(text)
    summary = summarize(result.records)
    assert summary.total == 2
    assert summary.first_timestamp is not None


def test_read_log_source_file(tmp_path):
    log_file = tmp_path / "app.log"
    log_file.write_text("2026-10-03T12:00:00Z INFO [api] ok\n", encoding="utf-8")
    assert read_log_source(str(log_file)) == "2026-10-03T12:00:00Z INFO [api] ok\n"


def test_read_log_source_stdin(monkeypatch):
    import io

    monkeypatch.setattr(
        "sys.stdin", io.StringIO("2026-10-03T12:00:00Z INFO [api] ok\n")
    )
    assert "INFO" in read_log_source("-")


def test_parse_log_text_masks_secrets_in_raw_and_message():
    from ops_ai_agent.domain.masking import mask_sensitive  # noqa: F401

    line = (
        '{"ts":"2026-10-03T12:00:00Z","level":"error","service":"api",'
        '"message":"auth failed with key AKIAIOSFODNN7EXAMPLE"}'
    )
    result = parse_log_text(line)
    record = result.records[0]
    assert "AKIAIOSFODNN7EXAMPLE" not in record.raw
    assert "AKIAIOSFODNN7EXAMPLE" not in record.message
    assert "***MASKED***" in record.message
