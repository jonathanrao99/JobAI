"""
backend/config.py
=================
Central configuration using pydantic-settings.
All values come from .env — never hardcode secrets.
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings


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
    openrouter_model: str = "stepfun/step-3.5-flash:free"
    openrouter_fallback_model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    google_model: str = "gemini-2.0-flash"
    openai_model: str = "gpt-4o-mini"

    # ── Apify ────────────────────────────────────────────
    apify_api_token: str = ""
    apify_people_actor_id: str = "apify/google-search-scraper"
    apify_email_actor_id: str = ""
    contact_enrichment_max_contacts: int = 5
    contact_enrichment_min_contacts: int = 3
    contact_enrichment_timeout_seconds: int = 45
    contact_enrichment_email_top_k: int = 3
    contact_enrichment_cache_ttl_seconds: int = 21600
    contact_enrichment_force_refresh: bool = False
    scraper_runtime_profile: str = "balanced"  # fast | balanced | max
    scraper_max_results_per_source: int = 200
    scraper_max_apify_actor_runs: int = 40

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

    # ── 2Captcha ─────────────────────────────────────────
    twocaptcha_api_key: str = ""

    # ── Redis ────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── App ──────────────────────────────────────────────
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    # If set, all /api/* routes require Authorization: Bearer <token> or X-JobAI-Token
    jobai_api_token: str = ""
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

    @model_validator(mode="after")
    def production_requires_api_token(self):
        if (self.environment or "").lower() == "production" and not (self.jobai_api_token or "").strip():
            raise ValueError("JOBAI_API_TOKEN is required when ENVIRONMENT=production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Singleton instance
settings = get_settings()
