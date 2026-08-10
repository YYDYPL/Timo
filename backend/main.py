"""FastAPI application for the local interview-prep tool."""

from __future__ import annotations

from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

try:
    from .db import (
        DB_PATH,
        count_questions,
        dumps,
        ensure_review,
        get_db,
        init_db,
        insert_question,
        loads,
        local_now,
        row_to_project,
        row_to_question,
        today_iso,
    )
    from .llm import (
        LLMError,
        LLMNotConfigured,
        evaluate_answer,
        generate_followup_questions,
        generate_reference_answer,
        is_configured,
    )
    from .models import (
        EvaluateAnswerRequest,
        FollowupQuestionOut,
        GenerateAnswerRequest,
        GenerateFollowupsRequest,
        ImportFollowupsRequest,
        ProjectCreate,
        ProjectUpdate,
        QuestionCreate,
        QuestionUpdate,
        ReviewSubmit,
    )
    from .seed import seed_database
    from .srs import QUALITY_LABELS, mastery_score, schedule_review
except ImportError:  # Allows: uvicorn main:app from inside backend/
    from db import (  # type: ignore
        DB_PATH,
        count_questions,
        dumps,
        ensure_review,
        get_db,
        init_db,
        insert_question,
        loads,
        local_now,
        row_to_project,
        row_to_question,
        today_iso,
    )
    from llm import (  # type: ignore
        LLMError,
        LLMNotConfigured,
        evaluate_answer,
        generate_followup_questions,
        generate_reference_answer,
        is_configured,
    )
    from models import (  # type: ignore
        EvaluateAnswerRequest,
        FollowupQuestionOut,
        GenerateAnswerRequest,
        GenerateFollowupsRequest,
        ImportFollowupsRequest,
        ProjectCreate,
        ProjectUpdate,
        QuestionCreate,
        QuestionUpdate,
        ReviewSubmit,
    )
    from seed import seed_database  # type: ignore
    from srs import QUALITY_LABELS, mastery_score, schedule_review  # type: ignore


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if count_questions() == 0:
        seed_database()
    yield


app = FastAPI(
    title="面试背题工具 API",
    version="1.0.0",
    description="Local-first question bank, SM-2 review queue, and optional LLM coaching.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _model_dict(model: Any, *, exclude_unset: bool = False) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)
    return model.dict(exclude_unset=exclude_unset)


def _clean_list(values: list[Any] | None) -> list[str]:
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def _joined_question(row: Any) -> dict[str, Any]:
    item = {
        "id": row["id"],
        "category": row["category"],
        "topic": row["topic"],
        "question": row["question"],
        "answer": row["answer"],
        "keypoints": loads(row["keypoints"], []),
        "difficulty": row["difficulty"],
        "source": row["source"],
        "created_at": row["created_at"],
    }
    keys = set(row.keys())
    if "review_ease_factor" in keys:
        item["review"] = {
            "question_id": row["id"],
            "ease_factor": row["review_ease_factor"] if row["review_ease_factor"] is not None else 2.5,
            "interval": row["review_interval"] if row["review_interval"] is not None else 0,
            "repetitions": row["review_repetitions"] if row["review_repetitions"] is not None else 0,
            "due_date": row["review_due_date"] or today_iso(),
            "last_reviewed_at": row["review_last_reviewed_at"],
            "suspended": bool(row["review_suspended"]) if row["review_suspended"] is not None else False,
        }
    return item


QUESTION_WITH_REVIEW_SQL = """
    SELECT q.*,
           r.ease_factor AS review_ease_factor,
           r.interval AS review_interval,
           r.repetitions AS review_repetitions,
           r.due_date AS review_due_date,
           r.last_reviewed_at AS review_last_reviewed_at,
           r.suspended AS review_suspended
    FROM questions q
    LEFT JOIN reviews r ON r.question_id = q.id
"""


def _require_question(question_id: int) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    item = row_to_question(row)
    if not item:
        raise HTTPException(status_code=404, detail="题目不存在")
    return item


def _require_project(project_id: int) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    item = row_to_project(row)
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在")
    return item


def _llm_http_error(exc: LLMError) -> HTTPException:
    if isinstance(exc, LLMNotConfigured):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@app.get("/api")
def api_index() -> dict[str, Any]:
    return {
        "name": "面试背题工具 API",
        "version": app.version,
        "docs": "/docs",
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    init_db()
    return {
        "status": "ok",
        "database": str(DB_PATH),
        "questions": count_questions(),
        "llm_configured": is_configured(),
    }


# ---------------------------------------------------------------------------
# Question bank


@app.get("/api/questions")
def list_questions(
    category: str | None = None,
    topic: str | None = None,
    search: str | None = None,
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if category:
        clauses.append("q.category = ?")
        params.append(category.strip())
    if topic:
        clauses.append("q.topic = ?")
        params.append(topic.strip())
    if search and search.strip():
        needle = f"%{search.strip()}%"
        clauses.append("(q.question LIKE ? OR q.answer LIKE ? OR q.topic LIKE ? OR q.keypoints LIKE ?)")
        params.extend([needle, needle, needle, needle])
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = QUESTION_WITH_REVIEW_SQL + where + " ORDER BY q.created_at DESC, q.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_joined_question(row) for row in rows]


@app.get("/api/questions/filters")
def question_filters() -> dict[str, Any]:
    with get_db() as conn:
        categories = [
            dict(row)
            for row in conn.execute(
                "SELECT category AS name, COUNT(*) AS count FROM questions GROUP BY category ORDER BY category"
            ).fetchall()
        ]
        topics = [
            dict(row)
            for row in conn.execute(
                "SELECT topic AS name, category, COUNT(*) AS count FROM questions GROUP BY category, topic ORDER BY category, topic"
            ).fetchall()
        ]
    return {"categories": categories, "topics": topics}


@app.get("/api/questions/{question_id}")
def get_question(question_id: int) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute(QUESTION_WITH_REVIEW_SQL + " WHERE q.id = ?", (question_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    return _joined_question(row)


@app.post("/api/questions", status_code=status.HTTP_201_CREATED)
def create_question(payload: QuestionCreate) -> dict[str, Any]:
    values = _model_dict(payload)
    values["question"] = values["question"].strip()
    if not values["question"]:
        raise HTTPException(status_code=422, detail="题目内容不能为空")
    values["category"] = values["category"].strip() or "八股"
    values["topic"] = values["topic"].strip()
    values["answer"] = values["answer"].strip()
    values["source"] = values["source"].strip()
    values["keypoints"] = _clean_list(values["keypoints"])
    return insert_question(**values)


@app.put("/api/questions/{question_id}")
@app.patch("/api/questions/{question_id}")
def update_question(question_id: int, payload: QuestionUpdate) -> dict[str, Any]:
    _require_question(question_id)
    values = _model_dict(payload, exclude_unset=True)
    if not values:
        return _require_question(question_id)
    # suspended lives on the reviews row, not on questions.
    suspended_value = values.pop("suspended", None)
    if "question" in values:
        values["question"] = (values["question"] or "").strip()
        if not values["question"]:
            raise HTTPException(status_code=422, detail="题目内容不能为空")
    for field in ("category", "topic", "answer", "source"):
        if field in values:
            values[field] = (values[field] or "").strip()
    if "category" in values and not values["category"]:
        values["category"] = "八股"
    if "keypoints" in values:
        values["keypoints"] = dumps(_clean_list(values["keypoints"]))

    with get_db() as conn:
        if values:
            assignments = ", ".join(f"{field} = ?" for field in values)
            conn.execute(
                f"UPDATE questions SET {assignments} WHERE id = ?",
                [*values.values(), question_id],
            )
        if suspended_value is not None:
            conn.execute(
                "UPDATE reviews SET suspended = ? WHERE question_id = ?",
                (int(bool(suspended_value)), question_id),
            )
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    return row_to_question(row) or {}


@app.delete("/api/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(question_id: int) -> Response:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="题目不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# SM-2 review flow


@app.get("/api/review/today")
@app.get("/api/reviews/today", include_in_schema=False)
def today_review_queue(
    on_date: date | None = Query(default=None, alias="date"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    target = (on_date or date.today()).isoformat()
    sql = (
        QUESTION_WITH_REVIEW_SQL
        + " WHERE COALESCE(r.suspended,0) = 0 AND r.due_date <= ?"
        " ORDER BY r.due_date ASC, r.repetitions ASC, q.difficulty DESC, q.id ASC LIMIT ?"
    )
    with get_db() as conn:
        rows = conn.execute(sql, (target, limit)).fetchall()
        total = int(
            conn.execute(
                "SELECT COUNT(*) FROM reviews WHERE COALESCE(suspended,0) = 0 AND due_date <= ?",
                (target,),
            ).fetchone()[0]
        )
    return {"date": target, "total": total, "items": [_joined_question(row) for row in rows]}


@app.post("/api/review/{question_id}")
@app.post("/api/reviews/{question_id}", include_in_schema=False)
def submit_review(question_id: int, payload: ReviewSubmit) -> dict[str, Any]:
    _require_question(question_id)
    reviewed_at = local_now()
    with get_db() as conn:
        ensure_review(conn, question_id)
        current_row = conn.execute("SELECT * FROM reviews WHERE question_id = ?", (question_id,)).fetchone()
        current = dict(current_row) if current_row is not None else {}
        next_state = schedule_review(current, payload.quality)
        conn.execute(
            """
            UPDATE reviews
            SET ease_factor = ?, interval = ?, repetitions = ?, due_date = ?, last_reviewed_at = ?, suspended = 0
            WHERE question_id = ?
            """,
            (
                next_state["ease_factor"],
                next_state["interval"],
                next_state["repetitions"],
                next_state["due_date"],
                reviewed_at,
                question_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO review_logs(question_id, quality, covered_keypoints, reviewed_at)
            VALUES (?, ?, ?, ?)
            """,
            (question_id, payload.quality, dumps(payload.covered_keypoints), reviewed_at),
        )
        row = conn.execute("SELECT * FROM reviews WHERE question_id = ?", (question_id,)).fetchone()
        remaining = int(
            conn.execute(
                "SELECT COUNT(*) FROM reviews WHERE COALESCE(suspended,0) = 0 AND due_date <= ?",
                (today_iso(),),
            ).fetchone()[0]
        )
    return {
        "question_id": question_id,
        "quality": payload.quality,
        "quality_label": QUALITY_LABELS.get(payload.quality, "重来"),
        "review": dict(row) if row is not None else next_state,
        "repeat_today": payload.quality < 3,
        "queue_remaining": remaining,
    }


@app.get("/api/review/logs")
@app.get("/api/reviews/logs", include_in_schema=False)
def review_logs(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT l.*, q.question, q.category, q.topic
            FROM review_logs l
            JOIN questions q ON q.id = l.question_id
            ORDER BY l.reviewed_at DESC, l.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["covered_keypoints"] = loads(item.get("covered_keypoints"), [])
        item["quality_label"] = QUALITY_LABELS.get(item["quality"], str(item["quality"]))
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Projects and AI-generated follow-ups


@app.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC, id DESC").fetchall()
    return [row_to_project(row) or {} for row in rows]


@app.get("/api/projects/{project_id}")
def get_project(project_id: int) -> dict[str, Any]:
    return _require_project(project_id)


@app.post("/api/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    values = _model_dict(payload)
    name = values["name"].strip()
    if not name:
        raise HTTPException(status_code=422, detail="项目名称不能为空")
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO projects(name, description, tags, created_at) VALUES (?, ?, ?, ?)",
            (name, values["description"].strip(), dumps(_clean_list(values["tags"])), local_now()),
        )
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_project(row) or {}


@app.put("/api/projects/{project_id}")
@app.patch("/api/projects/{project_id}")
def update_project(project_id: int, payload: ProjectUpdate) -> dict[str, Any]:
    _require_project(project_id)
    values = _model_dict(payload, exclude_unset=True)
    if not values:
        return _require_project(project_id)
    if "name" in values:
        values["name"] = (values["name"] or "").strip()
        if not values["name"]:
            raise HTTPException(status_code=422, detail="项目名称不能为空")
    if "description" in values:
        values["description"] = (values["description"] or "").strip()
    if "tags" in values:
        values["tags"] = dumps(_clean_list(values["tags"]))
    assignments = ", ".join(f"{field} = ?" for field in values)
    with get_db() as conn:
        conn.execute(f"UPDATE projects SET {assignments} WHERE id = ?", [*values.values(), project_id])
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return row_to_project(row) or {}


@app.delete("/api/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int) -> Response:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="项目不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _save_followups(project: dict[str, Any], items: list[dict[str, Any]], suspended: bool = False) -> list[dict[str, Any]]:
    topic = (project.get("tags") or [project["name"]])[0]
    saved = []
    for item in items:
        saved.append(
            insert_question(
                category="项目",
                topic=str(topic),
                question=str(item["question"]).strip(),
                answer=str(item.get("answer", "") or "").strip(),
                keypoints=_clean_list(item.get("keypoints", [])),
                difficulty=4,
                source=f"AI 追问 · {project['name']}",
                suspended=bool(suspended),
            )
        )
    return saved


@app.post("/api/projects/{project_id}/generate-followups")
def generate_project_followups(project_id: int, payload: GenerateFollowupsRequest) -> dict[str, Any]:
    project = _require_project(project_id)
    try:
        items = generate_followup_questions(project, payload.count)
    except LLMError as exc:
        raise _llm_http_error(exc) from exc
    saved = _save_followups(project, items) if payload.save else []
    return {"project_id": project_id, "items": items, "saved": saved}


@app.post("/api/projects/{project_id}/followups", status_code=status.HTTP_201_CREATED)
def import_project_followups(project_id: int, payload: ImportFollowupsRequest) -> dict[str, Any]:
    project = _require_project(project_id)
    items = [_model_dict(item) for item in payload.questions if item.question.strip()]
    if not items:
        raise HTTPException(status_code=422, detail="至少需要一道追问")
    saved = _save_followups(project, items, payload.suspended)
    return {"project_id": project_id, "count": len(saved), "items": saved}


# ---------------------------------------------------------------------------
# LLM answer evaluation


@app.post("/api/ai/evaluate")
def ai_evaluate(payload: EvaluateAnswerRequest) -> dict[str, Any]:
    if not payload.answer.strip():
        raise HTTPException(status_code=422, detail="请先输入你的回答")
    if payload.question_id is not None:
        stored = _require_question(payload.question_id)
        question = stored["question"]
        reference_answer = stored["answer"]
        keypoints = stored["keypoints"]
    else:
        question = (payload.question or "").strip()
        if not question:
            raise HTTPException(status_code=422, detail="question_id 或 question 至少提供一个")
        reference_answer = ""
        keypoints = _clean_list(payload.keypoints)
    try:
        result = evaluate_answer(
            question=question,
            reference_answer=reference_answer,
            keypoints=keypoints,
            candidate_answer=payload.answer.strip(),
        )
    except LLMError as exc:
        raise _llm_http_error(exc) from exc
    result["question_id"] = payload.question_id
    return result


@app.get("/api/ai/status")
def ai_status() -> dict[str, bool]:
    return {"configured": is_configured()}


@app.post("/api/ai/generate-answer")
def ai_generate_answer(payload: GenerateAnswerRequest) -> dict[str, Any]:
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="请先填写题目内容")
    keypoints = _clean_list(payload.keypoints)
    try:
        answer = generate_reference_answer(question, keypoints)
    except LLMError as exc:
        raise _llm_http_error(exc) from exc
    return {"answer": answer}


# ---------------------------------------------------------------------------
# Progress statistics


@app.get("/api/stats")
def get_stats(recent_limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    target = today_iso()
    with get_db() as conn:
        cards = conn.execute(
            """
            SELECT q.id, q.category, q.topic, q.question,
                   r.ease_factor, r.interval, r.repetitions, r.due_date, r.last_reviewed_at, r.suspended
            FROM questions q
            LEFT JOIN reviews r ON r.question_id = q.id
            ORDER BY q.id
            """
        ).fetchall()
        recent_rows = conn.execute(
            """
            SELECT l.id, l.question_id, l.quality, l.covered_keypoints, l.reviewed_at,
                   q.question, q.category, q.topic
            FROM review_logs l
            JOIN questions q ON q.id = l.question_id
            ORDER BY l.reviewed_at DESC, l.id DESC
            LIMIT ?
            """,
            (recent_limit,),
        ).fetchall()

    groups: dict[str, dict[str, dict[str, Any]]] = {
        "category": defaultdict(lambda: {"total": 0, "mastered": 0, "due": 0, "score_sum": 0.0}),
        "topic": defaultdict(lambda: {"total": 0, "mastered": 0, "due": 0, "score_sum": 0.0}),
    }
    score_sum = 0.0
    mastered_count = 0
    today_due = 0
    for row in cards:
        card = dict(row)
        score = mastery_score(card)
        mastered = int(card.get("repetitions") or 0) >= 3
        suspended = int(card.get("suspended") or 0)
        due = not suspended and (not card.get("due_date") or card["due_date"] <= target)
        score_sum += score
        mastered_count += int(mastered)
        today_due += int(due)
        for group_name, key in (("category", card["category"]), ("topic", card["topic"] or "未分类")):
            bucket = groups[group_name][key]
            bucket["total"] += 1
            bucket["mastered"] += int(mastered)
            bucket["due"] += int(due)
            bucket["score_sum"] += score

    def group_rows(group_name: str) -> list[dict[str, Any]]:
        result = []
        for name, bucket in groups[group_name].items():
            average = round(bucket["score_sum"] / bucket["total"], 1) if bucket["total"] else 0.0
            result.append(
                {
                    "name": name,
                    "total": bucket["total"],
                    "mastered": bucket["mastered"],
                    "due": bucket["due"],
                    "mastery_percent": average,
                    "weak": average < 50,
                }
            )
        return sorted(result, key=lambda item: (not item["weak"], item["mastery_percent"], item["name"]))

    recent = []
    for row in recent_rows:
        item = dict(row)
        item["covered_keypoints"] = loads(item.get("covered_keypoints"), [])
        item["quality_label"] = QUALITY_LABELS.get(item["quality"], str(item["quality"]))
        recent.append(item)

    total = len(cards)
    return {
        "today_due": today_due,
        "total_questions": total,
        "mastered_count": mastered_count,
        "mastery_percent": round(score_sum / total, 1) if total else 0.0,
        "by_category": group_rows("category"),
        "by_topic": group_rows("topic"),
        "recent_reviews": recent,
    }


# Mount last so /api routes always win. StaticFiles(html=True) serves
# frontend/index.html for the root URL and keeps the app build-free.
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
