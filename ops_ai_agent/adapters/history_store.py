"""triage 実行履歴のJSONLストア（監査ログ・追記のみ）。"""

import logging
from pathlib import Path

from ops_ai_agent.domain.history import TriageHistoryRecord

logger = logging.getLogger(__name__)

type Records = list[TriageHistoryRecord]


class JsonHistoryStore:
    """data/history.jsonl への追記記録（監査ログのため上書きしない）。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def add(self, record: TriageHistoryRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as file:
            file.write(record.model_dump_json() + "\n")

    def get(self, record_id: str) -> TriageHistoryRecord:
        for record in self._load_all():
            if record.id == record_id:
                return record
        raise KeyError(record_id)

    def list(self, *, limit: int | None = None) -> Records:
        """履歴を新しい順に返す（limit指定時は直近limit件）。"""
        records = list(reversed(self._load_all()))
        return records if limit is None else records[:limit]

    def _load_all(self) -> Records:
        if not self._path.exists():
            return []
        records: list[TriageHistoryRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(TriageHistoryRecord.model_validate_json(line))
            except ValueError:
                logger.warning("history.jsonl の不正な行をスキップしました")
        return records
