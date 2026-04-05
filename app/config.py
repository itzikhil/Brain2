from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    database_url: str
    telegram_bot_token: str
    telegram_webhook_secret: str
    gemini_api_key: str
    port: int = 8000

    # Bot mode: "polling" for local development, "webhook" for Railway
    bot_mode: str = "polling"

    # Logging
    log_channel_id: Optional[str] = None

    # Vector search settings
    embedding_dimension: int = 3072
    default_search_limit: int = 5

    # Cloudflare R2 storage (optional)
    r2_account_id: Optional[str] = None
    r2_access_key_id: Optional[str] = None
    r2_secret_access_key: Optional[str] = None
    r2_bucket_name: str = "brain2-docs"

    # OpenRouter (optional - primary cloud model)
    openrouter_api_key: str = ""

    # Morning briefing
    telegram_owner_id: Optional[str] = None
    openweather_api_key: Optional[str] = None
    newsapi_key: Optional[str] = None

    # Obsidian vault integration (optional)
    obsidian_vault_path: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
