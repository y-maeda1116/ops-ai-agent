"""Slack通知アダプタ（NotifierPort実装）。"""

from typing import Any

from slack_sdk import WebClient

from ops_ai_agent.config import Settings
from ops_ai_agent.domain.models import TriageReport

SEVERITY_COLOR = {
    "critical": "#dc2626",
    "high": "#ea580c",
    "medium": "#d97706",
    "low": "#6b7280",
}

_ESCALATION = {True: "要", False: "不要"}


def report_to_blocks(report: TriageReport) -> list[dict[str, object]]:
    """TriageReport を Block Kit blocks へ変換する。"""
    blocks: list[dict[str, object]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 障害一次切り分けレポート（{report.severity}）",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*重要度*: {report.severity} ／ *信頼度*: {report.confidence}"
                    f" ／ *エスカレーション*: "
                    f"{_ESCALATION[report.requires_human_escalation]}\n"
                    f"{report.summary}"
                ),
            },
        },
    ]
    if report.possible_causes:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*原因候補*"},
            }
        )
        blocks.extend(
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"• {cause.description}"},
                    {"type": "mrkdwn", "text": f"根拠: {cause.evidence}"},
                ],
            }
            for cause in report.possible_causes
        )
    if report.recommended_actions:
        actions_text = "\n".join(
            f"{action.order}. {action.description}（{action.owner_hint}）"
            for action in report.recommended_actions
        )
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*推奨初期対応*\n{actions_text}"},
            }
        )
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "参照インシデント: "
                    + (", ".join(report.referenced_incidents) or "なし"),
                }
            ],
        }
    )
    return blocks


class SlackNotifier:
    """NotifierPort の Slack 実装。"""

    def __init__(self, client: WebClient, channel: str) -> None:
        self._client = client
        self._channel = channel

    def send_report(self, report: TriageReport, *, context: str = "") -> None:
        blocks = report_to_blocks(report)
        if context:
            blocks.insert(
                1,
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"対象: {context}"}],
                },
            )
        self._client.chat_postMessage(
            channel=self._channel,
            blocks=blocks,
            text=f"障害一次切り分けレポート（{report.severity}）: {report.summary}",
        )


def create_slack_notifier(settings: Settings) -> SlackNotifier:
    """設定から SlackNotifier を構築する（トークン未設定時は ValueError）。"""
    if settings.slack_bot_token is None:
        msg = "SLACK_BOT_TOKEN が設定されていません。.env.example を参照してください。"
        raise ValueError(msg)
    client: Any = WebClient(token=settings.slack_bot_token)
    return SlackNotifier(client, settings.slack_channel)
