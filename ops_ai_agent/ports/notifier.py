"""通知ポート。"""

from typing import Protocol, runtime_checkable

from ops_ai_agent.domain.models import TriageReport


@runtime_checkable
class NotifierPort(Protocol):
    def send_report(self, report: TriageReport, *, context: str = "") -> None: ...
