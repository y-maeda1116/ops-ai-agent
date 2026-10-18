"""Webhook 受付サーバのテスト（エフェメラルポートで実ソケット使用）。"""

import hashlib
import hmac
import json
import threading
from collections.abc import Callable

import httpx

from ops_ai_agent.adapters.webhook_server import (
    SlidingWindowRateLimiter,
    create_handler,
    verify_signature,
)
from ops_ai_agent.domain.models import TriageReport
from ops_ai_agent.domain.webhook import NormalizedAlert

_SECRET = "whsec-test"
_ALERTMANAGER = {
    "alerts": [
        {
            "labels": {"alertname": "HighErrorRate", "severity": "critical"},
            "annotations": {"description": "5xx急増"},
        }
    ]
}


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _report() -> TriageReport:
    return TriageReport(
        severity="high",
        summary="要約",
        possible_causes=[],
        recommended_actions=[],
        referenced_incidents=[],
        confidence="medium",
        requires_human_escalation=False,
    )


def _start_server(
    on_alert: Callable[[NormalizedAlert], TriageReport],
    *,
    secret: str | None = _SECRET,
    max_per_minute: int = 100,
):
    handler_cls = create_handler(
        on_alert, secret=secret, rate_limiter=SlidingWindowRateLimiter(max_per_minute)
    )
    from http.server import ThreadingHTTPServer

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/webhook"

    def shutdown():
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return url, shutdown


class TestVerifySignature:
    def test_valid_signature_passes(self):
        body = b'{"a": 1}'
        assert verify_signature(body, _sign(body), _SECRET) is True

    def test_tampered_body_fails(self):
        assert verify_signature(b'{"a": 2}', _sign(b'{"a": 1}'), _SECRET) is False

    def test_missing_header_fails(self):
        assert verify_signature(b"{}", None, _SECRET) is False

    def test_wrong_secret_fails(self):
        body = b"{}"
        assert verify_signature(body, _sign(body, "other"), _SECRET) is False


class TestSlidingWindowRateLimiter:
    def test_allows_under_limit(self):
        limiter = SlidingWindowRateLimiter(3, clock=lambda: 100.0)
        assert [limiter.allow("ip1") for _ in range(3)] == [True, True, True]

    def test_blocks_over_limit(self):
        limiter = SlidingWindowRateLimiter(2, clock=lambda: 100.0)
        limiter.allow("ip1")
        limiter.allow("ip1")
        assert limiter.allow("ip1") is False

    def test_window_slides_by_time(self):
        now = 100.0
        limiter = SlidingWindowRateLimiter(1, clock=lambda: now)
        assert limiter.allow("ip1") is True
        assert limiter.allow("ip1") is False
        now = 160.0  # 60秒経過で窓から外れる
        assert limiter.allow("ip1") is True

    def test_keys_are_isolated(self):
        limiter = SlidingWindowRateLimiter(1, clock=lambda: 100.0)
        assert limiter.allow("ip1") is True
        assert limiter.allow("ip2") is True


class TestWebhookEndpoint:
    def test_valid_request_returns_report(self):
        received: list[NormalizedAlert] = []

        def on_alert(alert: NormalizedAlert) -> TriageReport:
            received.append(alert)
            return _report()

        url, shutdown = _start_server(on_alert)
        try:
            body = json.dumps(_ALERTMANAGER).encode()
            response = httpx.post(
                url, content=body, headers={"X-Signature": _sign(body)}
            )
        finally:
            shutdown()
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"] == "要約"
        assert received[0].title == "HighErrorRate"

    def test_invalid_json_returns_400(self):
        url, shutdown = _start_server(lambda _a: _report())
        try:
            body = b"not json"
            response = httpx.post(
                url, content=body, headers={"X-Signature": _sign(body)}
            )
        finally:
            shutdown()
        assert response.status_code == 400

    def test_unknown_payload_returns_400(self):
        url, shutdown = _start_server(lambda _a: _report())
        try:
            body = b'{"foo": "bar"}'
            response = httpx.post(
                url, content=body, headers={"X-Signature": _sign(body)}
            )
        finally:
            shutdown()
        assert response.status_code == 400

    def test_bad_signature_returns_401(self):
        url, shutdown = _start_server(lambda _a: _report())
        try:
            body = json.dumps(_ALERTMANAGER).encode()
            response = httpx.post(
                url, content=body, headers={"X-Signature": _sign(body, "wrong")}
            )
        finally:
            shutdown()
        assert response.status_code == 401

    def test_missing_signature_returns_401_when_secret_set(self):
        url, shutdown = _start_server(lambda _a: _report())
        try:
            response = httpx.post(url, json=_ALERTMANAGER)
        finally:
            shutdown()
        assert response.status_code == 401

    def test_no_secret_accepts_unsigned(self):
        url, shutdown = _start_server(lambda _a: _report(), secret=None)
        try:
            response = httpx.post(url, json=_ALERTMANAGER)
        finally:
            shutdown()
        assert response.status_code == 200

    def test_rate_limit_returns_429(self):
        url, shutdown = _start_server(
            lambda _a: _report(), secret=None, max_per_minute=1
        )
        try:
            assert httpx.post(url, json=_ALERTMANAGER).status_code == 200
            assert httpx.post(url, json=_ALERTMANAGER).status_code == 429
        finally:
            shutdown()

    def test_triage_failure_returns_502_without_details(self):
        def on_alert(_alert: NormalizedAlert) -> TriageReport:
            msg = "APIキー sk-xxx が無効"
            raise RuntimeError(msg)

        url, shutdown = _start_server(on_alert, secret=None)
        try:
            response = httpx.post(url, json=_ALERTMANAGER)
        finally:
            shutdown()
        assert response.status_code == 502
        assert "sk-xxx" not in response.text

    def test_get_returns_405(self):
        url, shutdown = _start_server(lambda _a: _report(), secret=None)
        try:
            response = httpx.get(url)
        finally:
            shutdown()
        assert response.status_code == 405
