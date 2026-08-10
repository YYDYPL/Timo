"""Unit tests for backend/db.py: suspended reviews and local-time stamps."""

from __future__ import annotations

import pytest

from backend import db


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("INTERVIEW_DB_PATH", str(db_path))
    db.DB_PATH = db_path  # get_db() resolves this module global at call time
    db.init_db()
    return db_path


def _insert_question_row(conn, qid=999):
    conn.execute(
        "INSERT INTO questions(id, category, topic, question, answer, keypoints, difficulty, source, created_at)"
        " VALUES (?, '八股', '', 'q', '', '[]', 3, '', ?)",
        (qid, db.local_now()),
    )


def test_ensure_review_defaults_to_not_suspended(fresh_db):
    with db.get_db() as conn:
        _insert_question_row(conn)
        db.ensure_review(conn, 999)
        row = conn.execute("SELECT suspended FROM reviews WHERE question_id = 999").fetchone()
    assert row["suspended"] == 0


def test_ensure_review_honors_suspended(fresh_db):
    with db.get_db() as conn:
        _insert_question_row(conn)
        db.ensure_review(conn, 999, suspended=True)
        row = conn.execute("SELECT suspended FROM reviews WHERE question_id = 999").fetchone()
    assert row["suspended"] == 1


def test_insert_question_can_suspend(fresh_db):
    item = db.insert_question(category="八股", topic="t", question="q", answer="a", keypoints=["k"], suspended=True)
    with db.get_db() as conn:
        row = conn.execute("SELECT suspended FROM reviews WHERE question_id = ?", (item["id"],)).fetchone()
    assert row["suspended"] == 1


def test_insert_question_defaults_to_active(fresh_db):
    item = db.insert_question(category="八股", topic="t", question="q", answer="a", keypoints=["k"])
    with db.get_db() as conn:
        row = conn.execute("SELECT suspended FROM reviews WHERE question_id = ?", (item["id"],)).fetchone()
    assert row["suspended"] == 0


def test_local_now_is_local_naive_iso(fresh_db):
    stamp = db.local_now()
    assert "T" in stamp
    assert "+" not in stamp and "Z" not in stamp  # no UTC offset marker


def test_init_db_migrates_old_reviews_table(tmp_path, monkeypatch):
    # Simulate a database created before the `suspended` column existed.
    old_path = tmp_path / "old.db"
    import sqlite3

    conn = sqlite3.connect(str(old_path))
    conn.execute(
        """
        CREATE TABLE reviews (
            question_id INTEGER PRIMARY KEY,
            ease_factor REAL NOT NULL DEFAULT 2.5,
            interval INTEGER NOT NULL DEFAULT 0,
            repetitions INTEGER NOT NULL DEFAULT 0,
            due_date TEXT NOT NULL,
            last_reviewed_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("INTERVIEW_DB_PATH", str(old_path))
    db.DB_PATH = old_path
    db.init_db()
    with db.get_db() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(reviews)").fetchall()}
    assert "suspended" in columns
