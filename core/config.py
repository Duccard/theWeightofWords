from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    openai_api_key: str
    database_url: str | None = None


def load_config() -> AppConfig:
    """
    Loads configuration from environment variables.

    Works with:
    - local .env (python-dotenv)
    - Streamlit Cloud Secrets
    - any cloud provider env vars
    """

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError(
            "Missing OPENAI_API_KEY. "
            "Set it in .env (local) or Streamlit Secrets (cloud)."
        )

    database_url = os.getenv("DATABASE_URL")

    return AppConfig(
        openai_api_key=openai_api_key,
        database_url=database_url,
    )
