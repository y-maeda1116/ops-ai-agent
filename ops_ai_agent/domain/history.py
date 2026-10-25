"""triage 実行履歴（監査ログ）のドメインモデル。"""

from pydantic import BaseModel

from ops_ai_agent.domain.models import TriageReport


class TriageHistoryRecord(BaseModel):
    """triage 実行1回の履歴レコード。

    context は実行元（例: "webhook:alertmanager"、"slack:C123"、ログファイルパス）。
    """

    id: str
    created_at: str
    context: str
    report: TriageReport
    thread_ts: str | None = None
