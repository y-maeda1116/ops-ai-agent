"""Webhook ペイロード正規化のテスト。"""

import pytest

from ops_ai_agent.domain.webhook import (
    WebhookPayloadError,
    parse_alert_payload,
    to_alert_text,
)

_ALERTMANAGER = {
    "version": "4",
    "status": "firing",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighErrorRate",
                "service": "api",
                "severity": "critical",
            },
            "annotations": {
                "description": "5xxレートが5%を超えました",
                "summary": "high error rate",
            },
            "startsAt": "2026-10-19T00:00:00Z",
        }
    ],
}

_PAGERDUTY = {
    "event_type": "incident.triggered",
    "resource_type": "incident",
    "incident": {
        "id": "PT123",
        "title": "DB CPU高負荷",
        "status": "triggered",
        "urgency": "high",
        "summary": "DBサーバのCPUが95%を超過",
    },
}

_GRAFANA = {
    "ruleId": 1,
    "ruleName": "High latency",
    "state": "alerting",
    "title": "[Alerting] High latency",
    "message": "p99が1秒を超えました",
}


def test_parse_alertmanager_payload():
    alert = parse_alert_payload(_ALERTMANAGER)
    assert alert.source == "alertmanager"
    assert alert.title == "HighErrorRate"
    assert alert.description == "5xxレートが5%を超えました"
    assert alert.severity == "critical"
    assert alert.status == "firing"


def test_parse_alertmanager_uses_summary_when_no_description():
    payload = {
        "alerts": [
            {
                "labels": {"alertname": "Latency"},
                "annotations": {"summary": "応答遅延"},
            }
        ]
    }
    alert = parse_alert_payload(payload)
    assert alert.description == "応答遅延"


def test_parse_pagerduty_payload():
    alert = parse_alert_payload(_PAGERDUTY)
    assert alert.source == "pagerduty"
    assert alert.title == "DB CPU高負荷"
    assert alert.description == "DBサーバのCPUが95%を超過"
    assert alert.severity == "high"
    assert alert.status == "triggered"


def test_parse_grafana_payload():
    alert = parse_alert_payload(_GRAFANA)
    assert alert.source == "grafana"
    assert alert.title == "High latency"
    assert alert.description == "p99が1秒を超えました"
    assert alert.status == "alerting"


def test_unknown_payload_raises():
    with pytest.raises(WebhookPayloadError):
        parse_alert_payload({"foo": "bar"})


def test_alertmanager_without_alerts_raises():
    with pytest.raises(WebhookPayloadError):
        parse_alert_payload({"version": "4", "alerts": []})


def test_to_alert_text_contains_fields():
    text = to_alert_text(parse_alert_payload(_ALERTMANAGER))
    assert "alertmanager" in text
    assert "HighErrorRate" in text
    assert "5xxレートが5%を超えました" in text
    assert "critical" in text
