"""Settings のテスト。"""

import pytest

from ops_ai_agent.config import Settings


def test_settings_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)
    assert settings.model == "claude-opus-5-5"
    assert settings.effort == "high"
    assert settings.embedding_model == "voyage-3.5-lite"
    assert settings.max_iterations == 12
    assert settings.max_retries == 2
    assert settings.webhook_secret is None
    assert settings.webhook_port == 8080
    assert settings.webhook_rate_limit == 30
    assert settings.prometheus_url is None
    assert settings.knowledge_dir.as_posix() == "knowledge"
    assert settings.data_dir.as_posix() == "data"
    assert settings.anthropic_api_key is None


def test_settings_env_overrides(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPS_AGENT_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("OPS_AGENT_MAX_ITERATIONS", "5")
    monkeypatch.setenv("OPS_AGENT_MAX_RETRIES", "5")
    monkeypatch.setenv("OPS_AGENT_WEBHOOK_SECRET", "whsec-test")
    monkeypatch.setenv("OPS_AGENT_WEBHOOK_PORT", "9090")
    monkeypatch.setenv("OPS_AGENT_WEBHOOK_RATE_LIMIT", "60")
    monkeypatch.setenv("OPS_AGENT_PROMETHEUS_URL", "http://prometheus:9090")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    settings = Settings(_env_file=None)
    assert settings.model == "claude-sonnet-5-5"
    assert settings.max_iterations == 5
    assert settings.max_retries == 5
    assert settings.webhook_secret == "whsec-test"
    assert settings.webhook_port == 9090
    assert settings.webhook_rate_limit == 60
    assert settings.prometheus_url == "http://prometheus:9090"
    assert settings.anthropic_api_key == "sk-test"


def test_require_anthropic_key_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        settings.require_anthropic_key()


def test_require_voyage_key_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    with pytest.raises(ValueError, match="VOYAGE_API_KEY"):
        settings.require_voyage_key()


def test_require_keys_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    settings = Settings(_env_file=None)
    assert settings.require_anthropic_key() == "sk-test"
    assert settings.require_voyage_key() == "pa-test"
