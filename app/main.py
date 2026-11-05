"""FastAPI app: the JSON API now, the web page in Week 4.

uv run uvicorn app.main:app --reload      then open http://127.0.0.1:8000/docs
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.chains.answer import AnswerResult, build_answer_chain_from_settings
from app.compat import use_selector_event_loop_on_windows
from app.config import get_settings
from app.db import DealRow, list_deals, make_engine
from app.retrieval.corpus import Candidate
from app.retrieval.factory import build_retriever
from app.retrieval.hybrid import RetrievalConfig

use_selector_event_loop_on_windows()

MAX_QUESTION_CHARS = 1000  # guardrail from the spec


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUESTION_CHARS)
    deal_ids: list[str] = Field(min_length=1, max_length=5)


class DealOut(BaseModel):
    deal_id: str
    target: str
    acquirer: str
    announcement_date: date
    source_url: str


class SourceOut(BaseModel):
    chunk_id: str
    deal_id: str
    section_number: str
    section_title: str
    header: str
    body: str


@dataclass
class Services:
    """Everything the endpoints need, built once at startup. Tests pass stand-ins."""

    ask: Callable[[str, list[str]], AnswerResult]
    known_deal_ids: set[str]
    deals: Callable[[], list[DealRow]]
    source: Callable[[str], Candidate | None]
    health: Callable[[], dict[str, Any]]


def build_services() -> Services:
    settings = get_settings()
    retriever = build_retriever(settings, config=RetrievalConfig(top_k=settings.top_k))
    chain = build_answer_chain_from_settings(settings, retriever)
    engine = make_engine(settings.database_url)
    chunks = {c.chunk_id: c for c in retriever.bm25.chunks}

    def health() -> dict[str, Any]:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok", "chunks": len(chunks)}

    return Services(
        ask=lambda q, deals: chain.invoke({"question": q, "deal_ids": deals}),
        known_deal_ids=retriever.bm25.deal_ids,
        deals=lambda: list_deals(engine),
        source=chunks.get,
        health=health,
    )


def create_app(services_factory: Callable[[], Services] = build_services) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = services_factory()  # loads the BM25 index and models once
        yield

    app = FastAPI(
        title="Deal-Document Assistant",
        description="Questions about public merger agreements, answered with section citations. "
        "Answers come from public filings and are not legal advice.",
        lifespan=lifespan,
    )

    def services(request: Request) -> Services:
        found: Services = request.app.state.services
        return found

    # Plain `def` endpoints run in FastAPI's thread pool, so a slow model call does not
    # block other requests.
    @app.post("/ask", response_model=AnswerResult)
    def ask(body: AskRequest, request: Request) -> AnswerResult:
        svc = services(request)
        unknown = sorted(set(body.deal_ids) - svc.known_deal_ids)
        if unknown:
            raise HTTPException(404, f"Unknown deal_id(s): {', '.join(unknown)}")
        return svc.ask(body.question, body.deal_ids)

    @app.get("/deals", response_model=list[DealOut])
    def deals(request: Request) -> list[DealOut]:
        return [DealOut(**row.__dict__) for row in services(request).deals()]

    @app.get("/sources/{chunk_id}", response_model=SourceOut)
    def source(chunk_id: str, request: Request) -> SourceOut:
        chunk = services(request).source(chunk_id)
        if chunk is None:
            raise HTTPException(404, f"No chunk {chunk_id}")
        return SourceOut(
            chunk_id=chunk.chunk_id,
            deal_id=chunk.deal_id,
            section_number=chunk.section_number,
            section_title=chunk.section_title,
            header=chunk.header,
            body=chunk.body,
        )

    @app.get("/health")
    def health(request: Request) -> dict[str, Any]:
        return services(request).health()

    return app


app = create_app()
