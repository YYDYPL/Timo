"""OpenAI-compatible LLM client and the application's two AI capabilities."""

from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from .db import get_active_llm_config
except ImportError:  # Allows running from backend/ directly (uvicorn main:app)
    from db import get_active_llm_config  # type: ignore


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


class LLMError(RuntimeError):
    """Base error surfaced by LLM-backed API endpoints."""


class LLMNotConfigured(LLMError):
    pass


def get_settings() -> dict[str, str]:
    """Return the active LLM connection settings.

    A saved config activated from the settings page takes precedence; when none
    is active the app falls back to the .env values.
    """

    active = get_active_llm_config()
    if active:
        return {
            "api_key": str(active.get("api_key") or "").strip(),
            "base_url": str(active.get("base_url") or "").strip(),
            "model": str(active.get("model") or "").strip(),
            "timeout": str(active.get("timeout") or 60),
            "source": "saved",
        }
    return {
        "api_key": os.getenv("LLM_API_KEY", "").strip(),
        "base_url": os.getenv("LLM_BASE_URL", "").strip(),
        "model": os.getenv("LLM_MODEL", "").strip(),
        "timeout": os.getenv("LLM_TIMEOUT", "60"),
        "source": "env",
    }


def is_configured() -> bool:
    settings = get_settings()
    # Local OpenAI-compatible servers commonly do not require a real key.
    return bool(settings["model"] and (settings["api_key"] or settings["base_url"]))


def test_llm_connection(
    *,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    timeout: int = 60,
) -> dict[str, Any]:
    """Verify a candidate LLM source (not yet saved) with a minimal chat call.

    Returns ``{"ok": bool, "message": str}`` — it never raises, so the settings
    page can show the result inline. Only the values passed in are used; the
    active configuration is not touched.
    """

    base_url = (base_url or "").strip()
    api_key = (api_key or "").strip()
    model = (model or "").strip()
    timeout = max(1, min(int(timeout or 60), 30))

    if not model:
        return {"ok": False, "message": "请先填写模型名称"}
    if not base_url and not api_key:
        return {"ok": False, "message": "请至少填写 Base URL 或 API Key 之一"}

    try:
        from openai import OpenAI
    except ImportError as exc:
        return {"ok": False, "message": "openai 依赖未安装，请先运行 pip install -r requirements.txt"}

    client = OpenAI(api_key=api_key or "not-needed", base_url=base_url or None, timeout=timeout, max_retries=0)
    started = time.monotonic()
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        class_name = exc.__class__.__name__.lower()
        if status == 401:
            return {"ok": False, "message": "API Key 无效或已过期"}
        if status == 404:
            return {"ok": False, "message": "模型不存在，或 Base URL 路径不对（通常以 /v1 结尾）"}
        if status:
            return {"ok": False, "message": f"请求失败（HTTP {status}）：{str(exc)[:200]}"}
        if "timeout" in class_name:
            return {"ok": False, "message": "请求超时，请检查 Base URL 或网络"}
        if "connection" in class_name:
            return {"ok": False, "message": "无法连接，请检查 Base URL 或网络"}
        return {"ok": False, "message": f"连接失败：{str(exc)[:200]}"}

    latency_ms = int((time.monotonic() - started) * 1000)
    return {"ok": True, "message": f"连接成功，模型 {model} 可用（{latency_ms}ms）", "model": model, "latency_ms": latency_ms}


@lru_cache(maxsize=8)
def _client(api_key: str, base_url: str, timeout: float):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMNotConfigured("openai 依赖未安装，请先运行 pip install -r requirements.txt") from exc

    kwargs: dict[str, Any] = {
        "api_key": api_key or "not-needed",
        "timeout": timeout,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _extract_json(content: str) -> Any:
    text = (content or "").strip()
    if not text:
        raise LLMError("LLM 返回了空内容")

    # 整段就是合法 JSON 时直接返回（最干净的情况）。
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 否则逐字符扫描：在字符串字面量之外（含转义）找到第一个配平的
    # {...} 或 [...]，再尝试解析。这样能正确处理：
    # - 前后有说明文字 / 中文括号引号；
    # - 答案内容里嵌套的 Markdown 代码围栏或 { }、[ ] 字符；
    # - 旧的「围栏正则」会误把答案里的 ``` 当成 JSON 围栏的结束而截断。
    for start in range(len(text)):
        opener = text[start]
        if opener not in "{[":
            continue
        closer = "}" if opener == "{" else "]"
        depth = 0
        in_string = False
        escaped = False
        i = start
        while i < len(text):
            char = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == opener:
                    depth += 1
                elif char == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break  # 该起点不是有效 JSON，换下一个起点
            i += 1

    raise LLMError("LLM 未返回有效 JSON")


def _chat_json(system_prompt: str, user_prompt: str) -> Any:
    settings = get_settings()
    if not is_configured():
        raise LLMNotConfigured("LLM 未配置，请在 .env 中设置 LLM_BASE_URL、LLM_API_KEY 和 LLM_MODEL")

    client = _client(settings["api_key"], settings["base_url"], float(settings.get("timeout") or 60))
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
    """Generate and validate 5-8 interview questions for a project.

    Each question carries a reference ``answer`` (one concise, complete answer
    a candidate could actually say) plus 3-7 ``keypoints``. Keeping both lets
    imported questions work in the active-recall review flow.
    """

    count = max(5, min(8, int(count)))
    system_prompt = (
        "你是资深技术面试官。根据候选人的真实项目生成有区分度的追问，覆盖架构取舍、"
        "实现细节、故障排查、性能、数据一致性和复盘。每道题都要附一段简洁完整的中文参考答案"
        "（200-400 字，可被直接念出来）和 3-7 个要点。参考答案正文可适当使用 Markdown 排版"
        "（加粗、列表、行内代码、代码块）。只输出 JSON 对象，不要输出 JSON 之外的 Markdown。"
    )
    user_prompt = f"""
项目名称：{project.get('name', '')}
项目描述：{project.get('description', '')}
技术标签：{', '.join(project.get('tags', []) or [])}

请生成 {count} 道可能被问到的中文追问。
严格返回：
{{"questions":[{{"question":"问题文本","answer":"参考答案","keypoints":["要点1","要点2"]}}]}}
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
        if not question:
            continue
        answer = str(item.get("answer", "") or "").strip()
        raw_keypoints = item.get("keypoints", [])
        if isinstance(raw_keypoints, str):
            keypoints = [part.strip() for part in re.split(r"[\n;；]", raw_keypoints) if part.strip()]
        elif isinstance(raw_keypoints, list):
            keypoints = [str(part).strip() for part in raw_keypoints if str(part).strip()]
        else:
            keypoints = []
        result.append({"question": question, "answer": answer, "keypoints": keypoints[:7]})
        if len(result) >= count:
            break

    if not result:
        raise LLMError("LLM 没有生成可用的追问")
    return result


def generate_reference_answer(
    question: str,
    keypoints: list[str],
    category: str = "",
    topic: str = "",
) -> str:
    """Draft a concise reference answer from a question, its keypoints, and the
    question's category/topic (used to tune the answer style)."""

    category = (category or "").strip()
    topic = (topic or "").strip()

    style = {
        "八股": "直击考点、表述标准严谨，优先使用公认的定义与结论",
        "agent": "结合 Agent 工程实践来讲（工具调用、上下文管理、评估、多智能体等）",
        "项目": "结合项目背景讲清做法、难点、取舍与结果",
    }.get(category.lower(), "条理清晰地讲清核心概念、原理与要点")

    system_prompt = (
        f"你是资深技术面试官，为一道「{category or '未分类'}」分类、"
        f"「{topic or '未指定'}」主题的面试题撰写参考答案。"
        f"要求：{style}；简明完整（200-500 字），覆盖给出的全部要点；"
        "参考答案正文可适当使用 Markdown 排版（加粗、列表、行内代码、代码块）。"
        "只输出 JSON 对象，不要输出 JSON 之外的 Markdown。"
    )
    user_prompt = f"""
面试题：{question}
关键要点：{json.dumps(keypoints, ensure_ascii=False)}

返回：
{{"answer":"完整参考答案"}}
""".strip()
    payload = _chat_json(system_prompt, user_prompt)
    if not isinstance(payload, dict):
        raise LLMError("LLM 参考答案格式不正确")
    answer = str(payload.get("answer", "") or "").strip()
    if not answer:
        raise LLMError("LLM 没有生成参考答案")
    return answer


def generate_keypoints(question: str, answer: str) -> list[str]:
    """Derive 3-7 concise answer keypoints from a question and its reference answer."""

    system_prompt = (
        "你是资深技术面试官。根据面试题和参考答案，提炼 3-7 条最核心、可用于给回答打分的要点。"
        "每条要点要简短（一句话以内）、互相独立、不重复，尽量用名词短语而非长句。"
        "只输出 JSON 对象，不要输出 JSON 之外的 Markdown。"
    )
    user_prompt = f"""
面试题：{question}
参考答案：{answer}

返回：
{{"keypoints":["要点1","要点2","要点3"]}}
""".strip()
    payload = _chat_json(system_prompt, user_prompt)
    if not isinstance(payload, dict):
        raise LLMError("LLM 要点结果格式不正确")

    raw = payload.get("keypoints") or payload.get("points") or payload.get("items") or []
    if isinstance(raw, str):
        raw = re.split(r"[\n;；]", raw)

    result: list[str] = []
    for item in raw:
        cleaned = str(item).strip()
        # 去掉常见的编号/圆点前缀，但保留 "2PC"、"3NF" 这类以数字开头的术语。
        cleaned = re.sub(r"^\s*[-*•・]\s*", "", cleaned)
        cleaned = re.sub(r"^\d+[\.\)]\s+", "", cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            result.append(cleaned)

    if not result:
        raise LLMError("LLM 没有生成可用的要点")
    return result[:7]


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
    "generate_keypoints",
    "generate_reference_answer",
    "get_settings",
    "is_configured",
    "test_llm_connection",
]
