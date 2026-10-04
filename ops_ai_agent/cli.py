"""ops-agent コマンドラインインターフェース。"""

from pathlib import Path
from typing import Literal

import typer

from ops_ai_agent.adapters.claude_llm import create_claude_llm
from ops_ai_agent.adapters.console import ConsoleNotifier
from ops_ai_agent.adapters.json_vector_store import JsonVectorStore
from ops_ai_agent.adapters.knowledge_base import KnowledgeBase
from ops_ai_agent.adapters.voyage_embeddings import create_voyage_embedder
from ops_ai_agent.config import Settings
from ops_ai_agent.domain.ingest import parse_log_text, read_log_source
from ops_ai_agent.domain.triage import TriageRefusalError, TriageService
from ops_ai_agent.ports.llm import LlmPort
from ops_ai_agent.ports.notifier import NotifierPort
from ops_ai_agent.ports.retriever import KnowledgeRetrieverPort
from ops_ai_agent.rag.indexer import build_index

app = typer.Typer(
    help="Ops AI Agent - 障害一次切り分け・ログ解析エージェント",
    no_args_is_help=True,
)


@app.callback()
def _callback() -> None:
    """サブコマンド（index / triage / ask）を持つグループのルール。"""


def _build_retriever(settings: Settings) -> KnowledgeRetrieverPort:
    store = JsonVectorStore(settings.data_dir / "index.json")
    embedder = create_voyage_embedder(settings)
    return KnowledgeBase(store, embedder, settings.knowledge_dir / "runbooks")


def _build_llm(settings: Settings) -> LlmPort:
    return create_claude_llm(settings)


def _build_notifier(kind: str) -> NotifierPort:
    if kind == "console":
        return ConsoleNotifier()
    msg = f"未知の通知先: {kind}"
    raise typer.BadParameter(msg)


@app.command()
def index(
    knowledge_dir: Path | None = typer.Option(
        None, "--knowledge-dir", help="ナレッジディレクトリ"
    ),
    output: Path | None = typer.Option(None, "--output", help="index.jsonの出力先"),
) -> None:
    """ナレッジ（過去インシデント/runbook）のインデックスを構築する。"""
    settings = Settings()
    count = build_index(
        knowledge_dir or settings.knowledge_dir,
        create_voyage_embedder(settings),
        output or settings.data_dir / "index.json",
    )
    typer.echo(f"インデックス構築が完了しました（チャンク数: {count}）")


@app.command()
def triage(
    log: Path | None = typer.Option(
        None, "--log", "-l", help="ログファイルパス（'-'でstdin）"
    ),
    alert: str = typer.Option(None, "--alert", "-a", help="アラート本文"),
    notify: Literal["console", "slack"] = typer.Option(
        "console", "--notify", help="通知先"
    ),
) -> None:
    """ログ/アラートを一次切り分けしてレポートを出力する。"""
    if log is None and not alert:
        msg = "--log か --alert のどちらかを指定してください"
        raise typer.BadParameter(msg)
    settings = Settings()
    result = parse_log_text(read_log_source(str(log))) if log is not None else None
    if result is not None and not any(
        record.level != "unknown" for record in result.records
    ):
        msg = "ログファイルから有効なログ行を解析できませんでした"
        raise typer.BadParameter(msg)
    records = result.records if result is not None else []
    context = str(log) if log is not None else "alert"
    try:
        service = TriageService(
            _build_llm(settings),
            _build_retriever(settings),
            max_iterations=settings.max_iterations,
        )
        report = service.triage(records, alert_text=alert)
    except (ValueError, TriageRefusalError) as exc:
        typer.echo(f"エラー: {exc}", err=True)
        raise typer.Exit(1) from exc
    _build_notifier(notify).send_report(report, context=context)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
