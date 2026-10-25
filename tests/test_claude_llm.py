"""ClaudeLlmAdapter のテスト（SDKスタブ使用、実API不使用）。"""

from types import SimpleNamespace
from typing import Any, cast

import anthropic
import httpx
import pytest

from ops_ai_agent.adapters.claude_llm import ClaudeLlmAdapter, create_claude_llm
from ops_ai_agent.config import Settings
from ops_ai_agent.ports.llm import (
    Message,
    TextBlock,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
)


class StubAnthropic:
    """beta.messages.create を記録するSDKスタブ。"""

    def __init__(self, responses: list[Any]) -> None:
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _sdk_text_response(text: str, stop_reason: str = "end_turn") -> Any:
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
    )


def _sdk_tool_response() -> Any:
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[
            SimpleNamespace(type="thinking", thinking="..."),
            SimpleNamespace(type="tool_use", id="t1", name="search", input={"q": "x"}),
        ],
    )


def test_complete_sends_required_parameters():
    stub = StubAnthropic([_sdk_text_response("ok")])
    adapter = ClaudeLlmAdapter(cast(Any, stub))
    response = adapter.complete(
        system="sys", messages=[Message(role="user", content=[TextBlock(text="hi")])]
    )
    assert response.stop_reason == "end_turn"
    assert response.content[0].text == "ok"
    call = stub.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["max_tokens"] == 16000
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"] == {"effort": "high"}
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["fallbacks"] == "default"
    assert "tool_choice" not in call


def test_complete_with_tools_and_schema():
    stub = StubAnthropic([_sdk_tool_response()])
    adapter = ClaudeLlmAdapter(cast(Any, stub))
    tools = [
        ToolSpec(
            name="t",
            description="d",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )
    ]
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    response = adapter.complete(
        system="s",
        messages=[Message(role="user", content=[TextBlock(text="q")])],
        tools=tools,
        output_schema=schema,
    )
    call = stub.calls[0]
    assert call["tools"] == [
        {
            "name": "t",
            "description": "d",
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        }
    ]
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": schema}
    # thinkingブロックはスキップされ、tool_useのみドメインへ渡る
    assert isinstance(response.content[0], ToolUseBlock)
    assert response.content[0].id == "t1"
    assert response.content[0].input == {"q": "x"}


def test_message_conversion_roundtrip_shapes():
    stub = StubAnthropic([_sdk_text_response("ok")])
    adapter = ClaudeLlmAdapter(cast(Any, stub))
    messages = [
        Message(role="user", content=[TextBlock(text="q")]),
        Message(role="assistant", content=[ToolUseBlock(id="t1", name="n", input={})]),
        Message(
            role="user",
            content=[ToolResultBlock(tool_use_id="t1", content="r", is_error=True)],
        ),
    ]
    adapter.complete(system="s", messages=messages)
    sent = stub.calls[0]["messages"]
    assert sent[0] == {"role": "user", "content": [{"type": "text", "text": "q"}]}
    assert sent[1]["content"][0] == {
        "type": "tool_use",
        "id": "t1",
        "name": "n",
        "input": {},
    }
    assert sent[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "t1",
        "content": "r",
        "is_error": True,
    }


def _sdk_status_error(cls: type[Exception], status: int) -> Exception:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("err", response=httpx.Response(status, request=request), body=None)


def _retries_adapter(stub: StubAnthropic) -> ClaudeLlmAdapter:
    return ClaudeLlmAdapter(cast(Any, stub), sleeper=lambda _s: None)


def test_retries_on_rate_limit_then_succeeds():
    stub = StubAnthropic(
        [_sdk_status_error(anthropic.RateLimitError, 429)] * 2
        + [_sdk_text_response("ok")]
    )
    response = _retries_adapter(stub).complete(
        system="s", messages=[Message(role="user", content=[TextBlock(text="q")])]
    )
    assert response.content[0].text == "ok"
    assert len(stub.calls) == 3


def test_retries_on_timeout_and_server_error():
    timeout = anthropic.APITimeoutError(
        httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    stub = StubAnthropic(
        [
            timeout,
            _sdk_status_error(anthropic.InternalServerError, 500),
            _sdk_text_response("ok"),
        ]
    )
    response = _retries_adapter(stub).complete(
        system="s", messages=[Message(role="user", content=[TextBlock(text="q")])]
    )
    assert response.content[0].text == "ok"
    assert len(stub.calls) == 3


def test_gives_up_after_max_retries():
    stub = StubAnthropic([_sdk_status_error(anthropic.RateLimitError, 429)] * 5)
    with pytest.raises(anthropic.RateLimitError):
        _retries_adapter(stub).complete(
            system="s", messages=[Message(role="user", content=[TextBlock(text="q")])]
        )
    assert len(stub.calls) == 3  # 初回 + リトライ2回（既定値）


def test_does_not_retry_on_bad_request():
    stub = StubAnthropic([_sdk_status_error(anthropic.BadRequestError, 400)])
    with pytest.raises(anthropic.BadRequestError):
        _retries_adapter(stub).complete(
            system="s", messages=[Message(role="user", content=[TextBlock(text="q")])]
        )
    assert len(stub.calls) == 1


def test_create_claude_llm_disables_sdk_retry_and_wires_max_retries(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_client(**kwargs: Any) -> StubAnthropic:
        captured.update(kwargs)
        return StubAnthropic([_sdk_text_response("ok")])

    monkeypatch.setattr(anthropic, "Anthropic", fake_client)
    settings = Settings(
        _env_file=None,
        anthropic_api_key="k",
        max_retries=5,  # type: ignore[call-arg]
    )
    adapter = create_claude_llm(settings)
    assert captured["max_retries"] == 0  # SDK内蔵リトライは無効化
    assert adapter._max_retries == 5  # 設定値がアダプタへ反映される


def test_create_claude_llm_requires_key(tmp_path, monkeypatch):
    from ops_ai_agent.config import Settings

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        create_claude_llm(settings)
