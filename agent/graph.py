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
        system_prompt = tpl["system"]
        # allow {schema} in critic.user if you want later
        user_prompt = tpl["user"].format(poem=state["poem"], schema=schema_str)

        msg = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=(
                    f"{user_prompt}\n\n"
                    f"Constraints: {req.model_dump()}\n\n"
                    f"Poem:\n{state['poem']}\n\n"
                    f"Return only valid JSON."
                )
            ),
        ]

        res = safe_invoke(
            logger,
            user_error="Could not critique the poem right now.",
            fn=lambda: llm.invoke(msg),
        )
        if not res.ok:
            raise RuntimeError(res.error_debug or "critic_failed")

        critique = TypeAdapter(Critique).validate_json(res.content)
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
