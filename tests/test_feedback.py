"""フィードバック蓄積（ドメイン + JSONストア）のテスト。"""

from datetime import UTC, datetime

import pytest

from ops_ai_agent.adapters.feedback_store import JsonFeedbackStore
from ops_ai_agent.domain.feedback import FeedbackRecord, feedback_to_markdown


def _record(**overrides: object) -> FeedbackRecord:
    values: dict[str, object] = {
        "id": "fb-001",
        "helpful": True,
        "severity": "high",
        "summary": "アップストリームタイムアウトの疑い。",
        "possible_causes": ["アップストリーム遅延"],
        "recommended_actions": ["ロールバック判断"],
        "context": "webhook:alertmanager",
        "created_at": datetime(2026, 10, 19, 12, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return FeedbackRecord.model_validate(values)


class TestJsonFeedbackStore:
    def test_add_and_list_pending(self, tmp_path):
        store = JsonFeedbackStore(tmp_path / "feedback.json")
        store.add(_record())
        store.add(_record(id="fb-002", helpful=False))
        pending = store.list_pending()
        assert [record.id for record in pending] == ["fb-001", "fb-002"]

    def test_add_existing_id_raises(self, tmp_path):
        store = JsonFeedbackStore(tmp_path / "feedback.json")
        store.add(_record())
        with pytest.raises(ValueError, match="fb-001"):
            store.add(_record())

    def test_set_status_moves_out_of_pending(self, tmp_path):
        store = JsonFeedbackStore(tmp_path / "feedback.json")
        store.add(_record())
        store.set_status("fb-001", "accepted")
        assert store.list_pending() == []
        assert store.get("fb-001").status == "accepted"

    def test_set_status_unknown_id_raises(self, tmp_path):
        store = JsonFeedbackStore(tmp_path / "feedback.json")
        with pytest.raises(KeyError):
            store.set_status("missing", "accepted")

    def test_persists_across_instances(self, tmp_path):
        path = tmp_path / "feedback.json"
        store = JsonFeedbackStore(path)
        store.add(_record())
        reloaded = JsonFeedbackStore(path)
        assert reloaded.get("fb-001").summary == "アップストリームタイムアウトの疑い。"

    def test_empty_store_lists_nothing(self, tmp_path):
        store = JsonFeedbackStore(tmp_path / "feedback.json")
        assert store.list_pending() == []


class TestFeedbackToMarkdown:
    def test_renders_frontmatter_and_sections(self):
        text = feedback_to_markdown(_record())
        assert "id: FB-001" in text
        assert "severity: high" in text
        assert "アップストリームタイムアウトの疑い。" in text
        assert "アップストリーム遅延" in text
        assert "ロールバック判断" in text

    def test_marks_helpful_feedback(self):
        text = feedback_to_markdown(_record(helpful=True))
        assert "helpful: true" in text
