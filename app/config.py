"""ARGO application configuration — loaded from .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All ARGO configuration. Loaded from environment / .env file.

    Use the get_settings() function to get the singleton instance.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    environment: str = "development"
    app_base_url: str = "http://localhost:8000"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    secret_key: str = "change-me-in-production"
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite+aiosqlite:///./argo_dev.db"

    # Anthropic Claude
    anthropic_api_key: str 
    claude_haiku_model: str = "claude-haiku-4-5"
    claude_sonnet_model: str = "claude-sonnet-4-5"

    # OpenAI (optional — Whisper + embeddings)
    openai_api_key: Optional[str] = None

    # Microsoft Azure / Graph
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""
    graph_scopes: str = (
        "Mail.Read Mail.Send Mail.ReadWrite Calendars.Read User.Read offline_access"
    )

    # Team
    ceo_email: str = "yalireza@arpglobalcapital.com"
    team_emails: str = ""

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    pm_whatsapp_number: str = ""

    # Serper
    serper_api_key: str = ""

    # Overnight
    overnight_summary_timezone: str = "Europe/London"
    overnight_window_start_hour: int = 22
    overnight_window_end_hour: int = 3

    # AWS
    aws_region: str = "eu-west-1"
    ecr_registry: str = ""
    ecr_repository: str = "argo"

    # Feature flags
    enable_whatsapp: bool = True
    enable_email_fetch: bool = True
    enable_overnight_cron: bool = True

    # ── Validators ──────────────────────────────────────────────────────────

    @field_validator("ceo_email")
    @classmethod
    def ceo_email_must_contain_at(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("ceo_email must be a valid email address containing '@'")
        return v

    # ── Computed properties ──────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        """True if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """True if running in development environment."""
        return self.environment == "development"

    @property
    def graph_scopes_list(self) -> list[str]:
        """Return graph scopes as a list."""
        return self.graph_scopes.split()

    @property
    def team_emails_list(self) -> list[str]:
        """Return team emails as a list."""
        return [e.strip() for e in self.team_emails.split(",") if e.strip()]

    # Legacy alias so existing code using app_env still works
    @property
    def app_env(self) -> str:
        return self.environment

    # Convenience: redirect URI derived from app_base_url
    @property
    def azure_redirect_uri(self) -> str:
        return f"{self.app_base_url}/auth/callback"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton (lru_cache — created once per process)."""
    return Settings()
