import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: str
    log_level: str = "INFO"


def load_config() -> AppConfig:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "Missing OPENAI_API_KEY. Create a .env file (copy .env.example) and set OPENAI_API_KEY."
        )

    return AppConfig(
        openai_api_key=key,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
