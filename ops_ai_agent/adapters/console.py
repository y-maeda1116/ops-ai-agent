"""stdout へのMarkdownレポート出力（NotifierPort実装）。"""

import typer

from ops_ai_agent.domain.models import TriageReport

_SEVERITY_ICON = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "⚪",
}


def report_to_markdown(report: TriageReport, *, context: str = "") -> str:
    """TriageReport をMarkdown文字列へ整形する。"""
    icon = _SEVERITY_ICON[report.severity]
    lines = [
        f"# {icon} 障害一次切り分けレポート",
        "",
        f"**重要度**: {report.severity} ／ **信頼度**: {report.confidence} ／ "
        f"**エスカレーション**: {'要' if report.requires_human_escalation else '不要'}",
    ]
    if context:
        lines.append(f"**対象**: {context}")
    lines.extend(["", "## 要約", "", report.summary])
    lines.extend(["", "## 原因候補", ""])
    if report.possible_causes:
        lines.extend(
            f"- {cause.description}（根拠: {cause.evidence}）"
            for cause in report.possible_causes
        )
    else:
        lines.append("- （特定できず）")
    lines.extend(["", "## 推奨初期対応", ""])
    if report.recommended_actions:
        lines.extend(
            f"{action.order}. {action.description}（担当観点: {action.owner_hint}）"
            for action in report.recommended_actions
        )
    else:
        lines.append("（対応策提示できず）")
    lines.extend(["", "## 参照インシデント", ""])
    lines.append(
        ", ".join(report.referenced_incidents)
        if report.referenced_incidents
        else "なし"
    )
    return "\n".join(lines)


class ConsoleNotifier:
    """NotifierPort の stdout 実装。"""

    def send_report(self, report: TriageReport, *, context: str = "") -> None:
        typer.echo(report_to_markdown(report, context=context))
