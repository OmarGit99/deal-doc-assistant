"""Chat models named in the settings, plus token-cost arithmetic."""

from dataclasses import dataclass
from typing import Literal

from langchain_openai import ChatOpenAI

from app.config import Settings


def make_chat_model(settings: Settings, role: Literal["answer", "router"] = "answer") -> ChatOpenAI:
    if settings.openai_api_key is None:
        raise RuntimeError("Set OPENAI_API_KEY in .env")
    return ChatOpenAI(
        model=settings.answer_model if role == "answer" else settings.router_model,
        openai_api_key=settings.openai_api_key,
        reasoning_effort=settings.reasoning_effort,
        max_tokens=settings.answer_max_tokens,  # sent as max_completion_tokens
        request_timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0  # includes reasoning tokens, which are billed as output

    def cost_usd(self, input_price_per_million: float, output_price_per_million: float) -> float:
        return (
            self.input_tokens * input_price_per_million
            + self.output_tokens * output_price_per_million
        ) / 1_000_000
