from __future__ import annotations
from typing import TypedDict, Dict
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


def build_graphs(llm, prompts: Dict[str, str], logger):
    def generate_poem(state: AgentState):
        req = state["request"]
        prompt = prompts["generator"].format(**req.model_dump())
        res = safe_invoke(
            logger,
            user_error="Could not generate a poem right now.",
            fn=lambda: llm.invoke([SystemMessage(content=prompt)]),
        )
        if not res.ok:
            raise RuntimeError(res.error_debug or "generate_failed")
        return {"poem": res.content.strip()}

    def criticize_poem(state: AgentState):
        req = state["request"]
        schema_str = Critique.model_json_schema()
        critic_prompt = prompts["critic"].format(schema=schema_str)
        msg = [
            SystemMessage(content=critic_prompt),
            HumanMessage(
                content=f"Constraints: {req.model_dump()}\n\nPoem:\n{state['poem']}"
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
        req = state["request"]
        msg = [
            SystemMessage(content=prompts["reviser"]),
            HumanMessage(
                content=f"Constraints: {req.model_dump()}\n\nPoem:\n{state['poem']}\n\nCritique:\n{state['critique'].model_dump()}"
            ),
        ]
        res = safe_invoke(
            logger,
            user_error="Could not revise the poem right now.",
            fn=lambda: llm.invoke(msg),
        )
        if not res.ok:
            raise RuntimeError(res.error_debug or "revise_failed")
        return {"revised_poem": res.content.strip()}

    full = StateGraph(AgentState)
    full.add_node("generate_poem", generate_poem)
    full.add_node("criticize_poem", criticize_poem)
    full.add_node("revise_poem", revise_poem)
    full.set_entry_point("generate_poem")
    full.add_edge("generate_poem", "criticize_poem")
    full.add_edge("criticize_poem", "revise_poem")
    full.add_edge("revise_poem", END)
    full_graph = full.compile()

    improve = StateGraph(AgentState)
    improve.add_node("criticize_poem", criticize_poem)
    improve.add_node("revise_poem", revise_poem)
    improve.set_entry_point("criticize_poem")
    improve.add_edge("criticize_poem", "revise_poem")
    improve.add_edge("revise_poem", END)
    improve_graph = improve.compile()

    return full_graph, improve_graph
