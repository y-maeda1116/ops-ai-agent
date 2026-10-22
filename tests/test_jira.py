"""JiraTickets アダプタのテスト（MockTransport使用、実API不使用）。"""

import httpx
import pytest

from ops_ai_agent.adapters.jira import JiraTickets, TicketCreationError


def _jira(handler) -> JiraTickets:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return JiraTickets(
        client, "https://jira.example.com", "ops@example.com", "token", "OPS"
    )


def test_create_ticket_posts_issue_and_returns_url():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = request.read()
        return httpx.Response(201, json={"key": "OPS-42"})

    url = _jira(handler).create_ticket(
        "[triage][critical] DB枯渇", "説明本文", severity="critical"
    )
    assert url == "https://jira.example.com/browse/OPS-42"
    assert str(captured["url"]).endswith("/rest/api/3/issue")
    # Basic認証（email + APIトークン）
    auth = captured["auth"]
    assert auth is not None and auth.startswith("Basic ")
    body = captured["body"]
    assert b'"key":"OPS"' in body or b'"key": "OPS"' in body
    assert "DB枯渇" in body.decode()


def test_create_ticket_http_error_raises():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    with pytest.raises(TicketCreationError):
        _jira(handler).create_ticket("t", "d", severity="high")
