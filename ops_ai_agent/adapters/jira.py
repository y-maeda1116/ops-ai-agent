"""Jira REST API v3 チケット起票アダプタ（TicketPort実装）。"""

import base64

import httpx

from ops_ai_agent.config import Settings


class TicketCreationError(Exception):
    """Jira チケット起票の失敗（HTTPエラー・認証エラー）。"""


class JiraTickets:
    """Jira の課題起票（POST /rest/api/3/issue、Basic認証）。"""

    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        email: str,
        api_token: str,
        project_key: str,
    ) -> None:
        self._client = client
        self.base_url = base_url.rstrip("/")
        self._basic = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._project_key = project_key

    def create_ticket(self, title: str, description: str, *, severity: str) -> str:
        """課題を起票し、ブラウズURLを返す。"""
        payload = {
            "fields": {
                "project": {"key": self._project_key},
                "summary": title,
                "issuetype": {"name": "Task"},
                "labels": ["ops-ai-agent", f"severity-{severity}"],
                "description": _adf_paragraph(description),
            }
        }
        url = f"{self.base_url}/rest/api/3/issue"
        try:
            response = self._client.post(
                url,
                json=payload,
                headers={"Authorization": f"Basic {self._basic}"},
            )
            response.raise_for_status()
            key = response.json()["key"]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            msg = f"Jira チケット起票に失敗しました: {type(exc).__name__}"
            raise TicketCreationError(msg) from exc
        return f"{self.base_url}/browse/{key}"


def _adf_paragraph(text: str) -> dict[str, object]:
    """Jira API v3 の Atlassian Document Format 段落に変換する。"""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def create_jira_tickets(settings: Settings) -> JiraTickets | None:
    """設定から JiraTickets を構築する（設定不備時は None）。"""
    if (
        settings.jira_base_url is None
        or settings.jira_email is None
        or settings.jira_api_token is None
        or settings.jira_project_key is None
    ):
        return None
    return JiraTickets(
        httpx.Client(timeout=10.0),
        settings.jira_base_url,
        settings.jira_email,
        settings.jira_api_token,
        settings.jira_project_key,
    )
