from langchain_openai import ChatOpenAI
from core.config import AppConfig


def create_llm(
    cfg: AppConfig, *, model: str, temperature: float, top_p: float
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        model_kwargs={"top_p": top_p},
    )
