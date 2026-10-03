"""CLI エントリポイントのテスト。"""

from typer.testing import CliRunner

from ops_ai_agent.cli import app

runner = CliRunner()


def test_help_shows_app_description():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Ops AI Agent" in result.output
