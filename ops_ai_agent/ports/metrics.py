"""メトリクス照会ポート。"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class MetricsPort(Protocol):
    def query(self, expression: str) -> str: ...
