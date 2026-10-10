"""決定論的なログ統計解析（LLM不使用）。analyze_log ツールの実体。"""

import re
from collections import Counter
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from ops_ai_agent.domain.models import LogRecord

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_DIGITS_RE = re.compile(r"\d+")

_ERROR_LEVELS = frozenset({"error", "fatal", "critical"})


class ErrorPattern(BaseModel):
    pattern: str
    count: int
    sample: str


class WindowCount(BaseModel):
    window_start: datetime
    total: int
    errors: int


class LogSummary(BaseModel):
    total: int
    unparsed: int
    by_level: dict[str, int]
    by_service: dict[str, int]
    top_errors: list[ErrorPattern]
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    error_windows: list[WindowCount] = Field(default_factory=list)


def normalize_message(message: str) -> str:
    """集計用にメッセージを正規化（UUID/IPv4/数字をトークン化）。"""
    normalized = _UUID_RE.sub("UUID", message)
    normalized = _IPV4_RE.sub("IP", normalized)
    return _DIGITS_RE.sub("N", normalized)


def summarize(records: list[LogRecord], *, window_minutes: int = 5) -> LogSummary:
    """レコード列を集計する。

    level=="unknown" は by_level・エラーパターン・時間窓から除外し unparsed に数える。
    by_service と first/last_timestamp は全レコード対象（service 空行を除く）。
    """
    parsed = [r for r in records if r.level != "unknown"]
    by_level = Counter(r.level for r in parsed)
    by_service = Counter(r.service for r in records if r.service)

    error_counter: Counter[tuple[str, str]] = Counter()
    for record in parsed:
        if record.level in _ERROR_LEVELS:
            error_counter[(normalize_message(record.message), record.message)] += 1
    pattern_counter: Counter[str] = Counter()
    samples: dict[str, str] = {}
    for (pattern, sample), count in error_counter.items():
        pattern_counter[pattern] += count
        samples.setdefault(pattern, sample)
    top_errors = [
        ErrorPattern(pattern=pattern, count=count, sample=samples[pattern])
        for pattern, count in pattern_counter.most_common(5)
    ]

    timestamps = [r.timestamp for r in records]
    return LogSummary(
        total=len(records),
        unparsed=len(records) - len(parsed),
        by_level=dict(by_level),
        by_service=dict(by_service),
        top_errors=top_errors,
        first_timestamp=min(timestamps) if timestamps else None,
        last_timestamp=max(timestamps) if timestamps else None,
        error_windows=_build_windows(parsed, window_minutes=window_minutes),
    )


def _build_windows(
    parsed: list[LogRecord], *, window_minutes: int
) -> list[WindowCount]:
    if not parsed:
        return []
    start = min(r.timestamp for r in parsed)
    width = timedelta(minutes=window_minutes)
    buckets: dict[datetime, list[LogRecord]] = {}
    for record in parsed:
        offset = record.timestamp - start
        index = int(offset.total_seconds() // (width.total_seconds() or 1))
        bucket_start = start + index * width
        buckets.setdefault(bucket_start, []).append(record)
    return [
        WindowCount(
            window_start=bucket_start,
            total=len(items),
            errors=sum(1 for r in items if r.level in _ERROR_LEVELS),
        )
        for bucket_start, items in sorted(buckets.items())
    ]


def filter_records(
    records: list[LogRecord],
    *,
    level: str | None = None,
    service: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[LogRecord]:
    """条件でレコードをフィルタする。

    level/service は大文字小文字を無視した完全一致、時刻は [start, end) の半開区間。
    """
    return [
        record
        for record in records
        if (level is None or record.level == level.lower())
        and (service is None or record.service.lower() == service.lower())
        and (start is None or record.timestamp >= start)
        and (end is None or record.timestamp < end)
    ]


def format_summary(summary: LogSummary) -> str:
    """LLM向けにサマリをテキスト化する。"""
    lines = [
        f"総行数: {summary.total}（解析不能: {summary.unparsed}）",
        f"レベル別: {summary.by_level or {}}",
        f"サービス別: {summary.by_service or {}}",
    ]
    if summary.first_timestamp is not None and summary.last_timestamp is not None:
        lines.append(
            f"期間: {summary.first_timestamp.isoformat()} 〜 "
            f"{summary.last_timestamp.isoformat()}"
        )
    if summary.top_errors:
        lines.append("頻出エラーパターン:")
        lines.extend(
            f"  - {p.pattern} ×{p.count}（例: {p.sample}）" for p in summary.top_errors
        )
    if summary.error_windows:
        lines.append("時間窓別（total/errors）:")
        lines.extend(
            f"  - {w.window_start.isoformat()}: {w.total}/{w.errors}"
            for w in summary.error_windows
        )
    return "\n".join(lines)
