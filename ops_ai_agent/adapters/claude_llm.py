"""Claude API アダプタ（LlmPort実装）。"""

from typing import Any, cast

import anthropic

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


class ClaudeLlmAdapter:
    """anthropic SDK を用いる LlmPort 実装。"""

    def __init__(
        self,
        client: anthropic.Anthropic,
        *,
        model: str = "claude-opus-5-5",
        effort: str = "high",
        max_tokens: int = 16000,
    ) -> None:
        self._client: Any = client
        self._model = model
        self._effort = effort
        self._max_tokens = max_tokens

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
        response = self._client.beta.messages.create(
            betas=[_FALLBACK_BETA], fallbacks="default", **kwargs
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
    client = anthropic.Anthropic(api_key=settings.require_anthropic_key())
    return ClaudeLlmAdapter(client, model=settings.model, effort=settings.effort)
