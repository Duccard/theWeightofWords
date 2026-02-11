import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: str
    log_level: str = "INFO"
    database_url: Optional[str] = None  # optional: Supabase Postgres


def load_config() -> AppConfig:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "Missing OPENAI_API_KEY. Create a .env file (copy .env.example) and set OPENAI_API_KEY."
        )

    db_url = os.getenv("DATABASE_URL", "").strip() or None

    return AppConfig(
        openai_api_key=key,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        database_url=db_url,
    )
