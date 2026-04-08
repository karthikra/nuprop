from __future__ import annotations

from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "NUPROP"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Database — SQLite for dev, PostgreSQL (Supabase) for prod
    DATABASE_URL: str = "sqlite+aiosqlite:///nuprop.db"

    @computed_field
    @property
    def DATABASE_POOL_SIZE(self) -> int:
        return 0 if self.DATABASE_URL.startswith("sqlite") else 3

    @computed_field
    @property
    def DATABASE_MAX_OVERFLOW(self) -> int:
        return 0 if self.DATABASE_URL.startswith("sqlite") else 5

    # Redis (Upstash in prod)
    REDIS_ENABLED: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_DEFAULT_MODEL: str = "claude-sonnet-4-20250514"
    ANTHROPIC_OPUS_MODEL: str = "claude-opus-4-20250514"
    ANTHROPIC_HAIKU_MODEL: str = "claude-haiku-4-5-20251001"

    # Voyage (embeddings)
    VOYAGE_API_KEY: str = ""
    VOYAGE_MODEL: str = "voyage-3-large"

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_ACCESS_KEY_SECRET: str = ""
    R2_BUCKET_NAME: str = "nuprop-files"
    R2_ENDPOINT: str = ""

    # Resend (email)
    RESEND_API_KEY: str = ""

    # Web search
    SERPER_API_KEY: str = ""

    # Google OAuth (Gmail connector)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:5173/settings/gmail-callback"

    # Slack OAuth
    SLACK_CLIENT_ID: str = ""
    SLACK_CLIENT_SECRET: str = ""
    SLACK_REDIRECT_URI: str = "http://localhost:5173/settings/slack-callback"

    # Encryption for OAuth tokens
    ENCRYPTION_KEY: str = ""

    # Auth
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24h

    # Proposal site hosting
    PROPOSAL_SITE_DOMAIN: str = "proposals.nuprop.app"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @computed_field
    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @computed_field
    @property
    def OUTPUT_DIR(self) -> str:
        if self.is_production:
            return "/data/outputs"
        return "outputs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
