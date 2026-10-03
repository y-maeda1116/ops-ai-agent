"""ops-agent コマンドラインインターフェース。"""

import typer

app = typer.Typer(
    help="Ops AI Agent - 障害一次切り分け・ログ解析エージェント",
    no_args_is_help=True,
)


@app.callback()
def _callback() -> None:
    """サブコマンド（triage / ask 等）を持つグループのルール。"""


def main() -> None:
    app()


if __name__ == "__main__":
    main()
