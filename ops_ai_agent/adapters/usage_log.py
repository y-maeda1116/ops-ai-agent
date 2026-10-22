"""LLM usage（トークン/概算コスト）のJSONL記録と集計。"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from ops_ai_agent.ports.llm import Usage

logger = logging.getLogger(__name__)

# 1Mトークンあたりの概算単価（USD）: (入力, 出力)
_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus": (5.0, 25.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
}


def _price_for(model: str) -> tuple[float, float] | None:
    """モデル名から単価を引く（前方一致、未知モデルは None）。"""
    for prefix, price in _PRICES_PER_MTOK.items():
        if model.startswith(prefix):
            return price
    return None


def estimate_cost_usd(model: str, usage: Usage) -> float | None:
    """usage から概算コスト（USD）を計算する（未知モデルは None）。"""
    price = _price_for(model)
    if price is None:
        return None
    input_cost = usage.input_tokens / 1_000_000 * price[0]
    output_cost = usage.output_tokens / 1_000_000 * price[1]
    return round(input_cost + output_cost, 6)


class UsageRecord(BaseModel):
    """usage.jsonl の1レコード。"""

    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    created_at: str


class UsageSummary(BaseModel):
    """usage.jsonl の集計。"""

    runs: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = Field(default=0.0)


class JsonlUsageLogger:
    """data/usage.jsonl への追記記録（単価不明モデルは cost None）。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def record(self, model: str, usage: Usage) -> UsageRecord | None:
        """1件記録する。書き込み失敗時は警告ログして None（triage を止めない）。"""
        entry = UsageRecord(
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=estimate_cost_usd(model, usage),
            created_at=datetime.now(tz=UTC).isoformat(),
        )
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as file:
                file.write(entry.model_dump_json() + "\n")
        except OSError:
            logger.warning("usage.jsonl への記録に失敗しました: %s", self._path)
            return None
        return entry

    def load(self) -> list[UsageRecord]:
        if not self._path.exists():
            return []
        records: list[UsageRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(UsageRecord.model_validate_json(line))
            except ValueError:
                logger.warning("usage.jsonl の不正な行をスキップしました")
        return records

    def summarize(self) -> UsageSummary:
        """記録済みusageを集計する（cost不明レコードは集計対象外）。"""
        records = self.load()
        costs = [r.cost_usd for r in records if r.cost_usd is not None]
        return UsageSummary(
            runs=len(records),
            input_tokens=sum(r.input_tokens for r in records),
            output_tokens=sum(r.output_tokens for r in records),
            total_cost_usd=round(sum(costs), 6),
        )
