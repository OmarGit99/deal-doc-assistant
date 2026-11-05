from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.chains.answer import AnswerResult
from app.db import DealRow
from app.main import Services, create_app
from tests.test_retrieval import CORPUS


def fake_answer(question: str, deal_ids: list[str]) -> AnswerResult:
    return AnswerResult(
        question=question,
        deal_ids=deal_ids,
        found=True,
        answer="An answer.",
        citations=[],
        reason="answered",
        sources=[],
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    chunks = {c.chunk_id: c for c in CORPUS}
    services = Services(
        ask=fake_answer,
        known_deal_ids={"deal-a", "deal-b"},
        deals=lambda: [DealRow("deal-a", "Target", "Acquirer", date(2024, 1, 9), "https://x")],
        source=chunks.get,
        health=lambda: {"status": "ok", "database": "ok", "chunks": len(chunks)},
    )
    with TestClient(create_app(lambda: services)) as test_client:  # runs the startup hook
        yield test_client


def test_ask(client: TestClient) -> None:
    response = client.post("/ask", json={"question": "What is the fee?", "deal_ids": ["deal-a"]})
    assert response.status_code == 200
    assert response.json()["answer"] == "An answer."


def test_ask_rejects_unknown_deals(client: TestClient) -> None:
    response = client.post("/ask", json={"question": "What is the fee?", "deal_ids": ["nope"]})
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_ask_caps_question_length(client: TestClient) -> None:
    response = client.post("/ask", json={"question": "x" * 1001, "deal_ids": ["deal-a"]})
    assert response.status_code == 422


def test_ask_requires_a_deal(client: TestClient) -> None:
    assert (
        client.post("/ask", json={"question": "What is the fee?", "deal_ids": []}).status_code
        == 422
    )


def test_sources(client: TestClient) -> None:
    response = client.get("/sources/a-fee")
    assert response.status_code == 200
    body = response.json()
    assert body["section_number"] == "11.04"
    assert body["body"].startswith("The Company shall pay")
    assert client.get("/sources/missing").status_code == 404


def test_deals_and_health(client: TestClient) -> None:
    assert client.get("/deals").json()[0]["deal_id"] == "deal-a"
    assert client.get("/health").json() == {"status": "ok", "database": "ok", "chunks": 4}


def test_openapi_docs_page_is_served(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
