"""チケット起票ユースケースのテスト（しきい値・重複防止）。"""

import pytest

from ops_ai_agent.domain.models import Action, Cause, TriageReport
from ops_ai_agent.domain.ticketing import (
    create_ticket_if_needed,
    report_fingerprint,
    severity_at_or_above,
)
from ops_ai_agent.ports.ticket import TicketPort, TicketStorePort


class _FakeTicketPort:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def create_ticket(self, title: str, description: str, *, severity: str) -> str:
        self.calls.append((title, description, severity))
        return f"https://jira.example.com/browse/OPS-{len(self.calls)}"


class _MemoryStore:
    def __init__(self) -> None:
        self.fingerprints: list[str] = []

    def contains(self, fingerprint: str) -> bool:
        return fingerprint in self.fingerprints

    def record(self, fingerprint: str) -> None:
        self.fingerprints.append(fingerprint)


def _report(severity: str = "critical") -> TriageReport:
    return TriageReport(
        severity=severity,  # type: ignore[arg-type]
        summary="DBコネクション枯渇",
        possible_causes=[Cause(description="接続プール上限", evidence="timeout多発")],
        recommended_actions=[
            Action(order=1, description="プール拡張", owner_hint="SRE")
        ],
        referenced_incidents=[],
        confidence="high",
        requires_human_escalation=True,
    )


def test_severity_at_or_above_ranking():
    assert severity_at_or_above("critical", "high")
    assert severity_at_or_above("high", "high")
    assert not severity_at_or_above("medium", "high")
    assert not severity_at_or_above("low", "high")


def test_report_fingerprint_stable_for_same_summary():
    assert report_fingerprint(_report()) == report_fingerprint(_report())


def test_create_ticket_below_threshold_returns_none():
    tickets = _FakeTicketPort()
    store = _MemoryStore()
    result = create_ticket_if_needed(
        _report("low"), tickets, store, threshold="high", title="t", description="d"
    )
    assert result is None
    assert tickets.calls == []


def test_create_ticket_meets_threshold_creates_and_records():
    tickets = _FakeTicketPort()
    store = _MemoryStore()
    report = _report("critical")
    url = create_ticket_if_needed(
        report, tickets, store, threshold="high", title="t", description="d"
    )
    assert url == "https://jira.example.com/browse/OPS-1"
    assert tickets.calls[0][2] == "critical"
    assert store.contains(report_fingerprint(report))


def test_duplicate_report_does_not_create_again():
    tickets = _FakeTicketPort()
    store = _MemoryStore()
    report = _report("critical")
    kwargs = {"threshold": "high", "title": "t", "description": "d"}
    create_ticket_if_needed(report, tickets, store, **kwargs)  # type: ignore[arg-type]
    second = create_ticket_if_needed(report, tickets, store, **kwargs)  # type: ignore[arg-type]
    assert second is None
    assert len(tickets.calls) == 1


def test_ports_are_runtime_checkable():
    assert isinstance(_FakeTicketPort(), TicketPort)
    assert isinstance(_MemoryStore(), TicketStorePort)


@pytest.mark.parametrize(
    ("severity", "threshold", "expected"),
    [
        ("critical", "critical", True),
        ("high", "critical", False),
        ("medium", "medium", True),
    ],
)
def test_threshold_matrix(severity: str, threshold: str, expected: bool):
    assert severity_at_or_above(severity, threshold) is expected


def test_json_ticket_store_roundtrip(tmp_path):
    from ops_ai_agent.adapters.ticket_store import JsonTicketStore

    path = tmp_path / "tickets.json"
    store = JsonTicketStore(path)
    assert not store.contains("fp1")
    store.record("fp1")
    reloaded = JsonTicketStore(path)
    assert reloaded.contains("fp1")
    assert not reloaded.contains("fp2")
