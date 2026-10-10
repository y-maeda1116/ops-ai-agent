"""Slack Bot（Socket Mode）。メンション/DMで切り分けを実行しスレッドに返信する。"""

import re
from collections.abc import Callable
from typing import Any

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from ops_ai_agent.adapters.slack import report_to_blocks
from ops_ai_agent.cli import _build_llm, _build_retriever
from ops_ai_agent.config import Settings
from ops_ai_agent.domain.ingest import parse_log_text
from ops_ai_agent.domain.triage import TriageService

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
        say(text=_ERROR_REPLY, thread_ts=thread_ts)
        return
    say(
        blocks=report_to_blocks(report),
        thread_ts=thread_ts,
        text=f"障害一次切り分けレポート（{report.severity}）: {report.summary}",
    )


def create_app(bot_token: str, *, service: TriageService, settings: Settings) -> App:
    """slack_bolt App を構築しイベントハンドラを登録する。

    Socket Mode 運用のため起動時の auth.test 検証は無効化する
    （接続は SocketModeHandler の app token で確立される）。
    """
    app = App(token=bot_token, token_verification_enabled=False)

    @app.event("app_mention")
    def on_mention(event: dict[str, Any], say: Callable[..., None]) -> None:
        handle_triage_request(event, say, service=service, settings=settings)

    @app.message("")
    def on_message(event: dict[str, Any], say: Callable[..., None]) -> None:
        handle_triage_request(event, say, service=service, settings=settings)

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
    )
    app = create_app(settings.slack_bot_token, service=service, settings=settings)
    # SocketModeHandler は型スタブを持たないため Any 経由で起動する
    handler: Any = SocketModeHandler(app, settings.require_slack_app_token())
    handler.start()
