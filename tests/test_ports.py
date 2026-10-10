"""ports の構造とテストダブルのテスト。"""

import hashlib

from ops_ai_agent.ports.embeddings import EmbeddingPort
from ops_ai_agent.ports.llm import (
    LlmPort,
    LlmResponse,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolSpec,
    ToolUseBlock,
)
from ops_ai_agent.ports.notifier import NotifierPort
from ops_ai_agent.ports.retriever import KnowledgeRetrieverPort
from tests.fakes import FakeEmbedder, FakeLlm


def test_protocol_runtime_checkable():
    # FakeLlm/FakeEmbedder がプロトコルを満たすこと（静的にはmypyが検証）
    assert isinstance(FakeLlm([]), LlmPort)
    assert isinstance(FakeEmbedder(), EmbeddingPort)


def test_fake_llm_returns_scripted_responses_and_records():
    fake = FakeLlm(
        [
            LlmResponse(
                stop_reason="tool_use",
                content=[
                    ToolUseBlock(
                        id="t1", name="search_knowledge", input={"query": "5xx"}
                    ),
                ],
            ),
            LlmResponse(stop_reason="end_turn", content=[TextBlock(text='{"ok": 1}')]),
        ]
    )
    first = fake.complete(
        system="s", messages=[Message(role="user", content=[TextBlock(text="hi")])]
    )
    second = fake.complete(
        system="s",
        messages=[],
        tools=[ToolSpec(name="t", description="d", input_schema={"type": "object"})],
    )
    assert first.stop_reason == "tool_use"
    assert second.content[0].text == '{"ok": 1}'
    assert len(fake.requests) == 2
    assert fake.requests[1]["tools"] is not None


def test_fake_llm_exhausted_raises():
    fake = FakeLlm([])
    try:
        fake.complete(system="s", messages=[])
        raise AssertionError("AssertionError が発生すべき")
    except AssertionError as exc:
        assert "予期しない" in str(exc)


def test_message_holds_mixed_blocks():
    message = Message(
        role="user",
        content=[
            ToolResultBlock(tool_use_id="t1", content="ok", is_error=False),
            TextBlock(text="done"),
        ],
    )
    assert isinstance(message.content[0], ToolResultBlock)
    assert isinstance(message.content[1], TextBlock)


def test_fake_embedder_deterministic_and_query_document_consistent():
    embedder = FakeEmbedder()
    doc = embedder.embed_documents(["alpha", "beta"])
    assert len(doc) == 2
    assert len(doc[0]) == 16
    assert doc[0] != doc[1]
    assert embedder.embed_query("alpha") == doc[0]
    expected = [b / 255.0 for b in hashlib.sha256(b"alpha").digest()[:16]]
    assert doc[0] == expected


def test_retriever_notifier_protocol_signatures_exist():
    # プロトコルが import 可能で呼び出しシグネチャを持つことを静的に保証
    assert hasattr(KnowledgeRetrieverPort, "search")
    assert hasattr(KnowledgeRetrieverPort, "get_runbook")
    assert hasattr(NotifierPort, "send_report")
