from __future__ import annotations

import re
from typing import Any

from sympy import N, sympify

from truthbattle.types import TaskSpec

DESMOS_URL = "https://www.desmos.com/calculator"


def _pretty(s: str) -> str:
    return s.replace("**", "^")


def _to_float(value: str) -> float | None:
    try:
        n = N(sympify(value))
        return float(n)
    except Exception:
        return None


def _point_from_ode_condition(label: str) -> dict[str, float] | None:
    m = re.match(r"^\s*y\s*\(\s*(.+?)\s*\)\s*=\s*(.+?)\s*$", label)
    if not m:
        return None
    x = _to_float(m.group(1).strip())
    y = _to_float(m.group(2).strip())
    if x is None or y is None:
        return None
    return {"x": x, "y": y}


def build_graph_artifacts(task: TaskSpec, sympy_out: dict[str, Any]) -> dict[str, Any]:
    if task.task_type == "explain":
        return {"enabled": False, "reason": "No symbolic object to graph."}

    expressions: list[str] = []
    points: list[dict[str, float]] = []

    if task.task_type == "solve":
        expressions = [f"y={_pretty(task.lhs)}", f"y={_pretty(task.rhs)}"]
        for s in sympy_out.get("solutions", []):
            x = _to_float(s)
            if x is not None:
                points.append({"x": x, "y": 0.0})

    elif task.task_type == "simplify":
        expressions = [
            f"y={_pretty(sympy_out.get('expression', task.expression))}",
            f"y={_pretty(sympy_out.get('result', ''))}",
        ]

    elif task.task_type == "differentiate":
        expressions = [
            f"y={_pretty(sympy_out.get('expression', task.expression))}",
            f"y={_pretty(sympy_out.get('result', ''))}",
        ]

    elif task.task_type == "integrate":
        expressions = [
            f"y={_pretty(sympy_out.get('expression', task.expression))}",
            f"y={_pretty(sympy_out.get('result', ''))}",
        ]

    elif task.task_type == "ode":
        particulars = [
            p
            for p in sympy_out.get("particular_solutions", [])
            if isinstance(p, dict) and str(p.get("solution", "")).strip()
        ]
        if particulars:
            expressions = [f"y={_pretty(str(p['solution']))}" for p in particulars[:10]]
            for p in particulars:
                pt = _point_from_ode_condition(str(p.get("condition", "")))
                if pt:
                    points.append(pt)
        else:
            sols = [str(s) for s in sympy_out.get("solutions", []) if str(s).strip()]
            if sols:
                expressions = [f"y={_pretty(s)}" for s in sols[:3]]
            else:
                expressions = [f"y={_pretty(task.expression)}"]

    viewport = {
        "x": [-10, 10],
        "y": [-10, 10],
    }
    point_exprs = [f"({p['x']},{p['y']})" for p in points]
    clipboard_lines = expressions + point_exprs

    return {
        "enabled": True,
        "tool_calls": ["desmos", "mafs"],
        "desmos": {
            "url": DESMOS_URL,
            "how_to_use": "Open Desmos and paste each expression as a new line.",
            "expressions": expressions,
            "points": points,
            "clipboard_text": "\n".join(clipboard_lines),
        },
        "mafs": {
            "viewport": viewport,
            "curves": [{"expr": e} for e in expressions],
            "points": points,
        },
    }
