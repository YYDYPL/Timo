"""Integration tests for the review flow: suspend, force-review, and stats.

A throwaway SQLite database (INTERVIEW_DB_PATH) is used so the real
backend/data.db is never touched. The FastAPI TestClient runs the lifespan,
which auto-seeds the 25 built-in questions on an empty database.
"""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

from backend import db as backend_db

_TMP_DIR = tempfile.mkdtemp(prefix="timo_integration_")
_DB_FILE = os.path.join(_TMP_DIR, "integration.db")
# Other test modules import backend.db first and may have rebound DB_PATH, so
# pin it explicitly to this throwaway database for the whole module.
backend_db.DB_PATH = Path(_DB_FILE)

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


def _question_payload(**overrides) -> dict:
    payload = {
        "category": "项目",
        "topic": "集成测试",
        "question": "这是一道集成测试题",
        "answer": "参考答案",
        "keypoints": ["要点一", "要点二"],
        "difficulty": 3,
        "source": "",
        "suspended": False,
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def client():
    # Other test modules (test_db.py) rebind backend.db.DB_PATH at runtime, so
    # re-pin it here; then reset the database before each test.
    backend_db.DB_PATH = Path(_DB_FILE)
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(_DB_FILE + suffix)
        except FileNotFoundError:
            pass
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def suspended_question(client):
    created = client.post("/api/questions", json=_question_payload(suspended=True)).json()
    assert created.get("id") is not None
    return created


def test_fresh_db_auto_seeds(client):
    stats = client.get("/api/stats").json()
    assert stats["total_questions"] == 25
    assert stats["today_due"] == 25


def test_suspended_question_excluded_from_today_queue(client, suspended_question):
    qid = suspended_question["id"]
    queue = client.get("/api/review/today").json()
    assert qid not in [q["id"] for q in queue["items"]]
    detail = client.get(f"/api/questions/{qid}").json()
    assert detail["review"]["suspended"] is True


def test_force_review_unsuspends_and_schedules(client, suspended_question):
    qid = suspended_question["id"]
    response = client.post(f"/api/review/{qid}", json={"quality": 4})
    assert response.status_code == 200
    detail = client.get(f"/api/questions/{qid}").json()
    # A brand-new suspended card graded "good" is unsuspended and due tomorrow.
    assert detail["review"]["suspended"] is False
    assert detail["review"]["due_date"] != date.today().isoformat()
    today_queue = client.get("/api/review/today").json()
    assert qid not in [q["id"] for q in today_queue["items"]]


def test_put_can_toggle_suspended(client):
    created = client.post("/api/questions", json=_question_payload()).json()
    qid = created["id"]
    assert client.get(f"/api/questions/{qid}").json()["review"]["suspended"] is False

    client.put(f"/api/questions/{qid}", json={"suspended": True})
    assert client.get(f"/api/questions/{qid}").json()["review"]["suspended"] is True

    # A payload that only touches suspended still works.
    client.put(f"/api/questions/{qid}", json={"suspended": False})
    assert client.get(f"/api/questions/{qid}").json()["review"]["suspended"] is False


def test_stats_due_excludes_suspended(client, suspended_question):
    stats = client.get("/api/stats").json()
    # 25 seeded active cards + 1 suspended card; the suspended one is not due.
    assert stats["total_questions"] == 26
    assert stats["today_due"] == 25


def test_again_keeps_card_due_today(client):
    created = client.post("/api/questions", json=_question_payload()).json()
    qid = created["id"]
    response = client.post(f"/api/review/{qid}", json={"quality": 1})
    assert response.status_code == 200
    assert response.json()["repeat_today"] is True
    detail = client.get(f"/api/questions/{qid}").json()
    # 重来 = 还没记住：仍归今天待复习，刷新后还在今日队列。
    assert detail["review"]["due_date"] == date.today().isoformat()
    today_queue = client.get("/api/review/today").json()
    assert qid in [q["id"] for q in today_queue["items"]]


def test_generate_answer_requires_question_text(client):
    response = client.post("/api/ai/generate-answer", json={"question": "  ", "keypoints": []})
    assert response.status_code == 422


def test_generate_keypoints_requires_question_and_answer(client):
    no_question = client.post("/api/ai/generate-keypoints", json={"question": "  ", "answer": "答案"})
    assert no_question.status_code == 422
    no_answer = client.post("/api/ai/generate-keypoints", json={"question": "题目", "answer": "  "})
    assert no_answer.status_code == 422
