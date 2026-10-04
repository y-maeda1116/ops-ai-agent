"""アプリケーション設定（環境変数と.envから読み込み）。"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ops-ai-agent の設定。環境変数 > .env の順で解決される。"""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    anthropic_api_key: str | None = None
    voyage_api_key: str | None = None
    slack_bot_token: str | None = None
    slack_app_token: str | None = None

    model: str = Field(default="claude-opus-5-5", validation_alias="OPS_AGENT_MODEL")
    effort: str = Field(default="high", validation_alias="OPS_AGENT_EFFORT")
    embedding_model: str = Field(
        default="voyage-3.5-lite", validation_alias="OPS_AGENT_EMBEDDING_MODEL"
    )
    knowledge_dir: Path = Path("knowledge")
    data_dir: Path = Path("data")
    max_iterations: int = Field(default=12, validation_alias="OPS_AGENT_MAX_ITERATIONS")
    slack_channel: str = Field(
        default="#ops-alerts", validation_alias="OPS_AGENT_SLACK_CHANNEL"
    )

    def require_anthropic_key(self) -> str:
        """ANTHROPIC_API_KEY を検証付きで返す。"""
        if self.anthropic_api_key is None:
            msg = (
                "ANTHROPIC_API_KEY が設定されていません。"
                ".env.example を参考に環境変数を設定してください。"
            )
            raise ValueError(msg)
        return self.anthropic_api_key

    def require_voyage_key(self) -> str:
        """VOYAGE_API_KEY を検証付きで返す。"""
        if self.voyage_api_key is None:
            msg = (
                "VOYAGE_API_KEY が設定されていません。"
                ".env.example を参考に環境変数を設定してください。"
            )
            raise ValueError(msg)
        return self.voyage_api_key

    def require_slack_app_token(self) -> str:
        """SLACK_APP_TOKEN を検証付きで返す。"""
        if self.slack_app_token is None:
            msg = (
                "SLACK_APP_TOKEN が設定されていません（xapp- で始まる"
                "アプリトークン、connections:write 権限が必要です）。"
            )
            raise ValueError(msg)
        return self.slack_app_token
