"""起票済みチケットの軽量JSONストア（重複起票防止）。"""

import json
from pathlib import Path

from pydantic import BaseModel, Field


class _TicketFile(BaseModel):
    version: int = 1
    fingerprints: list[str] = Field(default_factory=list)


class JsonTicketStore:
    """data/tickets.json の永続を担うアダプタ（TicketStorePort実装）。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def contains(self, fingerprint: str) -> bool:
        return fingerprint in self._load().fingerprints

    def record(self, fingerprint: str) -> None:
        file = self._load()
        if fingerprint not in file.fingerprints:
            file.fingerprints.append(fingerprint)
            self._save(file)

    def _load(self) -> _TicketFile:
        if not self._path.exists():
            return _TicketFile()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return _TicketFile.model_validate(data)
        except (OSError, ValueError):
            return _TicketFile()

    def _save(self, file: _TicketFile) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(file.model_dump_json(indent=2), encoding="utf-8")
