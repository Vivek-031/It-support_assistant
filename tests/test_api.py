import json
import os
import tempfile
from pathlib import Path

# Must be set before the app is imported so the engine points at a throwaway database.
_TMP_DIR = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP_DIR) / 'test.db'}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.knowledge_base import SEED_FILE  # noqa: E402
from app.llm import LLMError  # noqa: E402
from app.retrieval import Article, KnowledgeBaseIndex  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def test_health_reports_seeded_knowledge_base(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["kb_articles"] >= 10


def test_create_ticket_stores_question_context_and_answer(client, monkeypatch):
    captured = {}

    def fake_generate(question, context):
        captured["question"] = question
        captured["context"] = context
        return "1. Restart the VPN client."

    monkeypatch.setattr(main, "generate_answer", fake_generate)

    response = client.post("/api/tickets", json={"question": "  My VPN will not   connect from home "})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "answered"
    assert body["question"] == "My VPN will not connect from home"
    assert body["ai_response"] == "1. Restart the VPN client."
    assert "VPN" in body["sources"][0]["title"]
    assert body["retrieved_context"] == captured["context"]
    assert "[KB-" in captured["context"]

    stored = client.get(f"/api/tickets/{body['id']}").json()
    assert stored["ai_response"] == body["ai_response"]
    assert stored["retrieved_context"] == body["retrieved_context"]


def test_llm_failure_keeps_ticket_as_failed(client, monkeypatch):
    def failing_generate(question, context):
        raise LLMError("The AI service timed out. Please try again.", 504)

    monkeypatch.setattr(main, "generate_answer", failing_generate)

    response = client.post("/api/tickets", json={"question": "Outlook is not receiving new emails"})
    assert response.status_code == 504
    ticket_id = response.json()["detail"]["ticket_id"]

    stored = client.get(f"/api/tickets/{ticket_id}").json()
    assert stored["status"] == "failed"
    assert stored["ai_response"] is None
    assert "timed out" in stored["error_message"]


@pytest.mark.parametrize("question", ["", "help me", "          ", "1234567890 !!"])
def test_rejects_invalid_questions(client, question):
    response = client.post("/api/tickets", json={"question": question})
    assert response.status_code == 422


def test_rejects_too_long_question(client):
    response = client.post("/api/tickets", json={"question": "a" * 1001})
    assert response.status_code == 422


def test_list_tickets_newest_first(client):
    response = client.get("/api/tickets")
    assert response.status_code == 200
    ids = [t["id"] for t in response.json()]
    assert ids == sorted(ids, reverse=True)


def test_unknown_ticket_returns_404(client):
    assert client.get("/api/tickets/999999").status_code == 404


def test_retrieval_ranks_relevant_article_first():
    rows = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    index = KnowledgeBaseIndex([Article(id=i, **row) for i, row in enumerate(rows, start=1)])

    top = index.search("documents stuck in the printer queue, nothing is printing")[0]
    assert "Printer" in top.article.title


def test_retrieval_returns_nothing_for_unrelated_text():
    rows = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    index = KnowledgeBaseIndex([Article(id=i, **row) for i, row in enumerate(rows, start=1)])

    assert index.search("banana smoothie recipe") == []
