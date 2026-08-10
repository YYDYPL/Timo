"""Tests for the LLM answer-generation helpers (network calls mocked out)."""

from __future__ import annotations

import pytest

from backend import llm
from backend.llm import LLMError


def test_followups_include_reference_answer(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_chat_json",
        lambda _system, _user: {
            "questions": [{"question": "q1", "answer": "a1", "keypoints": ["k1", "k2"]}]
        },
    )
    items = llm.generate_followup_questions({"name": "p", "description": "d", "tags": ["t"]}, count=5)
    assert items[0]["question"] == "q1"
    assert items[0]["answer"] == "a1"
    assert items[0]["keypoints"] == ["k1", "k2"]


def test_followups_accept_legacy_payload_without_answer(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_chat_json",
        lambda _system, _user: {"questions": [{"question": "q", "keypoints": ["k"]}]},
    )
    items = llm.generate_followup_questions({"name": "p"}, count=5)
    assert items[0]["answer"] == ""
    assert items[0]["keypoints"] == ["k"]


def test_generate_reference_answer_returns_string(monkeypatch):
    monkeypatch.setattr(llm, "_chat_json", lambda _system, _user: {"answer": "完整参考答案"})
    assert llm.generate_reference_answer("问题", ["要点"]) == "完整参考答案"


def test_generate_reference_answer_rejects_empty(monkeypatch):
    monkeypatch.setattr(llm, "_chat_json", lambda _system, _user: {})
    with pytest.raises(LLMError):
        llm.generate_reference_answer("问题", [])
