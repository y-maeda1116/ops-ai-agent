"""チケット自動起票ユースケース（しきい値判定・重複防止）。"""

import hashlib

from ops_ai_agent.domain.models import TriageReport
from ops_ai_agent.ports.ticket import TicketPort, TicketStorePort

_SEVERITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def severity_at_or_above(severity: str, threshold: str) -> bool:
    """severity がしきい値以上の重要度かを判定する。"""
    return _SEVERITY_RANK.get(severity, -1) >= _SEVERITY_RANK.get(threshold, 0)


def report_fingerprint(report: TriageReport) -> str:
    """同じ障害の再検出を判定するフィンガープリント（summary基準）。"""
    return hashlib.sha256(report.summary.encode("utf-8")).hexdigest()


def create_ticket_if_needed(
    report: TriageReport,
    tickets: TicketPort,
    store: TicketStorePort,
    *,
    threshold: str,
    title: str,
    description: str,
) -> str | None:
    """しきい値以上の重要度かつ未起票ならチケットを作成してURLを返す。

    しきい値未満は None。起票済み（フィンガープリント記録済み）も None。
    """
    if not severity_at_or_above(report.severity, threshold):
        return None
    fingerprint = report_fingerprint(report)
    if store.contains(fingerprint):
        return None
    url = tickets.create_ticket(title, description, severity=report.severity)
    store.record(fingerprint)
    return url
