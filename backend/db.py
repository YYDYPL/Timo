"""SQLite persistence helpers for the interview-prep application.

The application deliberately keeps persistence small and boring: one SQLite
file, opened per request, with JSON encoded lists for keypoints and tags.  A
connection-per-operation model works well for this local tool and avoids
sharing sqlite cursors between FastAPI worker threads.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator


BACKEND_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("INTERVIEW_DB_PATH", str(BACKEND_DIR / "data.db")))


def local_now() -> str:
    """Return a local-time ISO timestamp (naive, no timezone offset).

    The rest of the app schedules on ``date.today()`` (local wall clock), so
    review timestamps must come from the same clock or they drift a day for
    users east/west of UTC around midnight.
    """

    return datetime.now().isoformat(timespec="seconds")


def today_iso() -> str:
    return date.today().isoformat()


def dumps(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def loads(value: Any, default: Any = None) -> Any:
    if value is None:
        return [] if default is None else default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return [] if default is None else default


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """Yield a configured SQLite connection and commit on success."""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables and indexes if they do not already exist."""

    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL DEFAULT '八股',
                topic TEXT NOT NULL DEFAULT '',
                question TEXT NOT NULL,
                answer TEXT NOT NULL DEFAULT '',
                keypoints TEXT NOT NULL DEFAULT '[]',
                difficulty INTEGER NOT NULL DEFAULT 3 CHECK (difficulty BETWEEN 1 AND 5),
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reviews (
                question_id INTEGER PRIMARY KEY,
                ease_factor REAL NOT NULL DEFAULT 2.5,
                interval INTEGER NOT NULL DEFAULT 0,
                repetitions INTEGER NOT NULL DEFAULT 0,
                due_date TEXT NOT NULL,
                last_reviewed_at TEXT,
                suspended INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS review_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                quality INTEGER NOT NULL CHECK (quality BETWEEN 1 AND 5),
                covered_keypoints TEXT NOT NULL DEFAULT '[]',
                reviewed_at TEXT NOT NULL,
                FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category);
            CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic);
            CREATE INDEX IF NOT EXISTS idx_reviews_due_date ON reviews(due_date);
            CREATE INDEX IF NOT EXISTS idx_review_logs_question ON review_logs(question_id);
            CREATE INDEX IF NOT EXISTS idx_review_logs_reviewed_at ON review_logs(reviewed_at);
            """
        )
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the original schema in-place."""

    review_columns = {row[1] for row in conn.execute("PRAGMA table_info(reviews)").fetchall()}
    if "suspended" not in review_columns:
        conn.execute("ALTER TABLE reviews ADD COLUMN suspended INTEGER NOT NULL DEFAULT 0")


def row_to_question(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["keypoints"] = loads(item.get("keypoints"), [])
    return item


def row_to_project(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["tags"] = loads(item.get("tags"), [])
    return item


def row_to_review(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    return item


def ensure_review(conn: sqlite3.Connection, question_id: int, due_date: str | None = None, suspended: bool = False) -> None:
    conn.execute(
        """
        INSERT INTO reviews(question_id, ease_factor, interval, repetitions, due_date, suspended)
        VALUES (?, 2.5, 0, 0, ?, ?)
        ON CONFLICT(question_id) DO NOTHING
        """,
        (question_id, due_date or today_iso(), int(bool(suspended))),
    )


def insert_question(
    *,
    category: str,
    topic: str,
    question: str,
    answer: str,
    keypoints: list[str],
    difficulty: int = 3,
    source: str = "",
    suspended: bool = False,
) -> dict[str, Any]:
    now = local_now()
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO questions(category, topic, question, answer, keypoints, difficulty, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (category, topic, question, answer, dumps(keypoints), difficulty, source, now),
        )
        qid = int(cur.lastrowid)
        ensure_review(conn, qid, suspended=suspended)
        return row_to_question(conn.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone()) or {}


def count_questions() -> int:
    with get_db() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0])


__all__ = [
    "DB_PATH",
    "dumps",
    "ensure_review",
    "get_db",
    "init_db",
    "insert_question",
    "loads",
    "local_now",
    "row_to_project",
    "row_to_question",
    "row_to_review",
    "today_iso",
]
