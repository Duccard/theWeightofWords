from __future__ import annotations

from typing import Optional

from langchain_openai import ChatOpenAI

from core.config import AppConfig


def create_llm(
    cfg: AppConfig,
    *,
    model: str = "gpt-4o-mini",
    temperature: float = 0.9,
    top_p: float = 0.95,
) -> ChatOpenAI:
    """
    Create the LLM client.

    Safe defaults:
    - prevents Streamlit Cloud crashes if caller forgets to pass model/temp/top_p
    - passes top_p explicitly when supported, otherwise via model_kwargs fallback
    """
    # Some versions of langchain-openai accept top_p explicitly; some warn if in model_kwargs.
    try:
        return ChatOpenAI(
            api_key=cfg.openai_api_key,
            model=model,
            temperature=temperature,
            top_p=top_p,
        )
    except TypeError:
        # Fallback for older signatures
        return ChatOpenAI(
            api_key=cfg.openai_api_key,
            model=model,
            temperature=temperature,
            model_kwargs={"top_p": top_p},
        )
