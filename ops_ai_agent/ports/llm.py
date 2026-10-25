"""LLMポート（ドメインが要求する唯一のLLM契約）。"""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class ToolSpec(BaseModel):
    """ツール定義（schema は additionalProperties: false を含むJSON Schema）。"""

    name: str
    description: str
    input_schema: dict[str, object]


class TextBlock(BaseModel):
    text: str


class ToolUseBlock(BaseModel):
    id: str
    name: str
    input: dict[str, object]


class ToolResultBlock(BaseModel):
    tool_use_id: str
    content: str
    is_error: bool = False


Block = TextBlock | ToolUseBlock | ToolResultBlock


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: list[Block]


class Usage(BaseModel):
    """1回の補完で消費したトークン数。"""

    input_tokens: int
    output_tokens: int


class LlmResponse(BaseModel):
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens" | "refusal" ...
    content: list[TextBlock | ToolUseBlock]
    usage: Usage | None = None


@runtime_checkable
class LlmPort(Protocol):
    """1ターン分の補完。エージェントループはドメイン側で所有する。"""

    def complete(
        self,
        *,
        system: str,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        output_schema: dict[str, object] | None = None,
    ) -> LlmResponse: ...
