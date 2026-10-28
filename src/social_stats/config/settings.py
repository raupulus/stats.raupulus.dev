"""Environment variable settings using pydantic-settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Server & Network
    app_env: str = "production"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    profiles_config_path: Path = Path("config/profiles.json")
    sqlite_db_path: Path = Path("data/stats.db")
    public_dir_path: Path = Path("public")
    cors_allowed_origins: str = "https://stats.raupulus.dev,https://raupulus.dev,http://localhost:8000,http://127.0.0.1:8000"

    # Security & 3-Channel Access Control
    api_bearer_token: str = ""
    ws_public_allowed_origins: str = (
        "https://stats.raupulus.dev,https://raupulus.dev,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )
    ws_public_max_per_ip: int = Field(default=5, ge=1, le=1000)
    ws_public_max_connections: int = Field(default=200, ge=1, le=10000)

    # Poll Intervals (seconds)
    poll_interval_youtube: int = Field(default=300, ge=10)
    poll_interval_bluesky: int = Field(default=120, ge=10)
    poll_interval_mastodon: int = Field(default=180, ge=10)
    poll_interval_twitter: int = Field(default=600, ge=10)
    poll_interval_instagram: int = Field(default=900, ge=10)
    poll_interval_tiktok: int = Field(default=900, ge=10)
    poll_interval_linkedin: int = Field(default=3600, ge=10)
    poll_interval_crypto: int = Field(default=60, ge=10)
    poll_interval_keycounter: int = Field(default=60, ge=10)

    # SQLite snapshot retention
    snapshot_retention_days: int = Field(default=30, ge=1)

    # Platform Credentials
    youtube_api_key: str = ""
    ig_main_user_id: str = ""
    ig_main_access_token: str = ""
    twitter_auth_token_cookie: str = ""
    twitter_ct0_cookie: str = ""
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    linkedin_access_token: str = ""
    linkedin_li_at_cookie: str = ""
    keycounter_api_url: str = "https://api.raupulus.dev/api/v2/keycounter/stats"
    keycounter_api_token: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        raw = self.cors_allowed_origins.strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def ws_public_origins_list(self) -> list[str]:
        """Parse comma-separated allowed Origins for /ws/public."""
        raw = self.ws_public_allowed_origins.strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        return [
            origin.strip().rstrip("/").lower()
            for origin in raw.split(",")
            if origin.strip()
        ]

    def get_poll_interval(self, platform: str) -> int:
        """Return the configured polling interval in seconds for a platform."""
        attr = f"poll_interval_{platform.lower()}"
        val = getattr(self, attr, None)
        if isinstance(val, int):
            return val
        return 300

    def get_instagram_credentials(self, credentials_ref: str = "MAIN") -> tuple[str, str]:
        """Resolve Instagram (user_id, access_token) dynamically by credentials_ref."""
        ref_clean = credentials_ref.strip().upper() or "MAIN"
        if ref_clean == "MAIN":
            user_id = self.ig_main_user_id or os.getenv("IG_MAIN_USER_ID", "")
            token = self.ig_main_access_token or os.getenv("IG_MAIN_ACCESS_TOKEN", "")
            return user_id.strip(), token.strip()
        user_id = os.getenv(f"IG_{ref_clean}_USER_ID", "").strip()
        token = os.getenv(f"IG_{ref_clean}_ACCESS_TOKEN", "").strip()
        return user_id, token

    def get_keycounter_token(self, credentials_ref: str = "MAIN") -> str:
        """Resolve Keycounter Bearer token dynamically by credentials_ref."""
        ref_clean = credentials_ref.strip().upper() or "MAIN"
        if ref_clean == "MAIN":
            token = (
                self.keycounter_api_token
                or os.getenv("KEYCOUNTER_API_TOKEN", "")
                or os.getenv("KEYCOUNTER_MAIN_API_TOKEN", "")
            )
            return token.strip()
        specific = os.getenv(f"KEYCOUNTER_{ref_clean}_API_TOKEN", "").strip()
        if specific:
            return specific
        return self.keycounter_api_token.strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached global Settings instance."""
    return Settings()
