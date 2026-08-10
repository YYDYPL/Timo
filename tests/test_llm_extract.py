"""Regression tests for JSON extraction from chat completions (backend/llm.py).

Covers prose-wrapped replies and replies whose string values contain characters
that look like JSON delimiters, which used to break the old outermost-token
extraction heuristic.
"""

from __future__ import annotations

import pytest

from backend.llm import LLMError, _extract_json


def test_plain_json():
    assert _extract_json('{"coverage": 80}') == {"coverage": 80}


def test_prose_wrapped_json():
    text = '好的，结果为：{"coverage": 80, "missed": ["漏了细节"]}，祝进步！'
    assert _extract_json(text) == {"coverage": 80, "missed": ["漏了细节"]}


def test_fenced_json_block():
    text = '```json\n{"coverage": 60}\n```'
    assert _extract_json(text) == {"coverage": 60}


def test_string_value_contains_unbalanced_bracket():
    # The string value contains a "(" with no matching ")" - must not be
    # confused for the container tokens by the heuristic parser.
    text = '{"questions":[{"question":"为什么选它（因为这个", "keypoints":["要点A"]}]}'
    parsed = _extract_json(text)
    assert parsed["questions"][0]["question"] == "为什么选它（因为这个"


def test_string_value_contains_braces():
    text = '{"question": "synchronized 用于 {同步} 场景", "keypoints": ["a"]}'
    parsed = _extract_json(text)
    assert parsed["question"] == "synchronized 用于 {同步} 场景"


def test_leading_fake_opener_raises():
    # Prose that begins with an unbalanced "{" and is not JSON.
    with pytest.raises(LLMError):
        _extract_json("前文{乱起的花括号不是 JSON")


def test_empty_content_raises():
    with pytest.raises(LLMError):
        _extract_json("   ")


def test_non_json_plain_text_raises():
    with pytest.raises(LLMError):
        _extract_json("抱歉，我没法给出结构化答案。")


def test_array_at_top_level():
    assert _extract_json('[{"question": "q1"}]') == [{"question": "q1"}]
