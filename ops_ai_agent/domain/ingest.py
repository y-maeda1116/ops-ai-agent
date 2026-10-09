"""ログテキストの取り込みと LogRecord 正規化。"""

import json
import re
import sys
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from ops_ai_agent.domain.models import LogRecord

_TIMESTAMP_KEYS = ("ts", "timestamp", "time")
_LEVEL_KEYS = ("level", "severity")
_SERVICE_KEYS = ("service", "component", "logger")
_MESSAGE_KEYS = ("message", "msg")

# プレーンテキスト: "2026-10-03T12:00:00Z ERROR [api-gateway] msg" または
# "2026-10-03 12:00:00,123 WARN worker - msg"（bare形式はセパレータ必須）
_PLAIN_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?)\s+"
    r"(?P<level>[A-Za-z]+)\s+"
    r"(?:\[(?P<service_bracket>[^\]]+)\]|(?P<service_bare>[\w.-]+)\s*[-:])\s*"
    r"(?P<msg>.*)$"
)


class IngestResult(BaseModel):
    """取り込み結果。skipped_lines は空行等、レコード化すらしなかった行。"""

    records: list[LogRecord] = Field(default_factory=list)
    skipped_lines: list[str] = Field(default_factory=list)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00").replace(",", ".")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        # naive時刻はUTCと解釈し、unknown行のaware now との混在TypeErrorを防ぐ
        return parsed.replace(tzinfo=UTC)
    return parsed


def _first_key(obj: dict[str, object], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in obj:
            return obj[key]
    return None


def _normalize_level(value: object) -> str:
    return str(value).strip().lower() if value is not None else "unknown"


def parse_log_text(text: str) -> IngestResult:
    """ログテキスト（JSONL/プレーン混在）を LogRecord 列へ正規化する。"""
    records: list[LogRecord] = []
    skipped: list[str] = []
    for line in text.rstrip("\n").splitlines():
        if not line.strip():
            skipped.append(line)
            continue
        record = _parse_json_line(line) or _parse_plain_line(line)
        if record is not None:
            records.append(record)
        else:
            # aware統一: analysis の min/max 比較で naive/aware 混在TypeErrorを避ける
            records.append(
                LogRecord(
                    timestamp=datetime.now(tz=UTC),
                    level="unknown",
                    service="",
                    message="",
                    raw=line,
                )
            )
    return IngestResult(records=records, skipped_lines=skipped)


def _parse_json_line(line: str) -> LogRecord | None:
    if not line.lstrip().startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    ts = _first_key(obj, _TIMESTAMP_KEYS)
    level = _first_key(obj, _LEVEL_KEYS)
    service = _first_key(obj, _SERVICE_KEYS)
    message = _first_key(obj, _MESSAGE_KEYS)
    if ts is None:
        return None
    return LogRecord(
        timestamp=_parse_timestamp(str(ts)),
        level=_normalize_level(level),
        service="" if service is None else str(service),
        message="" if message is None else str(message),
        raw=line,
    )


def _parse_plain_line(line: str) -> LogRecord | None:
    match = _PLAIN_RE.match(line)
    if match is None:
        return None
    service = match.group("service_bracket") or match.group("service_bare") or ""
    return LogRecord(
        timestamp=_parse_timestamp(match.group("ts")),
        level=match.group("level").lower(),
        service=service,
        message=match.group("msg"),
        raw=line,
    )


def read_log_source(path: str) -> str:
    """ログソースを読む。path が '-' なら stdin。"""
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8", errors="replace") as file:
        return file.read()
