from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
import yaml

from core.logging_setup import setup_logger

_PROMPT_CACHE: Optional[Dict[str, str]] = None


def load_prompts(path: str = "prompts/prompts.yaml") -> Dict[str, str]:
    """
    Load prompts from YAML and validate required keys.
    Cached to avoid reload churn during Streamlit reruns.
    """
    global _PROMPT_CACHE
    if _PROMPT_CACHE is not None:
        return _PROMPT_CACHE

    logger = setup_logger()

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(
            "prompts.yaml must contain a mapping of prompt_name -> prompt_text"
        )

    required = ["generator", "critic", "reviser"]
    for k in required:
        v = data.get(k)
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"Missing or empty prompt: {k}")

    logger.info(f"Loaded prompts from {path}")
    _PROMPT_CACHE = data
    return data
