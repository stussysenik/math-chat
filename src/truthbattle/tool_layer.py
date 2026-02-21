from __future__ import annotations

import os
from typing import Any

import httpx

from truthbattle.word_problems import try_solve_incline_friction

WOLFRAM_QUERY_URL = "https://api.wolframalpha.com/v2/query"


def _dedupe_preserve(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        x = item.strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


async def query_wolfram(
    question: str,
    timeout_seconds: float = 7.0,
) -> dict[str, Any]:
    app_id = os.getenv("WOLFRAM_APP_ID", "").strip()
    if not app_id:
        return {
            "status": "skipped",
            "reason": "WOLFRAM_APP_ID is not configured.",
            "pods": [],
        }

    q = " ".join(question.split())
    if not q:
        return {
            "status": "skipped",
            "reason": "Empty query.",
            "pods": [],
        }

    params = {
        "appid": app_id,
        "input": q[:1200],
        "output": "JSON",
        "format": "plaintext",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            res = await client.get(WOLFRAM_QUERY_URL, params=params)
            res.raise_for_status()
            data = res.json()
    except Exception as e:
        return {
            "status": "error",
            "reason": f"Wolfram request failed: {e}",
            "pods": [],
        }

    query_result = data.get("queryresult", {}) if isinstance(data, dict) else {}
    success = bool(query_result.get("success", False))
    pods = query_result.get("pods", []) or []
    parsed_pods: list[dict[str, Any]] = []
    for pod in pods[:6]:
        if not isinstance(pod, dict):
            continue
        title = str(pod.get("title", "")).strip() or "Result"
        subpods = pod.get("subpods", []) or []
        plaintexts: list[str] = []
        for sub in subpods:
            if not isinstance(sub, dict):
                continue
            p = str(sub.get("plaintext", "")).strip()
            if p:
                plaintexts.append(p)
        plaintexts = _dedupe_preserve(plaintexts)
        if plaintexts:
            parsed_pods.append({"title": title, "plaintext": plaintexts})

    assumptions = query_result.get("assumptions", []) or []
    assumption_texts: list[str] = []
    for item in assumptions:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        values = item.get("values", []) or []
        vals: list[str] = []
        for v in values:
            if not isinstance(v, dict):
                continue
            desc = str(v.get("desc", "")).strip()
            if desc:
                vals.append(desc)
        vals = _dedupe_preserve(vals)
        if word and vals:
            assumption_texts.append(f"{word}: {', '.join(vals[:3])}")

    if parsed_pods:
        return {
            "status": "ok" if success else "partial",
            "input": q,
            "pods": parsed_pods,
            "assumptions": _dedupe_preserve(assumption_texts),
        }

    didyoumeans = query_result.get("didyoumeans", {}) or {}
    suggestions: list[str] = []
    if isinstance(didyoumeans, dict):
        dym = didyoumeans.get("didyoumean", [])
        if isinstance(dym, dict):
            suggestions = [str(dym.get("#text", "")).strip()]
        elif isinstance(dym, list):
            suggestions = [
                str(x.get("#text", "")).strip() for x in dym if isinstance(x, dict)
            ]
    suggestions = _dedupe_preserve(suggestions)
    return {
        "status": "partial" if success else "error",
        "input": q,
        "reason": "Wolfram returned no plaintext pods.",
        "pods": [],
        "suggestions": suggestions,
    }


async def run_tool_layer(
    question: str,
    *,
    enable_wolfram: bool,
    wolfram_timeout_seconds: float,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": "skipped",
        "selected": None,
        "tool_calls": [],
        "notes": [],
    }

    # Open-source deterministic word-problem solver.
    friction = try_solve_incline_friction(question)
    if friction:
        out.update(
            {
                "status": "ok",
                "selected": "inclined_plane_friction_solver",
                "tool_calls": [
                    "word_solver.incline_friction",
                    "sympy",
                    "lean",
                    "desmos",
                    "mafs",
                ],
                "word_problem": friction,
            }
        )
        return out

    if not enable_wolfram:
        out["notes"] = ["Wolfram fallback disabled by runtime options."]
        return out

    wolfram = await query_wolfram(question, timeout_seconds=wolfram_timeout_seconds)
    out["wolfram"] = wolfram
    status = str(wolfram.get("status", "skipped"))
    if status in {"ok", "partial"}:
        out["status"] = "partial"
        out["selected"] = "wolfram_alpha"
        out["tool_calls"] = ["wolfram_alpha"]
        return out

    note = str(wolfram.get("reason", "")).strip()
    if note:
        out["notes"] = [note]
    return out
