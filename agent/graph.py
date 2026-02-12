from __future__ import annotations

from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import TypeAdapter

from agent.schemas import PoemRequest, Critique
from core.safe_call import safe_invoke


class AgentState(TypedDict, total=False):
    request: PoemRequest
    poem: str
    critique: Critique
    revised_poem: str
    user_memory: str


def _ctx(state: AgentState) -> Dict[str, Any]:
    """Build formatting context for YAML templates."""
    req = state["request"]
    data = req.model_dump()
    data["user_memory"] = state.get("user_memory") or "None"
    return data


def build_graphs(llm, prompts: Dict[str, Dict[str, str]], logger):
    def generate_poem(state: AgentState):
        ctx = _ctx(state)
        tpl = prompts["generator"]

        system_prompt = tpl["system"].format(**ctx)
        user_prompt = tpl["user"].format(**ctx)

        msg = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        res = safe_invoke(
            logger,
            user_error="Could not generate a poem right now.",
            fn=lambda: llm.invoke(msg),
        )
        if not res.ok:
            raise RuntimeError(res.error_debug or "generate_failed")

        return {"poem": res.content.strip()}

    def criticize_poem(state: AgentState):
        req = state["request"]
        schema_str = Critique.model_json_schema()

        tpl = prompts["critic"]
        system_prompt = tpl["system"].format(schema=schema_str)
        user_prompt = tpl["user"].format(
            constraints=req.model_dump(),
            poem=state["poem"],
        )

        msg = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        res = safe_invoke(
            logger,
            user_error="Could not critique the poem right now.",
            fn=lambda: llm.invoke(msg),
        )
        if not res.ok:
            raise RuntimeError(res.error_debug or "critic_failed")

        raw = (res.content or "").strip()

        # strict parse first
        try:
            critique = TypeAdapter(Critique).validate_json(raw)
            return {"critique": critique}
        except Exception:
            # fallback: extract JSON object if model added extra text
            import re

            m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if not m:
                raise RuntimeError(f"critic_parse_failed: {raw[:200]}")
            critique = TypeAdapter(Critique).validate_json(m.group(0))
            return {"critique": critique}

    def revise_poem(state: AgentState):
        ctx = _ctx(state)
        tpl = prompts["reviser"]

        system_prompt = tpl["system"].format(**ctx)
        user_prompt = tpl["user"].format(
            **ctx,
            poem=state["poem"],
            critique=state["critique"].model_dump(),
        )

        msg = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        res = safe_invoke(
            logger,
            user_error="Could not revise the poem right now.",
            fn=lambda: llm.invoke(msg),
        )
        if not res.ok:
            raise RuntimeError(res.error_debug or "revise_failed")

        return {"revised_poem": res.content.strip()}

    # Full graph: generate -> critique -> revise
    full = StateGraph(AgentState)
    full.add_node("generate_poem", generate_poem)
    full.add_node("criticize_poem", criticize_poem)
    full.add_node("revise_poem", revise_poem)
    full.set_entry_point("generate_poem")
    full.add_edge("generate_poem", "criticize_poem")
    full.add_edge("criticize_poem", "revise_poem")
    full.add_edge("revise_poem", END)
    full_graph = full.compile()

    # Improve-only graph: critique -> revise
    improve = StateGraph(AgentState)
    improve.add_node("criticize_poem", criticize_poem)
    improve.add_node("revise_poem", revise_poem)
    improve.set_entry_point("criticize_poem")
    improve.add_edge("criticize_poem", "revise_poem")
    improve.add_edge("revise_poem", END)
    improve_graph = improve.compile()

    return full_graph, improve_graph
