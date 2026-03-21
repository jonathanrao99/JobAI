"""
backend/config.py
=================
Central configuration using pydantic-settings.
All values come from .env — never hardcode secrets.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Supabase ─────────────────────────────────────────
    supabase_url: str
    supabase_anon_key: str = ""  # Project Settings → API → anon public
    supabase_service_key: str

    # ── Anthropic ────────────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_daily_spend_cap_usd: float = 5.00

    # ── LLM Provider (swappable) ─────────────────────────
    openrouter_api_key: str = ""
    llm_provider: str = "anthropic"  # anthropic | openrouter | gemini
    llm_model: str = "claude-sonnet-4-20250514"
    gemini_api_key: str = ""
    google_api_key: str = ""     # GOOGLE_API_KEY (used for Gemini)
    openai_api_key: str = ""     # OPENAI_API_KEY

    # Per-provider default models (agents call the same function).
    # Primary/fallback OpenRouter models (single-key rollout).
    # If the primary model errors (e.g., retired/quota/model not found),
    # the LLM client will retry the fallback once.
    openrouter_model: str = "mistralai/mistral-small-3.1-24b-instruct:free"
    openrouter_fallback_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    google_model: str = "gemini-2.0-flash"
    openai_model: str = "gpt-4o-mini"

    # ── Apify ────────────────────────────────────────────
    apify_api_token: str = ""

    # ── Apollo ───────────────────────────────────────────
    apollo_api_key: str = ""

    # ── PhantomBuster ────────────────────────────────────
    phantombuster_api_key: str = ""
    phantombuster_linkedin_agent_id: str = ""

    # ── Gmail ────────────────────────────────────────────
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = "http://localhost:8000/auth/gmail/callback"

    # ── Google Calendar ──────────────────────────────────
    gcal_client_id: str = ""
    gcal_client_secret: str = ""

    # ── Resend ───────────────────────────────────────────
    resend_api_key: str = ""
    outreach_from_email: str = ""
    outreach_from_name: str = ""

    # ── 2Captcha ─────────────────────────────────────────
    twocaptcha_api_key: str = ""

    # ── Redis ────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── App ──────────────────────────────────────────────
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"

    # ── Agent rate limits ────────────────────────────────
    max_applications_per_day: int = 25
    max_linkedin_dms_per_day: int = 15
    max_linkedin_connections_per_day: int = 20
    max_cold_emails_per_day: int = 30
    apply_min_delay_seconds: int = 45
    scrape_interval_hours: int = 6

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Singleton instance
settings = get_settings()
