"""Pydantic request/response models shared by the FastAPI routes."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class QuestionBase(BaseModel):
    category: str = "八股"
    topic: str = ""
    question: str
    answer: str = ""
    keypoints: list[str] = Field(default_factory=list)
    difficulty: int = Field(default=3, ge=1, le=5)
    source: str = ""
    suspended: bool = False


class QuestionCreate(QuestionBase):
    pass


class QuestionUpdate(BaseModel):
    category: Optional[str] = None
    topic: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    keypoints: Optional[list[str]] = None
    difficulty: Optional[int] = Field(default=None, ge=1, le=5)
    source: Optional[str] = None
    suspended: Optional[bool] = None


class QuestionOut(QuestionBase):
    id: int
    created_at: str


class ReviewSubmit(BaseModel):
    # SM-2 quality: 1 (again), 3 (hard), 4 (good), 5 (easy).
    quality: Literal[1, 3, 4, 5]
    covered_keypoints: list[Any] = Field(default_factory=list)


class ReviewOut(BaseModel):
    question_id: int
    ease_factor: float
    interval: int
    repetitions: int
    due_date: str
    last_reviewed_at: Optional[str] = None


class ProjectBase(BaseModel):
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class ProjectOut(ProjectBase):
    id: int
    created_at: str


class EvaluateAnswerRequest(BaseModel):
    question_id: Optional[int] = None
    question: Optional[str] = None
    answer: str
    keypoints: Optional[list[str]] = None


class GenerateAnswerRequest(BaseModel):
    question: str
    keypoints: list[str] = Field(default_factory=list)


class FollowupQuestionOut(BaseModel):
    question: str
    answer: str = ""
    keypoints: list[str] = Field(default_factory=list)


class GenerateFollowupsRequest(BaseModel):
    count: int = Field(default=6, ge=5, le=8)
    save: bool = False


class ImportFollowupsRequest(BaseModel):
    questions: list[FollowupQuestionOut] = Field(default_factory=list)
    suspended: bool = False


class StatsOut(BaseModel):
    today_due: int
    total_questions: int
    mastered_count: int
    mastery_percent: float
    by_category: list[dict[str, Any]]
    by_topic: list[dict[str, Any]]
    recent_reviews: list[dict[str, Any]]


__all__ = [
    "EvaluateAnswerRequest",
    "FollowupQuestionOut",
    "GenerateAnswerRequest",
    "GenerateFollowupsRequest",
    "ImportFollowupsRequest",
    "ProjectCreate",
    "ProjectOut",
    "ProjectUpdate",
    "QuestionCreate",
    "QuestionOut",
    "QuestionUpdate",
    "ReviewOut",
    "ReviewSubmit",
    "StatsOut",
]
