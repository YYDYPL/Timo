"""OpenAI-compatible LLM client and the application's two AI capabilities."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


class LLMError(RuntimeError):
    """Base error surfaced by LLM-backed API endpoints."""


class LLMNotConfigured(LLMError):
    pass


def get_settings() -> dict[str, str]:
    return {
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "base_url": os.getenv("LLM_BASE_URL", "").strip(),
        "model": os.getenv("LLM_MODEL", "").strip(),
    }


def is_configured() -> bool:
    settings = get_settings()
    # Local OpenAI-compatible servers commonly do not require a real key.
    return bool(settings["model"] and (settings["api_key"] or settings["base_url"]))


@lru_cache(maxsize=8)
def _client(api_key: str, base_url: str):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMNotConfigured("openai 依赖未安装，请先运行 pip install -r requirements.txt") from exc

    kwargs: dict[str, Any] = {
        "api_key": api_key or "not-needed",
        "timeout": float(os.getenv("LLM_TIMEOUT", "60")),
    }
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _extract_json(content: str) -> Any:
    text = (content or "").strip()
    if not text:
        raise LLMError("LLM 返回了空内容")

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Some compatible providers still wrap the object in prose. Extract
        # every JSON string literal so reply text (Chinese quotes, parentheses,
        # etc.) can no longer be mistaken for the container token.
        literal_re = re.compile(r'"((?:[^"\\]|\\.)*)"')
        literal_spans = [it.span() for it in literal_re.finditer(text)]
        for token in ("{", "["):
            closer = "}" if token == "{" else "]"
            for opener in re.finditer(re.escape(token), text):
                start = opener.start()
                if any(a < start < b for a, b in literal_spans):
                    continue
                # naive bracket balance until the matching closer
                balance = 0
                end = None
                for i in range(start, len(text)):
                    if text[i] == token:
                        balance += 1
                    elif text[i] == closer:
                        balance -= 1
                        if balance == 0:
                            end = i + 1
                            break
                if end is None:
                    continue
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        raise LLMError("LLM 未返回有效 JSON")


def _chat_json(system_prompt: str, user_prompt: str) -> Any:
    settings = get_settings()
    if not is_configured():
        raise LLMNotConfigured("LLM 未配置，请在 .env 中设置 LLM_BASE_URL、LLM_API_KEY 和 LLM_MODEL")

    client = _client(settings["api_key"], settings["base_url"])
    request: dict[str, Any] = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        response = client.chat.completions.create(**request)
    except Exception as first_error:
        # Older Ollama and a few OpenAI-compatible gateways reject
        # response_format. The prompt still requires strict JSON, so retry.
        request.pop("response_format", None)
        try:
            response = client.chat.completions.create(**request)
        except Exception as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise LLMError(f"LLM 调用失败：{detail}") from first_error

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise LLMError("LLM 响应格式不兼容") from exc
    return _extract_json(content or "")


def generate_followup_questions(project: dict[str, Any], count: int = 6) -> list[dict[str, Any]]:
    """Generate and validate 5-8 interview questions for a project."""

    count = max(5, min(8, int(count)))
    system_prompt = (
        "你是资深技术面试官。根据候选人的真实项目生成有区分度的追问，覆盖架构取舍、"
        "实现细节、故障排查、性能、数据一致性和复盘。只输出 JSON 对象，不要 Markdown。"
    )
    user_prompt = f"""
项目名称：{project.get('name', '')}
项目描述：{project.get('description', '')}
技术标签：{', '.join(project.get('tags', []) or [])}

请生成 {count} 道可能被问到的中文追问。每题提供 3-7 个简洁答案要点。
严格返回：
{{"questions":[{{"question":"问题文本","keypoints":["要点1","要点2"]}}]}}
""".strip()
    payload = _chat_json(system_prompt, user_prompt)
    if isinstance(payload, dict):
        items = payload.get("questions") or payload.get("followups") or payload.get("items") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        raw_keypoints = item.get("keypoints", [])
        if not question:
            continue
        if isinstance(raw_keypoints, str):
            keypoints = [part.strip() for part in re.split(r"[\n;；]", raw_keypoints) if part.strip()]
        elif isinstance(raw_keypoints, list):
            keypoints = [str(part).strip() for part in raw_keypoints if str(part).strip()]
        else:
            keypoints = []
        result.append({"question": question, "keypoints": keypoints[:7]})
        if len(result) >= count:
            break

    if not result:
        raise LLMError("LLM 没有生成可用的追问")
    return result


def evaluate_answer(
    *,
    question: str,
    reference_answer: str,
    keypoints: list[str],
    candidate_answer: str,
) -> dict[str, Any]:
    """Evaluate a recalled answer against the stored reference and keypoints."""

    system_prompt = (
        "你是严格但有帮助的技术面试教练。判断候选人答案是否真正覆盖关键知识点，"
        "不要因为措辞不同扣分。只输出 JSON 对象，不要 Markdown。"
    )
    user_prompt = f"""
面试题：{question}
参考答案：{reference_answer}
关键要点：{json.dumps(keypoints, ensure_ascii=False)}
候选人回答：{candidate_answer}

返回以下结构：
{{"coverage":0到100的整数,"covered":["已覆盖要点"],"missed":["遗漏要点"],"suggestion":"两三句话的改进建议"}}
""".strip()
    payload = _chat_json(system_prompt, user_prompt)
    if not isinstance(payload, dict):
        raise LLMError("LLM 评估结果格式不正确")

    raw_coverage = payload.get("coverage", payload.get("coverage_percent", payload.get("score", 0)))
    if isinstance(raw_coverage, str):
        match = re.search(r"\d+(?:\.\d+)?", raw_coverage)
        raw_coverage = float(match.group(0)) if match else 0
    try:
        coverage = int(round(float(raw_coverage)))
    except (TypeError, ValueError):
        coverage = 0
    coverage = max(0, min(100, coverage))

    def string_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [part.strip() for part in re.split(r"[\n;；]", value) if part.strip()]
        return []

    return {
        "coverage": coverage,
        "covered": string_list(payload.get("covered", [])),
        "missed": string_list(payload.get("missed", [])),
        "suggestion": str(payload.get("suggestion", "")).strip(),
    }


__all__ = [
    "LLMError",
    "LLMNotConfigured",
    "evaluate_answer",
    "generate_followup_questions",
    "get_settings",
    "is_configured",
]
