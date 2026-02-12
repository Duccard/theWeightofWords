from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Any
import yaml

from core.logging_setup import setup_logger

# Cache to avoid reload churn during Streamlit reruns.
_PROMPT_CACHE: Optional[Dict[str, Dict[str, str]]] = None


def _validate_prompt_block(name: str, block: Any) -> Dict[str, str]:
    """
    Validate a prompt block shaped like:
      name:
        system: "..."
        user: "..."
    """
    if not isinstance(block, dict):
        raise ValueError(f"Prompt '{name}' must be a mapping with keys: system, user")

    system = block.get("system")
    user = block.get("user")

    if not isinstance(system, str) or not system.strip():
        raise ValueError(f"Missing or empty prompt: {name}.system")
    if not isinstance(user, str) or not user.strip():
        raise ValueError(f"Missing or empty prompt: {name}.user")

    # Return normalized trimmed strings
    return {"system": system.strip(), "user": user.strip()}


def load_prompts(path: str = "prompts/prompts.yaml") -> Dict[str, Dict[str, str]]:
    """
    Load prompts from YAML and validate required keys.
    Expected structure:
      generator: {system: "...", user: "..."}
      critic:    {system: "...", user: "..."}
      reviser:   {system: "...", user: "..."}
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
            "prompts.yaml must contain a mapping of prompt_name -> {system,user}"
        )

    required = ["generator", "critic", "reviser"]
    normalized: Dict[str, Dict[str, str]] = {}

    for name in required:
        normalized[name] = _validate_prompt_block(name, data.get(name))

    logger.info(f"Loaded prompts from {path}")
    _PROMPT_CACHE = normalized
    return normalized
