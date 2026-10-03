"""ドメインモデルのテスト。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ops_ai_agent.domain.models import (
    Action,
    Cause,
    KnowledgeChunk,
    LogRecord,
    SearchHit,
    TriageReport,
)


def _record(**overrides: object) -> LogRecord:
    fields: dict[str, object] = {
        "timestamp": datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
        "level": "error",
        "service": "api-gateway",
        "message": "upstream timeout after 5000ms",
        "raw": '{"ts":"2026-10-03T12:00:00Z","level":"error"}',
    }
    return LogRecord(**{**fields, **overrides})


def test_log_record_requires_all_fields():
    record = _record()
    assert record.level == "error"
    assert record.service == "api-gateway"
    assert record.raw.startswith('{"ts"')


def test_log_record_missing_field_raises():
    with pytest.raises(ValidationError):
        LogRecord(
            timestamp=datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
            level="error",
            service="api-gateway",
            message="x",
        )


def _report(**overrides: object) -> TriageReport:
    fields: dict[str, object] = {
        "severity": "high",
        "summary": "api-gateway の 5xx 急増。アップストリームタイムアウトが疑われる。",
        "possible_causes": [
            Cause(
                description="アップストリームの応答遅延",
                evidence="error rate 62% in 5min window",
            )
        ],
        "recommended_actions": [
            Action(
                order=1,
                description="アップストリームの状況を確認",
                owner_hint="app チーム",
            )
        ],
        "referenced_incidents": ["INC-001"],
        "confidence": "medium",
        "requires_human_escalation": False,
    }
    return TriageReport(**{**fields, **overrides})


def test_triage_report_validates_json():
    record = _report()
    parsed = TriageReport.model_validate_json(record.model_dump_json())
    assert parsed.severity == "high"
    assert parsed.possible_causes[0].description == "アップストリームの応答遅延"
    assert parsed.recommended_actions[0].order == 1


def test_triage_report_invalid_severity_raises():
    with pytest.raises(ValidationError):
        _report(severity="urgent")


def test_triage_report_empty_causes_ok():
    report = _report(possible_causes=[], recommended_actions=[])
    assert report.possible_causes == []


def test_knowledge_chunk_and_search_hit():
    chunk = KnowledgeChunk(
        id="inc-001.md#0",
        source="knowledge/incidents/inc-001.md",
        title="api-gateway 5xx急増",
        text="症状: 5xx急増...",
        metadata={"service": "api-gateway", "severity": "critical"},
        embedding=[0.1, 0.2, 0.3],
    )
    hit = SearchHit(chunk=chunk, score=0.95)
    assert hit.chunk.metadata["service"] == "api-gateway"
    assert hit.score == pytest.approx(0.95)
