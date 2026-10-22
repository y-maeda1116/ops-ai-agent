"""usage記録（トークン/コスト）のテスト。"""

from pathlib import Path
from types import SimpleNamespace

import anthropic
from typer.testing import CliRunner

from ops_ai_agent import cli as cli_module
from ops_ai_agent.adapters.claude_llm import ClaudeLlmAdapter, create_claude_llm
from ops_ai_agent.adapters.usage_log import (
    JsonlUsageLogger,
    estimate_cost_usd,
)
from ops_ai_agent.config import Settings
from ops_ai_agent.ports.llm import Message, TextBlock, Usage
from tests.test_claude_llm import StubAnthropic, _sdk_text_response

runner = CliRunner()

_MSG = [Message(role="user", content=[TextBlock(text="hi")])]


def test_estimate_cost_usd_known_and_unknown_models():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = estimate_cost_usd("claude-opus-5-5", usage)
    assert cost is not None and cost > 0
    assert estimate_cost_usd("totally-unknown-model", usage) is None


def test_jsonl_usage_logger_roundtrip_and_summary(tmp_path: Path):
    path = tmp_path / "usage.jsonl"
    logger = JsonlUsageLogger(path)
    logger.record("claude-opus-5-5", Usage(input_tokens=100, output_tokens=50))
    logger.record("claude-opus-5-5", Usage(input_tokens=200, output_tokens=10))
    reloaded = JsonlUsageLogger(path)
    records = reloaded.load()
    assert len(records) == 2
    assert records[0].input_tokens == 100
    summary = reloaded.summarize()
    assert summary.runs == 2
    assert summary.input_tokens == 300
    assert summary.output_tokens == 60
    assert summary.total_cost_usd is not None and summary.total_cost_usd > 0


def test_usage_logger_empty_summary(tmp_path: Path):
    logger = JsonlUsageLogger(tmp_path / "usage.jsonl")
    summary = logger.summarize()
    assert summary.runs == 0
    assert summary.total_cost_usd == 0.0


def _adapter_with_usage(on_usage) -> ClaudeLlmAdapter:
    response = _sdk_text_response("{}")
    response.usage = SimpleNamespace(input_tokens=120, output_tokens=45)
    return ClaudeLlmAdapter(
        StubAnthropic([response]), model="claude-opus-5-5", on_usage=on_usage
    )


def test_adapter_maps_usage_into_response_and_calls_callback():
    received: list[tuple[str, Usage]] = []
    adapter = _adapter_with_usage(lambda model, usage: received.append((model, usage)))
    response = adapter.complete(system="s", messages=_MSG)
    assert response.usage is not None
    assert response.usage.input_tokens == 120
    assert response.usage.output_tokens == 45
    assert received == [("claude-opus-5-5", response.usage)]


def test_adapter_without_usage_response_leaves_usage_none():
    received: list[object] = []
    adapter = ClaudeLlmAdapter(
        StubAnthropic([_sdk_text_response("{}")]),
        model="claude-opus-5-5",
        on_usage=lambda m, u: received.append((m, u)),
    )
    response = adapter.complete(system="s", messages=_MSG)
    assert response.usage is None
    assert received == []


def test_create_claude_llm_wires_default_jsonl_logger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    response = _sdk_text_response("{}")
    response.usage = SimpleNamespace(input_tokens=120, output_tokens=45)
    stub = StubAnthropic([response])
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kwargs: stub)
    llm = create_claude_llm(Settings())
    llm.complete(system="s", messages=_MSG)
    records = JsonlUsageLogger(Path("data/usage.jsonl")).load()
    assert len(records) == 1
    assert records[0].input_tokens == 120


def test_usage_command_prints_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logger = JsonlUsageLogger(Path("data/usage.jsonl"))
    logger.record("claude-opus-5-5", Usage(input_tokens=1000, output_tokens=500))
    result = runner.invoke(cli_module.app, ["usage"])
    assert result.exit_code == 0, result.output
    assert "input_tokens=1000" in result.stdout
    assert "output_tokens=500" in result.stdout


def test_usage_command_with_no_records(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(cli_module.app, ["usage"])
    assert result.exit_code == 0
    assert "記録はありません" in result.stdout
