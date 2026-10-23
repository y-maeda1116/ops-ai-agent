"""フィードバックの軽量JSONストア。"""

from pathlib import Path

from pydantic import BaseModel, Field

from ops_ai_agent.domain.feedback import FeedbackRecord


class _FeedbackFile(BaseModel):
    version: int = 1
    records: list[FeedbackRecord] = Field(default_factory=list)


class JsonFeedbackStore:
    """data/feedback.json の永続を担うアダプタ。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def add(self, record: FeedbackRecord) -> None:
        file = self._load()
        if any(existing.id == record.id for existing in file.records):
            msg = f"フィードバックIDが重複しています: {record.id}"
            raise ValueError(msg)
        file.records.append(record)
        self._save(file)

    def list_pending(self) -> list[FeedbackRecord]:
        return [record for record in self._load().records if record.status == "pending"]

    def get(self, feedback_id: str) -> FeedbackRecord:
        for record in self._load().records:
            if record.id == feedback_id:
                return record
        msg = f"フィードバックが見つかりません: {feedback_id}"
        raise KeyError(msg)

    def set_status(self, feedback_id: str, status: str) -> None:
        file = self._load()
        for record in file.records:
            if record.id == feedback_id:
                record.status = status  # type: ignore[assignment]
                self._save(file)
                return
        msg = f"フィードバックが見つかりません: {feedback_id}"
        raise KeyError(msg)

    def _load(self) -> _FeedbackFile:
        if not self._path.exists():
            return _FeedbackFile()
        return _FeedbackFile.model_validate_json(self._path.read_text(encoding="utf-8"))

    def _save(self, file: _FeedbackFile) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(file.model_dump_json(indent=2), encoding="utf-8")
