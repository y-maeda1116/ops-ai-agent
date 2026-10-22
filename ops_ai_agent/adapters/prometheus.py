"""Prometheus 即時クエリアダプタ（MetricsPort実装・httpx使用）。"""

import json
from urllib.parse import quote

import httpx

from ops_ai_agent.config import Settings


class MetricsQueryError(Exception):
    """Prometheus クエリの失敗（HTTPエラー・エラーレスポンス）。"""


class PrometheusMetrics:
    """MetricsPort の Prometheus 実装（/api/v1/query 即時クエリ）。"""

    def __init__(self, client: httpx.Client, base_url: str) -> None:
        self._client = client
        self.base_url = base_url.rstrip("/")

    def query(self, expression: str) -> str:
        """PromQL 即時クエリを実行し、時系列の要約文字列を返す。"""
        url = f"{self.base_url}/api/v1/query?query={quote(expression)}"
        response = self._client.get(url)
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            msg = f"Prometheus クエリに失敗しました: {type(exc).__name__}"
            raise MetricsQueryError(msg) from exc
        if payload.get("status") != "success":
            detail = str(payload.get("error", "unknown error"))
            msg = f"Prometheus クエリエラー: {detail}"
            raise MetricsQueryError(msg)
        result = payload["data"]["result"]
        return self._format(result)

    def _format(self, series: list[dict[str, object]]) -> str:
        if not series:
            return "ヒットなし: 条件に一致する時系列がありません。"
        lines = []
        for item in series:
            metric = item.get("metric", {})
            value = item.get("value", [])
            sample = value[1] if isinstance(value, list) and len(value) > 1 else "?"
            labels = json.dumps(metric, ensure_ascii=False, sort_keys=True)
            lines.append(f"{labels} = {sample}")
        return "\n".join(lines)


def create_prometheus_metrics(settings: Settings) -> PrometheusMetrics | None:
    """設定から PrometheusMetrics を構築する（URL未設定時は None）。"""
    if settings.prometheus_url is None:
        return None
    return PrometheusMetrics(httpx.Client(timeout=10.0), settings.prometheus_url)
