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


def test_fenced_json_containing_nested_code_fence():
    # 模型把 JSON 包进 ```json 围栏，而答案内容里又有一层代码围栏：
    # 旧的「围栏正则」会误把答案里的 ``` 当成 JSON 围栏结束而截断。
    text = '```json\n{"answer": "```java\\npublic class X {}\\n```"}\n```'
    parsed = _extract_json(text)
    assert parsed["answer"] == "```java\npublic class X {}\n```"


def test_wrapped_json_with_unbalanced_brace_inside_string():
    # 字符串值里含未配平的 }，旧的括号配平会误判为 JSON 结束。
    text = '好的：{"answer": "这里有 } 半个括号", "ok": true}，完毕'
    parsed = _extract_json(text)
    assert parsed["answer"] == "这里有 } 半个括号"
    assert parsed["ok"] is True


def test_prose_with_curly_braces_in_code_example():
    # 参考答案里出现 { ... } 代码示例、外层还被说明文字包裹。
    text = '回答如下：{"answer": "HashMap 的 put: key.hashCode() & (n-1)，树化时 {left, right}", "k": 1} 仅供参考'
    parsed = _extract_json(text)
    assert parsed["k"] == 1
