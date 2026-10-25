"""PrometheusMetrics アダプタのテスト（MockTransport使用、実API不使用）。"""

import httpx
import pytest

from ops_ai_agent.adapters.prometheus import (
    MetricsQueryError,
    PrometheusMetrics,
    create_prometheus_metrics,
)
from ops_ai_agent.config import Settings


def _metrics(handler) -> PrometheusMetrics:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PrometheusMetrics(client, "http://prometheus:9090")


def test_query_sends_instant_query_and_returns_series():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {
                            "metric": {"service": "api", "code": "500"},
                            "value": [1760000000, "12"],
                        }
                    ],
                },
            },
        )

    result = _metrics(handler).query('sum(rate(http_requests_total{code="500"}[5m]))')
    assert "api" in result
    assert "12" in result
    assert "query=" in str(captured["url"])


def test_query_error_status_raises():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"status": "error", "errorType": "bad_data", "error": "parse"}
        )

    with pytest.raises(MetricsQueryError):
        _metrics(handler).query("bad{{query")


def test_query_http_error_raises():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    with pytest.raises(MetricsQueryError):
        _metrics(handler).query("up")


def test_create_prometheus_metrics_requires_url():
    settings = Settings(_env_file=None)
    assert create_prometheus_metrics(settings) is None


def test_create_prometheus_metrics_with_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        prometheus_url="http://prometheus:9090",
    )
    metrics = create_prometheus_metrics(settings)
    assert metrics is not None
    assert metrics.base_url == "http://prometheus:9090"
