from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple

from agent.schemas import PoemRequest
from core.logging_setup import setup_logger
from core.prompt_loader import load_prompts
from agent.graph import build_graphs


@dataclass
class RunOutput:
    ok: bool
    error_user: Optional[str] = None
    poem: Optional[str] = None
    critique: Optional[Dict[str, Any]] = None
    revised_poem: Optional[str] = None


def _graphs(llm):
    logger = setup_logger()
    prompts = load_prompts()
    return build_graphs(llm, prompts, logger)


def generate_only(llm, req: PoemRequest) -> RunOutput:
    logger = setup_logger()
    full_graph, _ = _graphs(llm)
    try:
        result = full_graph.invoke({"request": req})
        return RunOutput(ok=True, poem=result.get("poem"))
    except Exception as e:
        logger.error(f"generate_only_failed err={type(e).__name__}:{e}")
        return RunOutput(
            ok=False, error_user="Could not generate the poem. Please try again."
        )


def generate_and_improve(llm, req: PoemRequest) -> RunOutput:
    logger = setup_logger()
    full_graph, _ = _graphs(llm)
    try:
        result = full_graph.invoke({"request": req})
        critique = result.get("critique")
        return RunOutput(
            ok=True,
            poem=result.get("poem"),
            critique=critique.model_dump() if critique else None,
            revised_poem=result.get("revised_poem"),
        )
    except Exception as e:
        logger.error(f"generate_and_improve_failed err={type(e).__name__}:{e}")
        return RunOutput(
            ok=False, error_user="Could not improve the poem. Please try again."
        )


def improve_again(llm, req: PoemRequest, poem: str) -> RunOutput:
    logger = setup_logger()
    _, improve_graph = _graphs(llm)
    try:
        result = improve_graph.invoke({"request": req, "poem": poem})
        critique = result.get("critique")
        return RunOutput(
            ok=True,
            critique=critique.model_dump() if critique else None,
            revised_poem=result.get("revised_poem"),
        )
    except Exception as e:
        logger.error(f"improve_again_failed err={type(e).__name__}:{e}")
        return RunOutput(
            ok=False, error_user="Could not improve again. Please try again."
        )
