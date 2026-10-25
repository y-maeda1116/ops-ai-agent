"""triage フィードバックのドメインモデルとナレッジ化。"""

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from ops_ai_agent.domain.models import TriageReport


class FeedbackRecord(BaseModel):
    """Slack ボタン等で収集した triage 評価。"""

    id: str
    helpful: bool
    severity: str
    summary: str
    possible_causes: list[str]
    recommended_actions: list[str]
    context: str
    created_at: datetime
    status: Literal["pending", "accepted", "rejected"] = "pending"


def feedback_value_from_report(report: TriageReport, context: str) -> str:
    """Slack ボタン value 用のコンパクトな JSON を生成する。"""
    return json.dumps(
        {
            "summary": report.summary,
            "severity": report.severity,
            "possible_causes": [c.description for c in report.possible_causes],
            "recommended_actions": [a.description for a in report.recommended_actions],
            "context": context,
        },
        ensure_ascii=False,
    )


def feedback_to_markdown(record: FeedbackRecord) -> str:
    """採択済みフィードバックを過去インシデント形式の Markdown へ変換する。"""
    created = record.created_at.date().isoformat()
    lines = [
        "---",
        f"id: {record.id.upper()}",
        f"title: {record.summary}",
        "service: unknown",
        f"severity: {record.severity}",
        "tags:",
        "  - feedback",
        f"helpful: {str(record.helpful).lower()}",
        f"resolved_at: {created}",
        "---",
        "",
        f"# {record.summary}",
        "",
        "## 症状",
        f"- triage レポート（{record.severity}）へのフィードバック: "
        f"{'役に立った' if record.helpful else '役に立たなかった'}",
        f"- 対象: {record.context or 'unknown'}",
        "",
        "## 原因候補",
    ]
    lines.extend(f"- {cause}" for cause in record.possible_causes)
    lines.append("")
    lines.append("## 対応")
    lines.extend(f"- {action}" for action in record.recommended_actions)
    lines.append("")
    return "\n".join(lines)
