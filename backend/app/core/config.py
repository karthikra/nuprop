from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

_SHARED_ENV = Path.home() / "env" / ".env.dev"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_SHARED_ENV),                # shared dev keys (loaded first, lower priority)
            ".env",                          # project-specific overrides (loaded last, wins)
        ),
        env_file_encoding="utf-8",
        extra="ignore",                      # ignore vars NUPROP doesn't declare
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
    ARQ_MAX_TRIES: int = 3

    # Anthropic via AWS Bedrock — never use direct Anthropic API.
    # Auth comes from the AWS SDK credential chain (profile, env vars, instance role).
    AWS_REGION: str = "ap-northeast-1"        # Tokyo — lowest latency from Bangalore
    AWS_PROFILE: str | None = None             # optional; falls back to env/role if unset

    # Bedrock global inference profile IDs — tiered model selection.
    # Verified via `aws bedrock list-inference-profiles --region ap-northeast-1`.
    # The skill's published IDs had wrong suffixes for Sonnet 4.6 and Haiku 4.5.
    ANTHROPIC_DEFAULT_MODEL: str = "global.anthropic.claude-sonnet-4-6"           # balanced
    ANTHROPIC_OPUS_MODEL: str = "global.anthropic.claude-opus-4-7"                # heavy
    ANTHROPIC_HAIKU_MODEL: str = "global.anthropic.claude-haiku-4-5-20251001-v1:0"  # fast

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
