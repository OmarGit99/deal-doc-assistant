"""The question-answering chain:

    retrieve -> not-found gate -> format sections -> prompt -> model (structured output)
             -> citation validator -> AnswerResult

Built with LCEL so every step shows up as its own span in a LangSmith trace.
"""

import logging
import time
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables import (
    Runnable,
    RunnableBranch,
    RunnableConfig,
    RunnableLambda,
)
from pydantic import BaseModel, Field

from app.chains.citations import Citation, validate_citations
from app.chains.prompts import ANSWER_PROMPT, NOT_FOUND, format_sections
from app.config import Settings
from app.llm import Usage, make_chat_model
from app.retrieval.hybrid import HybridRetriever, RetrievalResult

log = logging.getLogger(__name__)

Reason = Literal[
    "answered",  # found, with at least one verified citation
    "low_retrieval_score",  # the gate stopped it before the model was called
    "model_declined",  # the model said the sections do not answer the question
    "no_valid_citations",  # the model answered, but no citation survived validation
    "model_error",  # the model call failed or returned unparseable output
]


class AnswerDraft(BaseModel):
    """An answer to the question, supported by exact quotes from the sections."""

    # This class is sent to OpenAI as a strict JSON schema; the docstring and field
    # descriptions above and below are part of what the model reads.

    found: bool = Field(description="False if the sections do not answer the question")
    answer: str = Field(description="The answer, or a one-line note on what is missing")
    citations: list[Citation] = Field(description="One or more citations per claim")


class SourceRef(BaseModel):
    chunk_id: str
    section_number: str
    section_title: str
    rerank_score: float | None


class AnswerResult(BaseModel):
    question: str
    deal_ids: list[str]
    found: bool
    answer: str
    citations: list[Citation]
    reason: Reason
    rejected_citations: int = 0
    sources: list[SourceRef]  # what was retrieved, in rank order
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    timings_ms: dict[str, float] = Field(default_factory=dict)
    trace_id: str | None = None  # filled in once LangSmith tracing is on (Week 3)


def _sources(retrieval: RetrievalResult) -> list[SourceRef]:
    return [
        SourceRef(
            chunk_id=c.chunk_id,
            section_number=c.section_number,
            section_title=c.section_title,
            rerank_score=c.rerank_score,
        )
        for c in retrieval.candidates
    ]


def build_answer_chain(
    retriever: HybridRetriever,
    structured_llm: Runnable[Any, dict[str, Any]],
    *,
    not_found_threshold: float,
    input_price: float,
    output_price: float,
) -> Runnable[dict[str, Any], AnswerResult]:
    """`structured_llm` is a chat model wrapped with
    with_structured_output(AnswerDraft, include_raw=True); tests pass a stand-in."""

    def retrieve(inputs: dict[str, Any]) -> dict[str, Any]:
        result = retriever.retrieve(inputs["question"], inputs["deal_ids"])
        return {**inputs, "retrieval": result}

    def should_skip_model(state: dict[str, Any]) -> bool:
        retrieval: RetrievalResult = state["retrieval"]
        best = retrieval.best_rerank_score
        return not retrieval.candidates or (best is not None and best < not_found_threshold)

    def not_found(state: dict[str, Any]) -> AnswerResult:
        retrieval: RetrievalResult = state["retrieval"]
        return AnswerResult(
            question=state["question"],
            deal_ids=state["deal_ids"],
            found=False,
            answer=NOT_FOUND,
            citations=[],
            reason="low_retrieval_score",
            sources=_sources(retrieval),
            timings_ms=dict(retrieval.timings_ms),
        )

    def generate(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
        retrieval: RetrievalResult = state["retrieval"]
        prompt_vars = {
            "question": state["question"],
            "deals": ", ".join(state["deal_ids"]),
            "sections": format_sections(retrieval.candidates),
        }
        start = time.perf_counter()
        try:
            output = (ANSWER_PROMPT | structured_llm).invoke(prompt_vars, config)
        except Exception:  # timeouts, rate limits after retries, API errors
            log.exception("answer model call failed")
            output = {"raw": None, "parsed": None, "parsing_error": "model call failed"}
        llm_ms = round((time.perf_counter() - start) * 1000, 1)
        return {**state, "llm_output": output, "llm_ms": llm_ms}

    def finalize(state: dict[str, Any]) -> AnswerResult:
        retrieval: RetrievalResult = state["retrieval"]
        output = state["llm_output"]
        raw = output.get("raw")
        usage = Usage()
        if isinstance(raw, AIMessage) and raw.usage_metadata:
            usage = Usage(raw.usage_metadata["input_tokens"], raw.usage_metadata["output_tokens"])
        base: dict[str, Any] = {
            "question": state["question"],
            "deal_ids": state["deal_ids"],
            "sources": _sources(retrieval),
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": round(usage.cost_usd(input_price, output_price), 6),
            "timings_ms": {**retrieval.timings_ms, "llm": state["llm_ms"]},
        }
        draft: AnswerDraft | None = output.get("parsed")
        if draft is None:
            log.warning("answer model output unusable: %s", output.get("parsing_error"))
            return AnswerResult(
                **base, found=False, answer=NOT_FOUND, citations=[], reason="model_error"
            )
        if not draft.found:
            return AnswerResult(
                **base, found=False, answer=NOT_FOUND, citations=[], reason="model_declined"
            )

        valid, rejected = validate_citations(draft.citations, retrieval.candidates)
        for r in rejected:
            log.warning(
                "citation rejected (%s): %s %r", r.reason, r.citation.chunk_id, r.citation.quote
            )
        if not valid:
            return AnswerResult(
                **base,
                found=False,
                answer=NOT_FOUND,
                citations=[],
                reason="no_valid_citations",
                rejected_citations=len(rejected),
            )
        return AnswerResult(
            **base,
            found=True,
            answer=draft.answer,
            citations=valid,
            reason="answered",
            rejected_citations=len(rejected),
        )

    answer_path = RunnableLambda(generate) | RunnableLambda(finalize)
    gate = RunnableBranch((should_skip_model, RunnableLambda(not_found)), answer_path)
    return (RunnableLambda(retrieve) | gate).with_config(run_name="answer_question")


def build_answer_chain_from_settings(
    settings: Settings, retriever: HybridRetriever
) -> Runnable[dict[str, Any], AnswerResult]:
    llm = make_chat_model(settings, "answer")
    structured = llm.with_structured_output(AnswerDraft, include_raw=True)
    return build_answer_chain(
        retriever,
        structured,
        not_found_threshold=settings.not_found_threshold,
        input_price=settings.answer_input_price_per_million,
        output_price=settings.answer_output_price_per_million,
    )
