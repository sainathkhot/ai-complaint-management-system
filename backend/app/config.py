"""Application configuration.

Model selection note
--------------------
The assignment specifies `gemma2-9b-it`. Groq announced the deprecation of that
model on 2025-08-08 (in favour of `llama-3.1-8b-instant`) and retired it from
production in October 2025. See docs/MODEL_NOTES.md.

Rather than hard-coding a replacement, the app resolves models at startup:
it queries Groq's /models endpoint, and picks the first entry of each
preference list that is actually live on the account. If `gemma2-9b-it` is ever
restored, it is picked up automatically with no code change.
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Groq ---
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Ordered by preference. First model that is live on the account wins.
    # `gemma2-9b-it` is kept at the head so the app honours the spec whenever
    # the model is available.
    reasoning_model_preference: List[str] = [
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
    ]
    extraction_model_preference: List[str] = [
        "gemma2-9b-it",
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
    ]

    llm_temperature: float = 0.1
    llm_max_retries: int = 2
    llm_timeout_seconds: int = 45

    # --- Database ---
    database_url: str = "postgresql+psycopg://aivoa:aivoa@localhost:5432/aivoa_cms"

    # --- App ---
    app_name: str = "AIVOA Complaint Management System"
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB, matches the reference UI
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
