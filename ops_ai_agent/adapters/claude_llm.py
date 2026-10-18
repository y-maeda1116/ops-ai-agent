"""Claude API アダプタ（LlmPort実装）。"""

import time
from collections.abc import Callable
from typing import Any, cast

import anthropic

from ops_ai_agent.adapters.retry import call_with_retry
from ops_ai_agent.config import Settings
from ops_ai_agent.ports.llm import (
    Block,
    LlmResponse,
    Message,
    TextBlock,
    ToolSpec,
    ToolUseBlock,
)

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _is_retryable_error(exc: Exception) -> bool:
    """429 / タイムアウト / 接続エラー / 5xx を再試行対象と判定する。"""
    if isinstance(
        exc, (anthropic.RateLimitError, anthropic.APIConnectionError)
    ):  # APIConnectionError はタイムアウトを含む
        return True
    return isinstance(exc, anthropic.APIStatusError) and 500 <= exc.status_code < 600


class ClaudeLlmAdapter:
    """anthropic SDK を用いる LlmPort 実装。"""

    def __init__(
        self,
        client: anthropic.Anthropic,
        *,
        model: str = "claude-opus-5-5",
        effort: str = "high",
        max_tokens: int = 16000,
        max_retries: int = 2,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client: Any = client
        self._model = model
        self._effort = effort
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._sleeper = sleeper

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        output_schema: dict[str, object] | None = None,
    ) -> LlmResponse:
        output_config: dict[str, object] = {"effort": self._effort}
        if output_schema is not None:
            output_config["format"] = {
                "type": "json_schema",
                "schema": output_schema,
            }
        kwargs: dict[str, object] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [self._to_sdk_message(m) for m in messages],
            "thinking": {"type": "adaptive"},
            "output_config": output_config,
        }
        if tools is not None:
            kwargs["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "strict": True,
                }
                for tool in tools
            ]
        response = call_with_retry(
            lambda: self._client.beta.messages.create(
                betas=[_FALLBACK_BETA], fallbacks="default", **kwargs
            ),
            max_retries=self._max_retries,
            retryable=_is_retryable_error,
            sleeper=self._sleeper,
        )
        return self._to_domain_response(response)

    def _to_sdk_message(self, message: Message) -> dict[str, object]:
        return {
            "role": message.role,
            "content": [self._to_sdk_block(block) for block in message.content],
        }

    def _to_sdk_block(self, block: Block) -> dict[str, object]:
        if isinstance(block, TextBlock):
            return {"type": "text", "text": block.text}
        if isinstance(block, ToolUseBlock):
            return {
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            }
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": block.content,
            "is_error": block.is_error,
        }

    def _to_domain_response(self, response: Any) -> LlmResponse:
        content: list[TextBlock | ToolUseBlock] = []
        for sdk_block in response.content:
            kind = getattr(sdk_block, "type", None)
            if kind == "text":
                content.append(TextBlock(text=sdk_block.text))
            elif kind == "tool_use":
                content.append(
                    ToolUseBlock(
                        id=sdk_block.id,
                        name=sdk_block.name,
                        input=cast(dict[str, object], sdk_block.input),
                    )
                )
            # thinking 等のその他ブロックはスキップ
        return LlmResponse(stop_reason=response.stop_reason, content=content)


def create_claude_llm(settings: Settings) -> ClaudeLlmAdapter:
    """設定から ClaudeLlmAdapter を構築する（キー未設定時は ValueError）。"""
    # SDK内蔵リトライを無効化し、再試行ポリシーはアダプタ側で一元管理する
    client = anthropic.Anthropic(
        api_key=settings.require_anthropic_key(), max_retries=0
    )
    return ClaudeLlmAdapter(
        client,
        model=settings.model,
        effort=settings.effort,
        max_retries=settings.max_retries,
    )
