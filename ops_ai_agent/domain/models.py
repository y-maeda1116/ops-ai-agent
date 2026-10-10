"""ドメインモデル（pydantic）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class LogRecord(BaseModel):
    """取り込み時に正規化されたログ1行。"""

    timestamp: datetime
    level: str  # 小文字正規化済み（例: "error"）
    service: str
    message: str
    raw: str


class Cause(BaseModel):
    """原因候補。"""

    description: str
    evidence: str  # 根拠となったログ/統計/ナレッジ参照の説明


class Action(BaseModel):
    """推奨初期対応手順の1ステップ。"""

    order: int
    description: str
    owner_hint: str  # 担当観点（例: "app チーム" / "DBA"）


class TriageReport(BaseModel):
    """エージェントの最終出力（structured outputsで検証）。"""

    severity: Literal["critical", "high", "medium", "low"]
    summary: str
    possible_causes: list[Cause]
    recommended_actions: list[Action]
    referenced_incidents: list[str]
    confidence: Literal["high", "medium", "low"]
    requires_human_escalation: bool


class KnowledgeChunk(BaseModel):
    """ベクタストア永続単位（原文＋埋め込み＋メタデータ）。"""

    id: str
    source: str
    title: str
    text: str
    metadata: dict[str, str]
    embedding: list[float]


class SearchHit(BaseModel):
    """検索結果1件。"""

    chunk: KnowledgeChunk
    score: float
