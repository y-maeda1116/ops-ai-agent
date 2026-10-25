"""Webhook ペイロードの正規化（Alertmanager / PagerDuty / Grafana 対応）。

外部アラートシステムの JSON を NormalizedAlert に正規化する。
"""

from typing import Literal, cast

from pydantic import BaseModel


class WebhookPayloadError(ValueError):
    """既知のアラート形式として解釈できないペイロード。"""


class NormalizedAlert(BaseModel):
    """正規化済みアラート。"""

    source: Literal["alertmanager", "pagerduty", "grafana"]
    title: str
    description: str
    severity: str | None
    status: str


def parse_alert_payload(payload: dict[str, object]) -> NormalizedAlert:
    """ペイロードを構造で判別し、正規化する（未知形式は WebhookPayloadError）。"""
    if _looks_like_alertmanager(payload):
        return _parse_alertmanager(payload)
    if _looks_like_pagerduty(payload):
        return _parse_pagerduty(payload)
    if _looks_like_grafana(payload):
        return _parse_grafana(payload)
    msg = "既知のアラート形式（Alertmanager/PagerDuty/Grafana）として解釈できません"
    raise WebhookPayloadError(msg)


def to_alert_text(alert: NormalizedAlert) -> str:
    """triage へ渡すアラート本文を生成する。"""
    lines = [
        f"source: {alert.source}",
        f"title: {alert.title}",
        f"description: {alert.description}",
        f"severity: {alert.severity or 'unknown'}",
        f"status: {alert.status}",
    ]
    return "\n".join(lines)


def _looks_like_alertmanager(payload: dict[str, object]) -> bool:
    alerts = payload.get("alerts")
    return isinstance(alerts, list) and len(alerts) > 0


def _looks_like_pagerduty(payload: dict[str, object]) -> bool:
    return isinstance(payload.get("incident"), dict)


def _looks_like_grafana(payload: dict[str, object]) -> bool:
    return "ruleId" in payload or "ruleName" in payload


def _parse_alertmanager(payload: dict[str, object]) -> NormalizedAlert:
    alerts = cast(list[object], payload["alerts"])
    first = alerts[0]
    if not isinstance(first, dict):
        msg = "alerts[0] がオブジェクトではありません"
        raise WebhookPayloadError(msg)
    labels = _as_dict(first.get("labels"))
    annotations = _as_dict(first.get("annotations"))
    description = str(
        annotations.get("description")
        or annotations.get("summary")
        or labels.get("alertname")
        or ""
    )
    status = str(first.get("status") or payload.get("status") or "unknown")
    return NormalizedAlert(
        source="alertmanager",
        title=str(labels.get("alertname") or "unknown"),
        description=description,
        severity=_opt_severity(labels.get("severity")),
        status=status,
    )


def _parse_pagerduty(payload: dict[str, object]) -> NormalizedAlert:
    incident = _as_dict(payload["incident"])
    # PagerDuty の urgency (high/low) をそのまま重要度として扱う
    return NormalizedAlert(
        source="pagerduty",
        title=str(incident.get("title") or "unknown"),
        description=str(incident.get("summary") or incident.get("title") or ""),
        severity=_opt_severity(incident.get("urgency")),
        status=str(incident.get("status") or "unknown"),
    )


def _parse_grafana(payload: dict[str, object]) -> NormalizedAlert:
    rule_name = payload.get("ruleName")
    title = str(rule_name or payload.get("title") or "unknown")
    return NormalizedAlert(
        source="grafana",
        title=title,
        description=str(payload.get("message") or title),
        severity=None,
        status=str(payload.get("state") or "unknown"),
    )


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _opt_severity(value: object) -> str | None:
    return str(value) if value else None
