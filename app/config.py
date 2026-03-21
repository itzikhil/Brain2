from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    database_url: str
    telegram_bot_token: str
    telegram_webhook_secret: str
    gemini_api_key: str
    port: int = 8000

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

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
