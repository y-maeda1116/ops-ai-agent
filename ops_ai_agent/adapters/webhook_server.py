"""Webhook 受付HTTPサーバ（stdlib http.server、署名検証・レート制限付き）。"""

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ops_ai_agent.domain.models import TriageReport
from ops_ai_agent.domain.webhook import (
    NormalizedAlert,
    WebhookPayloadError,
    parse_alert_payload,
)

_MAX_BODY_BYTES = 1_000_000


def verify_signature(body: bytes, header: str | None, secret: str) -> bool:
    """X-Signature（sha256=<hex>）を constant-time 比較で検証する。"""
    if header is None:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.strip())


class SlidingWindowRateLimiter:
    """クライアントキー単位のスライディングウィンドウ（60秒）レート制限。"""

    def __init__(
        self, max_per_minute: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._max = max_per_minute
        self._clock = clock
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        window_start = now - 60.0
        hits = [t for t in self._hits.get(key, []) if t > window_start]
        if len(hits) >= self._max:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True


def create_handler(
    on_alert: Callable[[NormalizedAlert], TriageReport],
    *,
    secret: str | None,
    rate_limiter: SlidingWindowRateLimiter,
) -> type[BaseHTTPRequestHandler]:
    """設定済みのリクエストハンドラクラスを生成する。"""

    class WebhookHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (http.server の命名規約)
            if not rate_limiter.allow(self.client_address[0]):
                self._send_json(429, {"error": "rate limit exceeded"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > _MAX_BODY_BYTES:
                self._send_json(400, {"error": "invalid body"})
                return
            body = self.rfile.read(length)
            if secret is not None and not verify_signature(
                body, self.headers.get("X-Signature"), secret
            ):
                self._send_json(401, {"error": "invalid signature"})
                return
            try:
                payload = json.loads(body.decode())
                if not isinstance(payload, dict):
                    raise ValueError("top-level must be an object")
                alert = parse_alert_payload(payload)
            except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
                self._send_json(400, {"error": "unrecognized payload"})
                return
            except WebhookPayloadError:
                self._send_json(400, {"error": "unrecognized payload"})
                return
            try:
                report = on_alert(alert)
            except Exception:
                # 内部エラーの詳細は漏らさず、サーバログにのみ記録する
                self.log_error("triage failed")
                self._send_json(502, {"error": "triage failed"})
                return
            self._send_json(200, report.model_dump(mode="json"))

        def do_GET(self) -> None:  # noqa: N802
            self.send_error(405)

        def _send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            pass  # アクセスログは任意のロガーへ差し替え可能にするため無効化

    return WebhookHandler


def run_webhook_server(
    on_alert: Callable[[NormalizedAlert], TriageReport],
    *,
    secret: str | None,
    max_per_minute: int,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> ThreadingHTTPServer:
    """サーバを構築して serve_forever を開始する（ブロッキング）。"""
    handler_cls = create_handler(
        on_alert, secret=secret, rate_limiter=SlidingWindowRateLimiter(max_per_minute)
    )
    server = ThreadingHTTPServer((host, port), handler_cls)
    server.serve_forever()
    return server  # pragma: no cover（serve_forever が戻らないため）
