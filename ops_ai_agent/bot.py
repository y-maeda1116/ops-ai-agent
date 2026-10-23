"""Slack Bot（Socket Mode）。メンション/DMで切り分けを実行しスレッドに返信する。"""

import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from ops_ai_agent.adapters.feedback_store import JsonFeedbackStore
from ops_ai_agent.adapters.prometheus import create_prometheus_metrics
from ops_ai_agent.adapters.slack import report_to_blocks
from ops_ai_agent.cli import (
    _build_llm,
    _build_retriever,
    _maybe_create_ticket,
    _save_history,
)
from ops_ai_agent.config import Settings
from ops_ai_agent.domain.feedback import FeedbackRecord, feedback_value_from_report
from ops_ai_agent.domain.ingest import parse_log_text
from ops_ai_agent.domain.triage import TriageService

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")
_FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)

_USAGE = (
    "ログテキストをコードブロック（``` で囲む）付きで送ってください。"
    "例: <@bot> 切り分けお願い\n```\n2026-10-03T12:00:00Z ERROR [api] ...\n```"
)

_ERROR_REPLY = (
    "切り分けに失敗しました。時間をおいて再試行するか、"
    "担当者へエスカレーションしてください。"
)

_FEEDBACK_THANKS = (
    "フィードバックを記録しました（承認待ち）。"
    "承認後、`ops-agent feedback accept` でナレッジに反映できます。"
)

_FEEDBACK_ERROR = "フィードバックの記録に失敗しました。"


def _new_feedback_id() -> str:
    return f"fb-{uuid4().hex[:12]}"


def extract_log_text(text: str) -> str:
    """メンションを除去し、コードフェンス内のテキストを抽出する。"""
    without_mention = _MENTION_RE.sub("", text).strip()
    fences = _FENCE_RE.findall(without_mention)
    if fences:
        return "\n".join(fence.strip() for fence in fences)
    return without_mention


def handle_triage_request(
    event: dict[str, Any],
    say: Callable[..., None],
    *,
    service: TriageService,
    settings: Settings,
) -> None:
    """メンション/DM 受信時に切り分けを実行してスレッドへ返信する。"""
    thread_ts = event.get("thread_ts") or event.get("ts")
    log_text = extract_log_text(str(event.get("text", "")))
    result = parse_log_text(log_text)
    if not any(record.level != "unknown" for record in result.records):
        say(text=_USAGE, thread_ts=thread_ts)
        return
    try:
        report = service.triage(result.records, alert_text=str(event.get("text", "")))
    except Exception:
        # ユーザーには汎用返信とし、原因はスタックトレースごとログへ残す
        logger.exception("triage failed")
        say(text=_ERROR_REPLY, thread_ts=thread_ts)
        return
    feedback_value = feedback_value_from_report(
        report, context=f"slack:{event.get('channel', '')}"
    )
    say(
        blocks=report_to_blocks(report, feedback_value=feedback_value),
        thread_ts=thread_ts,
        text=f"障害一次切り分けレポート（{report.severity}）: {report.summary}",
    )
    # 実行履歴（監査ログ）をSlack通知と紐付けて保存する
    try:
        _save_history(
            settings,
            report,
            f"slack:{event.get('channel', '')}",
            thread_ts=str(thread_ts) if thread_ts else None,
        )
    except Exception:
        logger.exception("history save failed")
    try:
        ticket_url = _maybe_create_ticket(settings, report)
    except Exception:
        logger.exception("ticket creation failed")
        ticket_url = None
    if ticket_url is not None:
        say(
            text=f"インシデントチケットを起票しました: {ticket_url}",
            thread_ts=thread_ts,
        )


def handle_feedback_action(
    body: dict[str, Any],
    respond: Callable[..., None],
    *,
    store: JsonFeedbackStore,
    id_factory: Callable[[], str] = _new_feedback_id,
    now_factory: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
) -> None:
    """フィードバックボタン（block_actions）の受信を記録する。"""
    try:
        action = body["actions"][0]
        value = json.loads(str(action["value"]))
        record = FeedbackRecord(
            id=id_factory(),
            helpful=str(action["action_id"]) == "feedback_helpful",
            severity=str(value["severity"]),
            summary=str(value["summary"]),
            possible_causes=[str(c) for c in value["possible_causes"]],
            recommended_actions=[str(a) for a in value["recommended_actions"]],
            context=str(value.get("context", "")),
            created_at=now_factory(),
        )
        store.add(record)
    except Exception:
        # ボタン value は不正な可能性があるため、失敗はログに残して通知
        logger.exception("feedback action failed")
        respond(text=_FEEDBACK_ERROR)
        return
    respond(text=_FEEDBACK_THANKS, thread_ts=body.get("message", {}).get("ts"))


def create_app(
    bot_token: str,
    *,
    service: TriageService,
    settings: Settings,
    feedback_store: JsonFeedbackStore | None = None,
) -> App:
    """slack_bolt App を構築しイベントハンドラを登録する。

    Socket Mode 運用のため起動時の auth.test 検証は無効化する
    （接続は SocketModeHandler の app token で確立される）。
    """
    app = App(token=bot_token, token_verification_enabled=False)
    if feedback_store is None:
        feedback_store = JsonFeedbackStore(settings.data_dir / "feedback.json")

    @app.event("app_mention")
    def on_mention(event: dict[str, Any], say: Callable[..., None]) -> None:
        handle_triage_request(event, say, service=service, settings=settings)

    @app.message("")
    def on_message(event: dict[str, Any], say: Callable[..., None]) -> None:
        handle_triage_request(event, say, service=service, settings=settings)

    @app.action("feedback_helpful")
    def on_feedback_helpful(body: dict[str, Any], respond: Callable[..., None]) -> None:
        handle_feedback_action(body, respond, store=feedback_store)

    @app.action("feedback_not_helpful")
    def on_feedback_not_helpful(
        body: dict[str, Any], respond: Callable[..., None]
    ) -> None:
        handle_feedback_action(body, respond, store=feedback_store)

    return app


def run_bot(settings: Settings) -> None:
    """Socket Mode でBotを起動する。"""
    if settings.slack_bot_token is None:
        msg = "SLACK_BOT_TOKEN が設定されていません。"
        raise ValueError(msg)
    service = TriageService(
        _build_llm(settings),
        _build_retriever(settings),
        max_iterations=settings.max_iterations,
        metrics=create_prometheus_metrics(settings),
    )
    app = create_app(settings.slack_bot_token, service=service, settings=settings)
    # SocketModeHandler は型スタブを持たないため Any 経由で起動する
    handler: Any = SocketModeHandler(app, settings.require_slack_app_token())
    handler.start()
