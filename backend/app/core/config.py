"""Application configuration, loaded from environment / .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Claude ---
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5"
    claude_effort: str = "high"

    # --- Storage ---
    database_url: str = "sqlite:///./jobhunt.db"  # point at Postgres for production
    upload_dir: Path = Path("./storage/uploads")

    # --- Scout agent (Agent 2) ---
    openrouter_api_key: str = ""
    scout_model: str = "deepseek/deepseek-v4-flash"
    scout_vision_model: str = "google/gemini-3.7-flash"

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
