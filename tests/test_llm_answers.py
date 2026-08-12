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


def test_generate_reference_answer_includes_category_and_topic(monkeypatch):
    captured = {}

    def fake_chat(system, _user):
        captured["system"] = system
        return {"answer": "参考答案"}

    monkeypatch.setattr(llm, "_chat_json", fake_chat)
    llm.generate_reference_answer("问题", ["要点"], category="八股", topic="JVM")
    assert "八股" in captured["system"]
    assert "JVM" in captured["system"]
    # 分类会调整风格：八股 → 直击考点
    assert "直击考点" in captured["system"]


def test_generate_reference_answer_style_follows_category(monkeypatch):
    captured = {}

    def fake_chat(system, _user):
        captured["system"] = system
        return {"answer": "参考答案"}

    monkeypatch.setattr(llm, "_chat_json", fake_chat)
    llm.generate_reference_answer("问题", ["要点"], category="项目", topic="订单")
    assert "项目" in captured["system"]
    assert "项目背景" in captured["system"]


def test_generate_reference_answer_rejects_empty(monkeypatch):
    monkeypatch.setattr(llm, "_chat_json", lambda _system, _user: {})
    with pytest.raises(LLMError):
        llm.generate_reference_answer("问题", [])


def test_generate_keypoints_returns_clean_list(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_chat_json",
        lambda _system, _user: {"keypoints": ["1. 可重入", "- 异常自动释放", "2PC 两阶段提交"]},
    )
    keypoints = llm.generate_keypoints("问题", "答案")
    assert keypoints == ["可重入", "异常自动释放", "2PC 两阶段提交"]


def test_generate_keypoints_handles_string_and_alternative_keys(monkeypatch):
    monkeypatch.setattr(llm, "_chat_json", lambda _system, _user: {"points": "要点A\n要点B"})
    assert llm.generate_keypoints("问题", "答案") == ["要点A", "要点B"]


def test_generate_keypoints_caps_at_seven(monkeypatch):
    many = [f"要点{i}" for i in range(1, 10)]
    monkeypatch.setattr(llm, "_chat_json", lambda _system, _user: {"keypoints": many})
    assert len(llm.generate_keypoints("问题", "答案")) == 7


def test_generate_keypoints_rejects_empty(monkeypatch):
    monkeypatch.setattr(llm, "_chat_json", lambda _system, _user: {})
    with pytest.raises(LLMError):
        llm.generate_keypoints("问题", "答案")
