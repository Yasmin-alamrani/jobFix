"""Application configuration, loaded from environment / .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Gemini (both agents: the analyst, and the scout's scoring) ---
    gemini_api_key: str = ""
    # 3.6 rather than the newer 3.8: on 14 Sep 2026 3.8 answered every request
    # with 503 "high demand" and 3.7 hung, while 3.6 replied in seconds. All
    # three are stable and priced the same. Override with GEMINI_MODEL.
    gemini_model: str = "gemini-3.6-flash"
    gemini_thinking: str = "high"  # low | medium | high

    # --- Storage ---
    database_url: str = "sqlite:///./jobhunt.db"  # point at Postgres for production
    upload_dir: Path = Path("./storage/uploads")

    # --- Scout agent (Agent 2) ---
    # Its model calls use the Gemini settings above; only job sources live here.

    # Google for Jobs, via JSearch. This is how LinkedIn roles reach us:
    # LinkedIn syndicates to Google on purpose, so we read the aggregation
    # rather than the site. Free tier is 200 requests/month.
    jsearch_api_key: str = ""
    jsearch_country: str = "sa"

    # Single-user mode: every row is stamped with this owner so that adding real
    # accounts later is a migration rather than a rewrite.
    default_user_id: str = "local"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    return s
