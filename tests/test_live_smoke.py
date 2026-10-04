"""実APIを使うスモークテスト（pytest -m live でのみ実行、CIではスキップ）。"""

import pytest

from ops_ai_agent.adapters.claude_llm import create_claude_llm
from ops_ai_agent.adapters.voyage_embeddings import create_voyage_embedder
from ops_ai_agent.config import Settings
from ops_ai_agent.ports.llm import Message, TextBlock

pytestmark = pytest.mark.live


def test_live_claude_end_turn():
    settings = Settings()
    llm = create_claude_llm(settings)
    response = llm.complete(
        system="1語で答えてください。",
        messages=[Message(role="user", content=[TextBlock(text="1+1は？")])],
    )
    assert response.stop_reason == "end_turn"
    assert any(isinstance(b, TextBlock) for b in response.content)


def test_live_voyage_embedding():
    embedder = create_voyage_embedder(Settings())
    vector = embedder.embed_query("api-gateway 5xx急増")
    assert len(vector) > 0
    assert all(isinstance(x, float) for x in vector)
