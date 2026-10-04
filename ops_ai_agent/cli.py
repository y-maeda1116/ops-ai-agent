"""ops-agent コマンドラインインターフェース。"""

from pathlib import Path

import typer

from ops_ai_agent.adapters.voyage_embeddings import create_voyage_embedder
from ops_ai_agent.config import Settings
from ops_ai_agent.rag.indexer import build_index

app = typer.Typer(
    help="Ops AI Agent - 障害一次切り分け・ログ解析エージェント",
    no_args_is_help=True,
)


@app.callback()
def _callback() -> None:
    """サブコマンド（index / triage / ask）を持つグループのルール。"""


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
