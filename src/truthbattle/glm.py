from __future__ import annotations

import base64
import json
import os
from typing import Any
from urllib.parse import urlparse

import httpx

from truthbattle.prompts import (
    PROVER_TUTOR_SYSTEM_PROMPT,
    SOCRATIC_TUTOR_SYSTEM_PROMPT,
    TASK_PARSER_SYSTEM_PROMPT,
    TASK_REPAIR_SYSTEM_PROMPT,
    VISION_EXTRACT_SYSTEM_PROMPT,
)


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def _model_content(data: dict[str, Any]) -> str:
    return str(data.get("choices", [{}])[0].get("message", {}).get("content", ""))


def _base_config() -> tuple[str, str, str]:
    base_url = os.getenv("GLM_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("GLM_API_KEY", "").strip()
    model = os.getenv("GLM_MODEL", "glm-4.7")
    return base_url, api_key, model


async def _post_chat(
    payload: dict[str, Any], timeout_seconds: float = 45.0
) -> dict[str, Any] | None:
    base_url, api_key, _ = _base_config()
    if not base_url:
        return None

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        try:
            res = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            res.raise_for_status()
            return res.json()
        except Exception:
            return None


async def glm_extract_task(question: str) -> dict[str, Any] | None:
    _, _, model = _base_config()
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": TASK_PARSER_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "response_format": {"type": "json_object"},
    }
    data = await _post_chat(payload)
    if not data:
        return None
    return _extract_json(_model_content(data))


async def glm_repair_task(
    original_question: str,
    previous_task_json: dict[str, Any],
    sympy_error: str,
) -> dict[str, Any] | None:
    _, _, model = _base_config()
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": TASK_REPAIR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "original_question": original_question,
                        "previous_task_json": previous_task_json,
                        "sympy_error": sympy_error,
                    },
                    ensure_ascii=True,
                ),
            },
        ],
        "response_format": {"type": "json_object"},
    }
    data = await _post_chat(payload)
    if not data:
        return None
    return _extract_json(_model_content(data))


async def glm_extract_from_images(
    image_urls: list[str],
    user_text: str = "",
    forward_headers: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    base_url, _, _ = _base_config()
    if not base_url or not image_urls:
        return None

    async def _normalize_url_for_vision(url: str) -> tuple[str | None, str | None]:
        u = url.strip()
        if not u:
            return None, "empty image url"
        if u.startswith("data:image/"):
            return u, None

        parsed = urlparse(u)
        host = (parsed.hostname or "").lower()
        is_local_file_api = parsed.path.startswith("/api/v1/files/")
        if is_local_file_api and host in {"127.0.0.1", "localhost"}:
            headers: dict[str, str] = {}
            if forward_headers:
                auth = forward_headers.get("authorization", "").strip()
                cookie = forward_headers.get("cookie", "").strip()
                if auth:
                    headers["Authorization"] = auth
                if cookie:
                    headers["Cookie"] = cookie
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.get(u, headers=headers)
                    if r.status_code != 200:
                        return None, f"local image fetch failed: HTTP {r.status_code}"
                    ctype = (
                        r.headers.get("content-type", "").split(";")[0].strip().lower()
                    )
                    if not ctype.startswith("image/"):
                        return (
                            None,
                            f"local image fetch returned non-image content-type: {ctype or 'unknown'}",
                        )
                    b64 = base64.b64encode(r.content).decode("ascii")
                    return f"data:{ctype};base64,{b64}", None
            except Exception as e:
                return None, f"local image fetch error: {e}"

        return u, None

    normalized_urls: list[str] = []
    notes: list[str] = []
    for u in image_urls:
        normalized, note = await _normalize_url_for_vision(u)
        if normalized:
            normalized_urls.append(normalized)
        elif note:
            notes.append(note)

    if not normalized_urls:
        return {
            "transcription": "",
            "normalized_problem": "",
            "hints": [],
            "confidence": 0.0,
            "note": (
                "No accessible image could be sent to vision model. "
                + ("; ".join(notes[:2]) if notes else "Image URL was inaccessible.")
            ),
        }

    vision_model = os.getenv("GLM_VISION_MODEL", "glm-4.6v")
    content: list[dict[str, Any]] = []
    if user_text.strip():
        content.append({"type": "text", "text": user_text.strip()})
    else:
        content.append(
            {
                "type": "text",
                "text": "Extract the complete math problem from this image and normalize it.",
            }
        )
    for url in normalized_urls:
        if url.strip():
            content.append({"type": "image_url", "image_url": {"url": url.strip()}})

    payload = {
        "model": vision_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": VISION_EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }
    raw_timeout = os.getenv("GLM_VISION_HTTP_TIMEOUT_SECONDS", "120").strip()
    try:
        vision_http_timeout = float(raw_timeout)
        if vision_http_timeout <= 0:
            vision_http_timeout = 120.0
    except Exception:
        vision_http_timeout = 120.0

    data = await _post_chat(payload, timeout_seconds=vision_http_timeout)
    if not data:
        return None

    out = _extract_json(_model_content(data))
    if out:
        if notes and not out.get("note"):
            out["note"] = "; ".join(notes[:2])
        return out

    content_text = _model_content(data).strip()
    if content_text:
        out = {
            "transcription": content_text,
            "normalized_problem": content_text,
            "hints": [],
            "confidence": 0.4,
        }
        if notes:
            out["note"] = "; ".join(notes[:2])
        return out
    return None


async def glm_tutor_response(
    question: str,
    evidence: dict[str, Any],
    style: str = "default",
) -> str | None:
    base_url, _, model = _base_config()
    if not base_url:
        return None

    system_prompt = (
        SOCRATIC_TUTOR_SYSTEM_PROMPT
        if style.strip().lower() == "socratic"
        else PROVER_TUTOR_SYSTEM_PROMPT
    )

    payload = {
        "model": model,
        "temperature": 0.15,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Question:\n"
                    f"{question}\n\n"
                    "Evidence JSON:\n"
                    f"{json.dumps(evidence, ensure_ascii=True)}"
                ),
            },
        ],
    }
    data = await _post_chat(payload)
    if not data:
        return None
    content = _model_content(data).strip()
    return content or None
