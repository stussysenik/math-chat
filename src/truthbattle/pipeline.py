from __future__ import annotations

import json
import os
import re
from asyncio import TimeoutError, wait_for
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from html import escape
from typing import Any

from sympy import Derivative, Expr, Function, N, Symbol, latex, sympify

from truthbattle.glm import glm_extract_from_images, glm_tutor_response
from truthbattle.graph_engine import build_graph_artifacts
from truthbattle.lean_engine import lean_first, lean_verify_solutions
from truthbattle.nlp import parse_task, repair_task
from truthbattle.sympy_engine import parse_for_lean, run_sympy, to_sympy
from truthbattle.tool_layer import run_tool_layer
from truthbattle.types import NodeTrace, TaskSpec, TutorResult
from truthbattle.verifier import build_verdict

_MODES = {"answer", "teach", "evidence"}
_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}


def _sympy_locals() -> dict:
    """Build a locals dict for sympify that recognizes common math functions."""
    loc: dict = {}
    for name in "yzwuvf":
        loc[name] = Function(name)
    for name in "xtsnabc":
        loc[name] = Symbol(name)
    loc["Derivative"] = Derivative
    loc["C1"] = Symbol("C1")
    loc["C2"] = Symbol("C2")
    return loc


def _to_latex(expr_str: str) -> str:
    """Best-effort convert a SymPy expression string to LaTeX."""
    s = expr_str.strip()
    if not s:
        return s
    try:
        parsed = sympify(s, locals=_sympy_locals())
        return latex(parsed)
    except Exception:
        return s


def _display_math(expr_str: str) -> str:
    """Wrap a SymPy expression as a display-math LaTeX block."""
    s = expr_str.strip()
    if "=" in s:
        parts = s.split("=", 1)
        lhs_tex = _to_latex(parts[0].strip())
        rhs_tex = _to_latex(parts[1].strip())
        return f"$$\n{lhs_tex} = {rhs_tex}\n$$"
    return f"$$\n{_to_latex(s)}\n$$"


def _numeric_approx(expr_str: str, digits: int = 12) -> str | None:
    s = expr_str.strip()
    if not s:
        return None
    try:
        val = N(sympify(s, locals=_sympy_locals()), digits)
        return str(val)
    except Exception:
        return None


def _render_symbolic_teach(task: TaskSpec, sympy_out: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## Symbolic Solution"]
    if task.task_type == "solve":
        lines.append(_display_math(f"{task.lhs} = {task.rhs}"))
        sols = [str(s) for s in sympy_out.get("solutions", []) if str(s).strip()]
        if sols:
            for i, sol in enumerate(sols, 1):
                lines.append(f"Solution {i}:")
                lines.append(_display_math(f"{task.variable} = {sol}"))
        else:
            lines.append("No closed-form symbolic solution was returned.")
        return lines

    if task.task_type == "ode":
        lines.append(_display_math(f"{task.expression} = 0"))
        sols = [str(s) for s in sympy_out.get("solutions", []) if str(s).strip()]
        if sols:
            lines.append("General solution family:")
            for s in sols[:3]:
                lines.append(_display_math(f"y({task.variable}) = {s}"))
        particulars = [
            p
            for p in sympy_out.get("particular_solutions", [])
            if isinstance(p, dict) and str(p.get("solution", "")).strip()
        ]
        if particulars:
            lines.append("Particular solutions from initial conditions:")
            for p in particulars:
                cond = str(p.get("condition", "")).strip()
                if cond:
                    lines.append(f"- {cond}")
                lines.append(
                    _display_math(f"y({task.variable}) = {str(p['solution'])}")
                )
        return lines

    if task.task_type in {"simplify", "differentiate", "integrate"}:
        lines.append(_display_math(task.expression))
        result = str(sympy_out.get("result", "")).strip()
        if result:
            if task.task_type == "differentiate":
                lines.append(
                    _display_math(f"d/d{task.variable}({task.expression}) = {result}")
                )
            elif task.task_type == "integrate":
                lines.append(
                    _display_math(
                        f"Integral({task.expression}, d{task.variable}) = {result} + C"
                    )
                )
            else:
                lines.append(_display_math(f"{task.expression} = {result}"))
        return lines

    lines.append("No symbolic target available.")
    return lines


def _render_numerical_teach(task: TaskSpec, sympy_out: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## Numerical Checks"]
    status = str(sympy_out.get("status", "")).strip().lower()
    if status != "ok":
        lines.append(
            "Symbolic stage did not complete; no numerical checks were computed."
        )
        return lines

    if task.task_type == "solve":
        sols = [str(s) for s in sympy_out.get("solutions", []) if str(s).strip()]
        residual_abs = sympy_out.get("residual_abs", [])
        if sols:
            for i, sol in enumerate(sols, 1):
                approx = _numeric_approx(sol)
                if approx is not None:
                    lines.append(f"- Root {i}: `{approx}`")
                else:
                    lines.append(f"- Root {i}: symbolic (`{sol}`)")
        if residual_abs:
            lines.append(f"- Residual abs values: `{residual_abs}`")
        return lines

    if task.task_type == "ode":
        particulars = [
            p for p in sympy_out.get("particular_solutions", []) if isinstance(p, dict)
        ]
        if particulars:
            for p in particulars:
                cond = str(p.get("condition", "")).strip()
                ok = bool(p.get("residual_exact_ok", False))
                residual = str(p.get("residual", "")).strip()
                label = cond or "initial condition"
                lines.append(
                    f"- {label}: residual `{residual or 'n/a'}` -> "
                    f"`{'pass' if ok else 'check'}`"
                )
            return lines
        flags = sympy_out.get("residual_exact_ok", [])
        if flags:
            lines.append(f"- General ODE residual flags: `{flags}`")
        else:
            lines.append("No initial-condition numerical checks were detected.")
        return lines

    if task.task_type in {"simplify", "differentiate", "integrate"}:
        if task.task_type == "integrate":
            lines.append(
                f"- Derivative check: `{sympy_out.get('derivative_check', False)}`"
            )
        elif task.task_type == "differentiate":
            lines.append(
                f"- Derivative identity check: `{sympy_out.get('derivative_check', False)}`"
            )
        else:
            lines.append(f"- Equivalence check: `{sympy_out.get('equivalent', False)}`")
        return lines

    lines.append("No numerical checks available for this task type.")
    return lines


def _render_graphical_teach(graph: dict[str, Any]) -> list[str]:
    lines: list[str] = ["## Graphical Solution"]
    if not graph.get("enabled"):
        lines.append(f"Graph stage skipped: {graph.get('reason', 'not generated')}")
        return lines
    desmos = graph.get("desmos", {}) if isinstance(graph.get("desmos"), dict) else {}
    url = str(desmos.get("url", "")).strip() or "https://www.desmos.com/calculator"
    lines.append(f"- Desmos URL: {url}")
    expressions = [str(x) for x in desmos.get("expressions", []) if str(x).strip()]
    if expressions:
        lines += ["```text", *expressions, "```"]
    points = desmos.get("points", [])
    if points:
        lines.append(f"- Key points: `{points}`")
    return lines


@dataclass
class RuntimeOptions:
    output_mode: str
    enable_vision: bool
    enable_lean: bool
    enable_sympy: bool
    enable_verify: bool
    enable_graph: bool
    enable_tools: bool
    enable_wolfram: bool
    embed_graph_artifact: bool
    show_trace: bool


def _task_summary(task: TaskSpec) -> str:
    if task.task_type == "solve":
        return f"Solve {task.lhs} = {task.rhs} for {task.variable}"
    if task.task_type in {"simplify", "differentiate", "integrate"}:
        return f"{task.task_type.title()} {task.expression} with respect to {task.variable}"
    if task.task_type == "ode":
        return f"Solve ODE residual {task.expression} = 0 over {task.variable}"
    return task.expression


def _vision_symbolic_candidate(vision: dict[str, Any] | None) -> str:
    if not isinstance(vision, dict):
        return ""
    text_blocks = [
        str(vision.get("normalized_problem", "")).strip(),
        str(vision.get("transcription", "")).strip(),
    ]
    text = "\n".join(x for x in text_blocks if x).strip()
    if not text:
        return ""

    lines = [x.strip() for x in text.splitlines() if x.strip()]
    candidates: list[tuple[int, str]] = []
    for line in lines:
        low = line.lower()
        score = 0
        if "=" in line:
            score += 2
        if "dy" in low or "y'" in low or "/dx" in low or "d/d" in low:
            score += 4
        if any(tok in low for tok in ["sin", "cos", "tan", "sqrt", "pi"]):
            score += 2
        if re.search(r"\d", line):
            score += 1
        if re.search(r"[+\-*/^()]", line):
            score += 1
        if score > 0:
            candidates.append((score, line))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0][1]
    return best if "=" in best else ""


def _image_explain_fallback(vision: dict[str, Any] | None) -> str:
    if not isinstance(vision, dict):
        return (
            "I received an image prompt but did not get usable symbolic extraction. "
            "Attach a clearer crop or include the equation text in the message."
        )

    note = str(vision.get("note", "")).strip()
    normalized = str(vision.get("normalized_problem", "")).strip()
    transcription = str(vision.get("transcription", "")).strip()
    candidate = _vision_symbolic_candidate(vision)

    if candidate:
        return (
            "I extracted image text but could not safely map it to a symbolic task in this turn. "
            f"Detected candidate: `{candidate}`. "
            "Retry with that equation pasted directly so Lean/SymPy/graphs can run."
        )
    if normalized or transcription:
        excerpt = (normalized or transcription).replace("\n", " ").strip()
        if len(excerpt) > 220:
            excerpt = excerpt[:220].rstrip() + "..."
        return (
            "I read the image text, but it did not contain one safe symbolic target. "
            f"Extracted text: `{excerpt}`"
        )
    if note:
        return (
            "I could not extract usable symbolic content from the image. "
            f"Vision note: {note}"
        )
    return (
        "I could not extract usable symbolic content from the image. "
        "Please crop the equation region or add the equation text."
    )


def _render_inline_graph_artifact(graph: dict[str, Any], enabled: bool) -> str:
    if not enabled or not graph.get("enabled"):
        return ""
    desmos = graph.get("desmos", {})
    url = str(desmos.get("url", "")).strip() or "https://www.desmos.com/calculator"
    clip = str(desmos.get("clipboard_text", "")).strip()
    lines = [
        "## Inline Graph",
        '<iframe src="'
        + escape(url, quote=True)
        + '" width="100%" height="420"></iframe>',
    ]
    if clip:
        lines += ["", "```text", clip, "```"]
    return "\n".join(lines).strip()


def _fallback_conversation(task: TaskSpec, sympy_out: dict[str, Any]) -> str:
    status = str(sympy_out.get("status", "")).strip().lower()
    if status == "error":
        return str(sympy_out.get("message", "SymPy execution failed."))
    if status == "skipped":
        return str(
            sympy_out.get(
                "message",
                (
                    "Symbolic layer is disabled for this run. "
                    "Enable `sympy=on` to compute symbolic steps."
                ),
            )
        )

    t = task.task_type
    if t == "solve":
        sols = sympy_out.get("solutions", [])
        if not sols:
            return "No solution was found in the current symbolic domain."
        if len(sols) == 1:
            return _display_math(f"{task.variable} = {sols[0]}")
        lines = [_display_math(f"{task.variable} = {s}") for s in sols]
        return "\n\n".join(lines)
    if t == "simplify":
        result = str(sympy_out.get("result", ""))
        return _display_math(result) if result else result
    if t == "differentiate":
        result = str(sympy_out.get("result", ""))
        return _display_math(result) if result else result
    if t == "integrate":
        result = str(sympy_out.get("result", ""))
        return _display_math(f"{result} + C") if result else "C"
    if t == "ode":
        particulars = [
            p
            for p in sympy_out.get("particular_solutions", [])
            if isinstance(p, dict) and str(p.get("solution", "")).strip()
        ]
        if particulars:
            lines: list[str] = []
            for p in particulars:
                cond = str(p.get("condition", "")).strip()
                if cond:
                    lines.append(f"Condition: {cond}")
                lines.append(
                    _display_math(f"y({task.variable}) = {str(p['solution'])}")
                )
            return "\n\n".join(lines)
        sols = sympy_out.get("solutions", [])
        if not sols:
            return "No closed-form ODE solution was produced by the symbolic layer."
        if len(sols) == 1:
            return _display_math(f"y({task.variable}) = {sols[0]}")
        lines = [_display_math(f"y({task.variable}) = {s}") for s in sols[:3]]
        return "\n\n".join(lines)
    expr_text = task.expression.strip()
    explicit_msg = str(sympy_out.get("message", "")).strip()
    if explicit_msg:
        return explicit_msg
    if expr_text and len(expr_text) > 20:
        excerpt = expr_text[:200] + ("..." if len(expr_text) > 200 else "")
        return (
            f"I received your input but could not extract a single symbolic target.\n\n"
            f"**Detected text:** `{excerpt}`\n\n"
            "Try providing the specific equation, or prefix with "
            "`solve`, `integrate`, `differentiate`, `simplify`, or write an ODE as `dy/dx = ...`"
        )
    return (
        "I can solve equations, simplify, differentiate, integrate, and solve ODEs.\n\n"
        "Provide the equation directly (e.g., `x^2 - 4 = 0`) or use keywords like "
        "`solve`, `integrate`, `differentiate`, or `dy/dx = ...`"
    )


def _vision_access_hint(vision: dict[str, Any] | None) -> str | None:
    if not isinstance(vision, dict):
        return None
    note = str(vision.get("note", "")).strip()
    if not note:
        return None
    low = note.lower()
    if "no accessible image" in low or "local image fetch failed" in low:
        return (
            "I received an image reference but could not access its bytes for vision parsing. "
            "In OpenWebUI, use a public/data image URL or include extracted text with the image."
        )
    return None


def _is_math_mode(task: TaskSpec) -> bool:
    return task.task_type in {"solve", "simplify", "differentiate", "integrate", "ode"}


def _is_noisy_non_symbolic(task: TaskSpec) -> bool:
    payload = " ".join(
        x
        for x in [task.expression, task.lhs, task.rhs]
        if isinstance(x, str) and x.strip()
    )
    low = payload.lower()
    markers = [
        "####",
        "tools available",
        "code_interpreter",
        "tool calls",
        "assistant",
        "http://",
        "https://",
        "```",
    ]
    if any(m in low for m in markers):
        return True
    if payload.count("\n") >= 3 and not any(op in payload for op in "=+-*/^()"):
        return True
    if len(payload) > 260 and not any(op in payload for op in "=+-*/^()"):
        return True
    op_count = len(re.findall(r"[=+\-*/^()]", payload))
    alpha_tokens = re.findall(r"[A-Za-z]{3,}", payload)
    if len(alpha_tokens) >= 22 and op_count <= 3:
        return True
    if (
        task.task_type == "solve"
        and len(payload) >= 120
        and payload.count("=") <= 1
        and op_count <= 4
    ):
        return True
    if re.search(r"[A-Za-z]{4,}\s+[A-Za-z]{4,}\s+[A-Za-z]{4,}\s+[A-Za-z]{4,}", payload):
        if task.task_type in {"solve", "simplify", "differentiate", "integrate"}:
            return True
    return False


def _is_generic_solver_prompt(text: str) -> bool:
    low = text.strip().lower()
    if not low:
        return True
    if any(op in low for op in "=+-*/^()"):
        return False
    generic_markers = [
        "how to solve",
        "solve this",
        "can you solve",
        "help me solve",
        "what is the answer",
        "how do i do this",
    ]
    return any(m in low for m in generic_markers) or len(low) <= 24


def _downgrade_to_explain(task: TaskSpec, question: str, reason: str) -> TaskSpec:
    return TaskSpec(
        task_type="explain",
        expression=question.strip(),
        variable=task.variable or "x",
        domain=task.domain or "unspecified",
        assumptions=task.assumptions or [],
        reasoning=reason,
    )


def _render_trace(trace: list[NodeTrace]) -> list[str]:
    lines: list[str] = []
    for i, node in enumerate(trace, 1):
        lines.append(f"- {i}. `{node.node}` -> `{node.status}`: {node.summary}")
    return lines


def _parse_bool(v: str) -> bool | None:
    x = v.strip().lower()
    if x in _BOOL_TRUE:
        return True
    if x in _BOOL_FALSE:
        return False
    return None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    parsed = _parse_bool(raw)
    return default if parsed is None else parsed


def _default_runtime_options() -> RuntimeOptions:
    output_mode = os.getenv("TB_OUTPUT_MODE", "answer").strip().lower()
    if output_mode not in _MODES:
        output_mode = "answer"
    return RuntimeOptions(
        output_mode=output_mode,
        enable_vision=_env_bool("TB_ENABLE_VISION", True),
        enable_lean=_env_bool("TB_ENABLE_LEAN", True),
        enable_sympy=_env_bool("TB_ENABLE_SYMPY", True),
        enable_verify=_env_bool("TB_ENABLE_VERIFY", True),
        enable_graph=_env_bool("TB_ENABLE_GRAPH", True),
        enable_tools=_env_bool("TB_ENABLE_TOOLS", True),
        enable_wolfram=_env_bool("TB_ENABLE_WOLFRAM", True),
        embed_graph_artifact=_env_bool("TB_EMBED_GRAPH_ARTIFACT", True),
        show_trace=_env_bool("TB_SHOW_TRACE", False),
    )


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        x = float(raw)
        return x if x > 0 else default
    except Exception:
        return default


def _auto_mode_from_question(question: str) -> str | None:
    low = question.strip().lower()
    if not low:
        return None

    evidence_markers = [
        "show evidence",
        "proof mode",
        "show proof",
        "show lean",
        "show sympy",
        "show desmos",
        "node trace",
        "verification details",
    ]
    if any(m in low for m in evidence_markers):
        return "evidence"
    if all(m in low for m in ["lean", "sympy"]):
        return "evidence"

    teach_markers = [
        "how to solve",
        "teach me",
        "step by step",
        "from zero",
        "zero knowledge",
        "beginner",
        "explain like",
    ]
    if any(m in low for m in teach_markers):
        return "teach"
    return None


def _extract_runtime_options(question: str) -> tuple[str, RuntimeOptions]:
    opts = _default_runtime_options()
    q = question or ""
    directive_blocks: list[str] = []
    mode_overridden = False

    for m in re.finditer(r"\[tb:(.*?)\]", q, flags=re.IGNORECASE | re.DOTALL):
        directive_blocks.append(m.group(1))
    q = re.sub(r"\[tb:.*?\]", " ", q, flags=re.IGNORECASE | re.DOTALL)

    kept_lines: list[str] = []
    for line in q.splitlines():
        s = line.strip()
        if s.lower().startswith("/tb"):
            directive_blocks.append(s[3:].strip())
            continue
        kept_lines.append(line)
    cleaned = "\n".join(kept_lines).strip()

    if not directive_blocks:
        if opts.output_mode == "answer":
            inferred = _auto_mode_from_question(cleaned)
            if inferred in _MODES:
                opts.output_mode = inferred
        return cleaned, opts

    kv_re = re.compile(r"([a-z_]+)\s*=\s*([^\s,;]+)", flags=re.IGNORECASE)
    for block in directive_blocks:
        for key, value in kv_re.findall(block):
            k = key.strip().lower()
            v = value.strip().lower()
            if k in {"mode", "output"}:
                if v in _MODES:
                    opts.output_mode = v
                    mode_overridden = True
                continue
            b = _parse_bool(v)
            if b is None:
                continue
            if k == "vision":
                opts.enable_vision = b
            elif k == "lean":
                opts.enable_lean = b
            elif k == "sympy":
                opts.enable_sympy = b
            elif k == "verify":
                opts.enable_verify = b
            elif k == "graph":
                opts.enable_graph = b
            elif k == "tools":
                opts.enable_tools = b
            elif k == "wolfram":
                opts.enable_wolfram = b
            elif k == "trace":
                opts.show_trace = b

    if not mode_overridden and opts.output_mode == "answer":
        inferred = _auto_mode_from_question(cleaned)
        if inferred in _MODES:
            opts.output_mode = inferred

    return cleaned, opts


def _render_evidence(
    task: TaskSpec,
    lean_first_out: dict[str, Any],
    sympy_out: dict[str, Any],
    verification: dict[str, Any],
    graph: dict[str, Any],
    verdict: dict[str, Any],
    conversational: str,
    trace: list[NodeTrace],
    vision: dict[str, Any] | None,
    tool_out: dict[str, Any],
    opts: RuntimeOptions,
) -> str:
    assumptions = task.assumptions or []
    lean_verify = verification.get("lean_verify")
    lines = [
        "## Final Answer",
        conversational,
        "",
        f"- Verdict: `{verdict.get('verdict', 'partial')}`",
        f"- Confidence: `{verdict.get('confidence', 0.0)}`",
        "",
        "## Runtime Layers",
        f"- mode: `{opts.output_mode}`",
        f"- vision: `{opts.enable_vision}`",
        f"- lean: `{opts.enable_lean}`",
        f"- sympy: `{opts.enable_sympy}`",
        f"- verify: `{opts.enable_verify}`",
        f"- graph: `{opts.enable_graph}`",
        f"- tools: `{opts.enable_tools}`",
        f"- wolfram: `{opts.enable_wolfram}`",
    ]

    lines += ["", "## Tool Layer"]
    lines.append(f"- Tool stage status: `{tool_out.get('status', 'skipped')}`")
    if tool_out.get("selected"):
        lines.append(f"- Selected tool path: `{tool_out.get('selected')}`")
    if tool_out.get("tool_calls"):
        lines.append(f"- Tool calls: `{tool_out.get('tool_calls')}`")
    for note in tool_out.get("notes", []):
        lines.append(f"- Note: {note}")
    wolfram = tool_out.get("wolfram")
    if isinstance(wolfram, dict) and wolfram.get("status") in {"ok", "partial"}:
        lines.append(f"- Wolfram status: `{wolfram.get('status')}`")
        pods = wolfram.get("pods", []) or []
        for pod in pods[:3]:
            if not isinstance(pod, dict):
                continue
            title = str(pod.get("title", "Result")).strip()
            texts = pod.get("plaintext", []) or []
            if texts:
                lines.append(f"- Wolfram {title}: `{texts[0]}`")

    lines += ["", "## LEAN Layer"]
    lines.append(f"- Parsed task: `{_task_summary(task)}`")
    lines.append(f"- Domain: `{task.domain}`")
    lines.append(
        f"- Assumptions: `{assumptions if assumptions else ['none provided']}`"
    )
    lines.append(
        f"- Lean formalization status: `{lean_first_out.get('status', 'unknown')}`"
    )
    if lean_first_out.get("reason"):
        lines.append(f"- Lean note: {lean_first_out.get('reason')}")
    if lean_first_out.get("code"):
        lines += ["```lean", str(lean_first_out.get("code", "")).strip(), "```"]

    lines += ["", "## SymPy Layer"]
    lines.append(f"- Stage status: `{sympy_out.get('status', 'skipped')}`")
    for step in sympy_out.get("steps", []):
        lines.append(f"- {step}")
    if sympy_out.get("message"):
        lines.append(f"- Message: {sympy_out.get('message')}")

    lines += ["", "## Verification Layer"]
    for item in verification.get("items", []):
        lines.append(f"- {item}")
    if verdict.get("issues"):
        lines.append(f"- Issues: `{verdict.get('issues')}`")
    if verdict.get("missing_proofs"):
        lines.append(f"- Missing proofs: `{verdict.get('missing_proofs')}`")
    if verdict.get("next_checks"):
        lines.append(f"- Next checks: `{verdict.get('next_checks')}`")
    if isinstance(lean_verify, dict) and lean_verify.get("code"):
        lines += ["```lean", str(lean_verify["code"]).strip(), "```"]

    lines += ["", "## Graph Layer"]
    if graph.get("enabled"):
        desmos = graph.get("desmos", {})
        lines.append(f"- Tool calls: `{graph.get('tool_calls', [])}`")
        lines.append(f"- Desmos URL: {desmos.get('url', '')}")
        for expr in desmos.get("expressions", []):
            lines.append(f"- Desmos expression: `{expr}`")
        if desmos.get("points"):
            lines.append(f"- Key points: `{desmos.get('points')}`")
        if desmos.get("clipboard_text"):
            lines += [
                "- Desmos paste block:",
                "```text",
                str(desmos.get("clipboard_text", "")).strip(),
                "```",
            ]
    else:
        lines.append(f"- Graph note: {graph.get('reason', 'graph stage skipped')}")

    lines += ["", "## Vision Layer"]
    if vision:
        lines.append(f"- Vision status: `{vision.get('status', 'unknown')}`")
        if vision.get("normalized_problem"):
            lines.append(
                f"- Image-normalized problem: `{vision.get('normalized_problem')}`"
            )
        if vision.get("note"):
            lines.append(f"- Vision note: {vision.get('note')}")
    else:
        lines.append("- No image input provided.")

    if opts.show_trace:
        lines += ["", "## Node Trace", *_render_trace(trace)]
        lines += [
            "",
            "```json",
            json.dumps([t.__dict__ for t in trace], ensure_ascii=True),
            "```",
        ]
    return "\n".join(lines)


def _render_teach(
    task: TaskSpec,
    sympy_out: dict[str, Any],
    lean_first_out: dict[str, Any],
    graph: dict[str, Any],
    verdict: dict[str, Any],
    tool_out: dict[str, Any],
    conversational: str,
) -> str:
    lines = ["## Final Answer", conversational]
    if not _is_math_mode(task):
        lines += ["", "## Atomic Walkthrough"]
        expr = task.expression.strip()
        if tool_out.get("selected") == "wolfram_alpha":
            lines.append(
                "1. Wolfram Alpha processed this query -- use its result as a starting point."
            )
            lines.append(
                "2. Restate the specific equation for Lean + SymPy verification."
            )
            return "\n".join(lines)
        if expr and len(expr) > 20:
            excerpt = expr[:200] + ("..." if len(expr) > 200 else "")
            lines.append(f"1. **Input received:** `{excerpt}`")
            lines.append("2. Could not map this to a single symbolic operation.")
            lines.append("3. Try providing one explicit target equation, such as:")
            lines.append("4. ODE format:")
            lines.append(_display_math("dy/dx = y**2*sin(x)"))
            lines.append("5. Algebra format:")
            lines.append(_display_math("x**2 - 4 = 0"))
            lines.append("6. Calculus format:")
            lines.append(_display_math("Integral(sin(x), dx)"))
        else:
            lines.append("1. Write the equation explicitly.")
            lines.append("2. Example:")
            lines.append(_display_math("lhs = rhs"))
            lines.append("3. Include domain or constraints if relevant.")
            lines.append("4. Use `solve`, `integrate`, `differentiate`, or `simplify`.")
            lines.append("5. For ODEs, write:")
            lines.append(_display_math("dy/dx = ..."))
        return "\n".join(lines)

    lines += ["", *_render_symbolic_teach(task, sympy_out)]
    lines += ["", *_render_numerical_teach(task, sympy_out)]
    lines += ["", *_render_graphical_teach(graph)]
    lines += ["", "## Atomic Walkthrough"]
    lines.append("1. Parse the task and domain.")
    lines.append(
        "2. Convert the problem to a symbolic target and run SymPy for exact forms."
    )
    lines.append("3. Run residual checks for numerical consistency.")
    lines.append(
        f"4. Lean formalization status: `{lean_first_out.get('status', 'skipped')}`."
    )
    lines.append(f"5. Overall verdict: `{verdict.get('verdict', 'partial')}`.")
    lines.append("6. Build graph artifacts from symbolic outputs.")

    lines += ["", "## Parsed Inputs"]
    lines.append(f"- Task type: `{task.task_type}`")
    lines.append(f"- Variable: `{task.variable}`")
    lines.append(f"- Domain: `{task.domain}`")
    assumptions = task.assumptions or []
    if assumptions:
        lines.append(f"- Assumptions: `{assumptions}`")
    else:
        lines.append("- Assumptions: `none provided`")

    lines += ["", "## SymPy Steps"]
    for step in sympy_out.get("steps", []):
        lines.append(f"- {step}")
    lines += [
        "",
        "## Checkpoint",
        f"Can you verify the solution by substituting back into the original equation?",
    ]
    return "\n".join(lines)


def _verification_without_verifier(sympy_out: dict[str, Any]) -> dict[str, Any]:
    status = str(sympy_out.get("status", "skipped"))
    if status == "ok":
        return {
            "verdict": "partial",
            "confidence": 0.72,
            "issues": [],
            "accepted_claims": ["Symbolic layer completed."],
            "missing_proofs": ["Verification layer was disabled."],
            "next_checks": ["Set `verify=on` for strict residual and proof checks."],
        }
    if status == "error":
        return {
            "verdict": "fail",
            "confidence": 0.2,
            "issues": [str(sympy_out.get("message", "Symbolic stage failed."))],
            "accepted_claims": [],
            "missing_proofs": ["Verification layer was disabled."],
            "next_checks": ["Fix symbolic parse and rerun with `verify=on`."],
        }
    return {
        "verdict": "partial",
        "confidence": 0.4,
        "issues": ["No symbolic verification was run."],
        "accepted_claims": [],
        "missing_proofs": ["Verification layer was disabled."],
        "next_checks": [
            "Enable symbolic and verification layers for math-proof output."
        ],
    }


def _adapt_word_problem_tool(tool_out: dict[str, Any]) -> dict[str, Any] | None:
    if str(tool_out.get("selected", "")) != "inclined_plane_friction_solver":
        return None
    payload = tool_out.get("word_problem")
    if not isinstance(payload, dict):
        return None

    params = (
        payload.get("parameters", {})
        if isinstance(payload.get("parameters"), dict)
        else {}
    )
    mu = params.get("mu")
    angle_deg = params.get("angle_deg")
    length_m = params.get("length_m")
    v0 = params.get("v0")
    g = params.get("g", 9.81)
    rhs = ""
    if all(x is not None for x in [mu, angle_deg, length_m, v0, g]):
        rhs = (
            f"{float(v0)}**2 + 2*{float(g)}*(sin({float(angle_deg)}*pi/180)"
            f"-{float(mu)}*cos({float(angle_deg)}*pi/180))*{float(length_m)}"
        )

    task = TaskSpec(
        task_type="solve",
        lhs="v**2",
        rhs=rhs or "0",
        variable="v",
        domain="real",
        assumptions=["v >= 0"],
        reasoning="tool_inclined_plane_friction",
    )

    sym = payload.get("sympy", {}) if isinstance(payload.get("sympy"), dict) else {}
    result = str(sym.get("result", "")).strip()
    steps = [str(s) for s in sym.get("steps", []) if str(s).strip()]
    if steps:
        steps.append("Applied physical assumption filter: v >= 0.")
    sympy_out = {
        "status": "ok",
        "task_type": "solve",
        "variable": "v",
        "equation": f"Eq(v**2, {task.rhs})",
        "solutions": [result] if result else [],
        "raw_solutions": ([f"-({result})", result] if result else []),
        "residuals": (["0"] if result else []),
        "residual_exact_ok": ([True] if result else []),
        "residual_abs": ([0.0] if result else []),
        "steps": steps,
        "message": "Solved using deterministic open-source incline-friction tool.",
    }

    lean = payload.get("lean", {}) if isinstance(payload.get("lean"), dict) else {}
    graph = payload.get("graph", {}) if isinstance(payload.get("graph"), dict) else {}
    verification_items = [
        str(x) for x in payload.get("verification_items", []) if str(x).strip()
    ]
    verdict = (
        payload.get("verdict", {}) if isinstance(payload.get("verdict"), dict) else {}
    )
    answer = str(payload.get("answer", "")).strip()
    lean_verify = {
        "status": str(lean.get("status", "unknown")),
        "checks": [{"solution": "v", "status": str(lean.get("status", "unknown"))}],
        "code": lean.get("code", ""),
    }
    return {
        "task": task,
        "sympy": sympy_out,
        "lean_first": lean,
        "lean_verify": lean_verify,
        "graph": graph,
        "verification_items": verification_items,
        "verdict": verdict,
        "answer": answer,
    }


def _wolfram_fallback_conversation(tool_out: dict[str, Any]) -> str | None:
    wolfram = tool_out.get("wolfram")
    if not isinstance(wolfram, dict):
        return None
    if str(wolfram.get("status", "")) not in {"ok", "partial"}:
        return None
    pods = wolfram.get("pods", [])
    if isinstance(pods, list):
        for pod in pods:
            if not isinstance(pod, dict):
                continue
            title = str(pod.get("title", "Result")).strip() or "Result"
            texts = pod.get("plaintext", [])
            if isinstance(texts, list):
                for t in texts:
                    x = str(t).strip()
                    if x:
                        return f"Wolfram fallback ({title}): {x}"
    suggestions = wolfram.get("suggestions", [])
    if isinstance(suggestions, list) and suggestions:
        first = str(suggestions[0]).strip()
        if first:
            return f"Wolfram could not resolve the query cleanly. Try: {first}"
    reason = str(wolfram.get("reason", "")).strip()
    return reason or None


async def run_tutor_stream(
    question: str,
    image_urls: list[str] | None = None,
    forward_headers: dict[str, str] | None = None,
) -> AsyncGenerator[str | TutorResult, None]:
    trace: list[NodeTrace] = []
    raw_question = question.strip()
    cleaned_question, opts = _extract_runtime_options(raw_question)
    merged_question = cleaned_question

    vision_out: dict[str, Any] | None = None
    if image_urls and opts.enable_vision:
        yield "> **Reading image** -- extracting math content...\n\n"
        vision_timeout = _env_float("TB_VISION_TIMEOUT_SECONDS", 45.0)
        retry_default = max(90.0, vision_timeout * 2.0)
        vision_retry_timeout = _env_float(
            "TB_VISION_RETRY_TIMEOUT_SECONDS", retry_default
        )
        vision_raw: dict[str, Any] | None = None
        try:
            vision_raw = await wait_for(
                glm_extract_from_images(
                    image_urls,
                    user_text=cleaned_question,
                    forward_headers=forward_headers,
                ),
                timeout=vision_timeout,
            )
        except TimeoutError:
            yield (
                f"> **Vision:** initial extraction timed out after {vision_timeout:.1f}s "
                " -- retrying with extended timeout...\n\n"
            )
            try:
                vision_raw = await wait_for(
                    glm_extract_from_images(
                        image_urls,
                        user_text=cleaned_question,
                        forward_headers=forward_headers,
                    ),
                    timeout=vision_retry_timeout,
                )
            except TimeoutError:
                vision_raw = {
                    "status": "partial",
                    "normalized_problem": "",
                    "transcription": "",
                    "hints": [],
                    "confidence": 0.0,
                    "note": (
                        "Vision extraction timed out after "
                        f"{vision_timeout:.1f}s and retry "
                        f"{vision_retry_timeout:.1f}s."
                    ),
                }
        if vision_raw:
            normalized = str(vision_raw.get("normalized_problem", "")).strip()
            transcription = str(vision_raw.get("transcription", "")).strip()
            vision_note = str(vision_raw.get("note", "")).strip()
            pick = normalized or transcription
            if pick:
                if cleaned_question and not _is_generic_solver_prompt(cleaned_question):
                    merged_question = (
                        f"{cleaned_question}\n\n[Image extracted math]\n{pick}"
                    ).strip()
                else:
                    merged_question = pick
            vision_out = {
                "status": ("ok" if pick else "partial"),
                "normalized_problem": normalized,
                "transcription": transcription,
                "hints": vision_raw.get("hints", []),
                "confidence": vision_raw.get("confidence", 0.0),
            }
            if vision_note:
                vision_out["note"] = vision_note
            if pick:
                pick_preview = pick[:150] + ("..." if len(pick) > 150 else "")
                yield f"> **Extracted:** `{pick_preview}`\n\n"
            trace.append(
                NodeTrace(
                    node="ingest",
                    status=("ok" if pick else "partial"),
                    summary=(
                        "Text + image were merged for symbolic parsing."
                        if pick
                        else "Image was received but no parseable math was extracted."
                    ),
                    payload={
                        "image_count": len(image_urls),
                        "normalized_problem": normalized,
                        "note": vision_note,
                    },
                )
            )
        else:
            vision_out = {
                "status": "partial",
                "normalized_problem": "",
                "transcription": "",
                "hints": [],
                "confidence": 0.0,
                "note": "Image input received but no structured vision extraction.",
                "image_count": len(image_urls),
            }
            trace.append(
                NodeTrace(
                    node="ingest",
                    status="partial",
                    summary="Image input received but no structured vision extraction.",
                    payload={"image_count": len(image_urls)},
                )
            )
    elif image_urls and not opts.enable_vision:
        vision_out = {
            "status": "skipped",
            "normalized_problem": "",
            "transcription": "",
            "hints": [],
            "confidence": 0.0,
            "note": "Vision layer disabled by runtime options.",
            "image_count": len(image_urls),
        }
        trace.append(
            NodeTrace(
                node="ingest",
                status="partial",
                summary="Image received but vision layer is disabled.",
                payload={"image_count": len(image_urls)},
            )
        )
    else:
        trace.append(
            NodeTrace(
                node="ingest",
                status="ok",
                summary="Text-only input path.",
                payload={"image_count": 0},
            )
        )

    parse_input = (
        merged_question.strip() or cleaned_question.strip() or raw_question.strip()
    )
    if not parse_input:
        parse_input = (
            "Solve the attached math problem."
            if image_urls
            else "Please help with math."
        )
    parse_timeout = _env_float("TB_PARSE_TIMEOUT_SECONDS", 6.0)
    repair_timeout = _env_float("TB_REPAIR_TIMEOUT_SECONDS", 6.0)
    parse_status = "ok"
    parse_summary = ""
    try:
        task = await wait_for(parse_task(parse_input), timeout=parse_timeout)
        parse_summary = f"Parsed as {task.task_type}."
    except TimeoutError:
        task = TaskSpec(
            task_type="explain",
            expression=parse_input,
            variable="x",
            domain="unspecified",
            assumptions=[],
            reasoning=f"parse_timeout_{parse_timeout:.1f}s",
        )
        parse_status = "partial"
        parse_summary = f"Parser timed out after {parse_timeout:.1f}s; fell back to conversational mode."
    trace.append(
        NodeTrace(
            node="parse",
            status=parse_status,
            summary=parse_summary,
            payload={
                "task": task.task_type,
                "domain": task.domain,
                "variable": task.variable,
            },
        )
    )

    if image_urls and task.task_type == "explain":
        vision_candidate = _vision_symbolic_candidate(vision_out)
        if vision_candidate:
            try:
                reparsed = await wait_for(
                    parse_task(vision_candidate),
                    timeout=min(parse_timeout, 4.0),
                )
            except TimeoutError:
                reparsed = None
            if reparsed and _is_math_mode(reparsed):
                task = reparsed
                trace.append(
                    NodeTrace(
                        node="parse_vision",
                        status="ok",
                        summary="Promoted symbolic task from vision-derived equation candidate.",
                        payload={
                            "candidate": vision_candidate,
                            "task": task.task_type,
                            "variable": task.variable,
                        },
                    )
                )
            else:
                trace.append(
                    NodeTrace(
                        node="parse_vision",
                        status="partial",
                        summary="Vision candidate was found but symbolic parse remained non-math.",
                        payload={"candidate": vision_candidate},
                    )
                )

    if _is_math_mode(task):
        if task.task_type == "solve":
            eq_latex = f"{_to_latex(task.lhs)} = {_to_latex(task.rhs)}"
        elif task.task_type == "ode":
            eq_latex = f"{_to_latex(task.expression)} = 0"
        elif task.task_type in {"simplify", "differentiate", "integrate"}:
            eq_latex = _to_latex(task.expression)
        else:
            eq_latex = task.expression[:100]
        yield f"> **Parsed as** `{task.task_type}`:\n>\n> $$ {eq_latex} $$\n\n"

    tool_out: dict[str, Any] = {
        "status": "skipped",
        "selected": None,
        "tool_calls": [],
        "notes": [],
    }
    if opts.enable_tools:
        tool_timeout = _env_float("TB_TOOL_TIMEOUT_SECONDS", 10.0)
        wolfram_timeout = _env_float("TB_WOLFRAM_TIMEOUT_SECONDS", 7.0)
        try:
            tool_out = await wait_for(
                run_tool_layer(
                    parse_input,
                    enable_wolfram=opts.enable_wolfram,
                    wolfram_timeout_seconds=wolfram_timeout,
                ),
                timeout=tool_timeout,
            )
        except TimeoutError:
            tool_out = {
                "status": "partial",
                "selected": None,
                "tool_calls": [],
                "notes": [f"Tool layer timed out after {tool_timeout:.1f}s."],
            }
        tool_status = str(tool_out.get("status", "skipped"))
        trace.append(
            NodeTrace(
                node="tools",
                status=(
                    "ok"
                    if tool_status == "ok"
                    else ("partial" if tool_status == "partial" else "skipped")
                ),
                summary=(
                    f"Tool layer status: {tool_status}."
                    if tool_status != "skipped"
                    else "Tool layer skipped."
                ),
                payload={
                    "selected": tool_out.get("selected"),
                    "tool_calls": tool_out.get("tool_calls", []),
                },
            )
        )
    else:
        trace.append(
            NodeTrace(
                node="tools",
                status="skipped",
                summary="Tool layer disabled by runtime options.",
                payload={},
            )
        )

    tool_override = _adapt_word_problem_tool(tool_out)
    if tool_override:
        task = tool_override["task"]
        yield "> **Recognized** physics word problem -- using specialized solver\n\n"
        trace.append(
            NodeTrace(
                node="tool_promote",
                status="ok",
                summary="Tool layer promoted prompt to symbolic incline-friction solve flow.",
                payload={"task": task.task_type, "variable": task.variable},
            )
        )

    needs_symbolic_preflight = opts.enable_lean or opts.enable_sympy
    if (
        _is_math_mode(task)
        and needs_symbolic_preflight
        and task.task_type != "ode"
        and not tool_override
    ):
        if _is_noisy_non_symbolic(task):
            task = _downgrade_to_explain(
                task, parse_input, "sanitize_non_symbolic_payload"
            )
            trace.append(
                NodeTrace(
                    node="sanitize",
                    status="partial",
                    summary="Noisy non-symbolic payload; downgraded to conversational mode.",
                    payload={"task_type": "explain"},
                )
            )
        else:
            try:
                parse_for_lean(task)
            except Exception as e:
                try:
                    repaired = await wait_for(
                        repair_task(
                            parse_input,
                            task,
                            f"Preflight symbolic parse failed: {e}",
                        ),
                        timeout=repair_timeout,
                    )
                except TimeoutError:
                    repaired = None
                    trace.append(
                        NodeTrace(
                            node="repair",
                            status="partial",
                            summary=f"Repair stage timed out after {repair_timeout:.1f}s.",
                            payload={"reason": "preflight_repair_timeout"},
                        )
                    )
                if repaired:
                    try:
                        parse_for_lean(repaired)
                        task = repaired
                        trace.append(
                            NodeTrace(
                                node="repair",
                                status="ok",
                                summary="Task repaired after symbolic preflight failure.",
                                payload={
                                    "task": task.task_type,
                                    "variable": task.variable,
                                    "reasoning": task.reasoning,
                                },
                            )
                        )
                    except Exception as e2:
                        task = _downgrade_to_explain(
                            task,
                            parse_input,
                            f"repair_preflight_failed: {e2}",
                        )
                        trace.append(
                            NodeTrace(
                                node="sanitize",
                                status="partial",
                                summary="Invalid symbolic parse; downgraded to conversational mode.",
                                payload={"reason": str(e2)},
                            )
                        )
                else:
                    task = _downgrade_to_explain(
                        task, parse_input, f"preflight_failed: {e}"
                    )
                    trace.append(
                        NodeTrace(
                            node="sanitize",
                            status="partial",
                            summary="Invalid symbolic parse; downgraded to conversational mode.",
                            payload={"reason": str(e)},
                        )
                    )

    lean_first_out: dict[str, Any] = {
        "supported": False,
        "status": "skipped",
        "reason": "Lean layer disabled by runtime options.",
    }
    sympy_out: dict[str, Any] = {
        "status": "skipped",
        "task_type": task.task_type,
        "message": "SymPy layer disabled by runtime options.",
        "steps": ["No symbolic action executed."],
    }
    lean_expr: Expr | None = None
    conversational_override = ""
    if tool_override:
        sympy_out = tool_override["sympy"]
        lean_first_out = tool_override["lean_first"]
        conversational_override = str(tool_override.get("answer", "")).strip()

    if tool_override:
        # Symbolic output already produced by tool layer.
        pass
    elif opts.enable_sympy:
        attempt = 0
        max_attempts = 2
        while attempt < max_attempts:
            attempt += 1

            lean_parse_error = ""
            lean_expr = None
            try:
                if task.task_type == "solve":
                    lhs, rhs, _ = parse_for_lean(task)
                    lean_expr = lhs - rhs
                elif task.task_type in {"simplify", "differentiate", "integrate"}:
                    expr, _, _ = parse_for_lean(task)
                    lean_expr = expr
            except Exception as e:
                lean_parse_error = str(e)

            if opts.enable_lean:
                if attempt == 1 and _is_math_mode(task):
                    yield "> **Lean-first** -- formalizing expression...\n\n"
                if task.task_type == "ode":
                    lean_first_out = {
                        "supported": False,
                        "status": "unsupported",
                        "reason": "ODE Lean bridge is not implemented yet.",
                    }
                elif lean_parse_error:
                    lean_first_out = {
                        "supported": False,
                        "status": "unsupported",
                        "reason": f"Lean parse bridge error: {lean_parse_error}",
                    }
                else:
                    lean_first_out = lean_first(task, lean_expr)
                lean_status = str(lean_first_out.get("status", "unknown"))
                if attempt == 1 and _is_math_mode(task):
                    yield f"> **Lean:** `{lean_status}`\n\n"
                trace.append(
                    NodeTrace(
                        node="lean_first",
                        status=("ok" if lean_status == "ok" else "partial"),
                        summary=f"Lean-first stage status: {lean_status}.",
                        payload={"status": lean_status, "attempt": attempt},
                    )
                )
            elif attempt == 1:
                trace.append(
                    NodeTrace(
                        node="lean_first",
                        status="skipped",
                        summary="Lean layer disabled by runtime options.",
                        payload={"status": "skipped"},
                    )
                )

            if attempt == 1 and _is_math_mode(task):
                yield f"> **SymPy** -- computing `{task.task_type}`...\n\n"
            sympy_out = run_sympy(task)
            sympy_status = str(sympy_out.get("status", "ok"))
            trace.append(
                NodeTrace(
                    node="sympy",
                    status=(
                        "ok"
                        if sympy_status == "ok"
                        else ("skipped" if sympy_status == "skipped" else "error")
                    ),
                    summary=(
                        "SymPy symbolic pass completed."
                        if sympy_status == "ok"
                        else (
                            "SymPy stage skipped."
                            if sympy_status == "skipped"
                            else "SymPy stage failed."
                        )
                    ),
                    payload={
                        "task_type": sympy_out.get("task_type"),
                        "result": sympy_out.get(
                            "result", sympy_out.get("solutions", [])
                        ),
                        "message": sympy_out.get("message", ""),
                        "attempt": attempt,
                    },
                )
            )

            if sympy_status != "error" or attempt >= max_attempts:
                break

            try:
                repaired = await wait_for(
                    repair_task(
                        parse_input,
                        task,
                        str(sympy_out.get("message", "unknown SymPy error")),
                    ),
                    timeout=repair_timeout,
                )
            except TimeoutError:
                repaired = None
                trace.append(
                    NodeTrace(
                        node="repair",
                        status="partial",
                        summary=f"Repair stage timed out after {repair_timeout:.1f}s.",
                        payload={"reason": "sympy_repair_timeout"},
                    )
                )
            if not repaired or repaired == task:
                break
            task = repaired
            trace.append(
                NodeTrace(
                    node="repair",
                    status="ok",
                    summary="Task was repaired after SymPy failure.",
                    payload={
                        "task": task.task_type,
                        "variable": task.variable,
                        "reasoning": task.reasoning,
                    },
                )
            )
    else:
        if opts.enable_lean:
            lean_parse_error = ""
            try:
                if task.task_type == "solve":
                    lhs, rhs, _ = parse_for_lean(task)
                    lean_expr = lhs - rhs
                elif task.task_type in {"simplify", "differentiate", "integrate"}:
                    expr, _, _ = parse_for_lean(task)
                    lean_expr = expr
            except Exception as e:
                lean_parse_error = str(e)
            if task.task_type == "ode":
                lean_first_out = {
                    "supported": False,
                    "status": "unsupported",
                    "reason": "ODE Lean bridge is not implemented yet.",
                }
            elif lean_parse_error:
                lean_first_out = {
                    "supported": False,
                    "status": "unsupported",
                    "reason": f"Lean parse bridge error: {lean_parse_error}",
                }
            else:
                lean_first_out = lean_first(task, lean_expr)
            lean_status = str(lean_first_out.get("status", "unknown"))
            trace.append(
                NodeTrace(
                    node="lean_first",
                    status=("ok" if lean_status == "ok" else "partial"),
                    summary=f"Lean-first stage status: {lean_status}.",
                    payload={"status": lean_status, "attempt": 1},
                )
            )
        else:
            trace.append(
                NodeTrace(
                    node="lean_first",
                    status="skipped",
                    summary="Lean layer disabled by runtime options.",
                    payload={"status": "skipped"},
                )
            )
        trace.append(
            NodeTrace(
                node="sympy",
                status="skipped",
                summary="SymPy layer disabled by runtime options.",
                payload={"task_type": task.task_type},
            )
        )

    verification_items: list[str] = []
    lean_verify: dict[str, Any] | None = None
    sympy_status = str(sympy_out.get("status", "skipped"))

    if sympy_status == "ok" and _is_math_mode(task):
        sols = sympy_out.get("solutions", [])
        result = sympy_out.get("result", "")
        if isinstance(sols, list) and sols:
            sols_latex = [_to_latex(str(s)) for s in sols[:3]]
            sols_display = ", \\quad ".join(sols_latex)
            if len(sols) > 3:
                sols_display += f" \\;\\ldots\\; ({len(sols)} \\text{{ total}})"
            yield f"> **Solution:**\n>\n> $$ {sols_display} $$\n\n"
        elif result:
            yield f"> **Result:**\n>\n> $$ {_to_latex(str(result))} $$\n\n"
    elif sympy_status == "error" and _is_math_mode(task):
        yield "> **SymPy:** computation encountered an error -- attempting repair...\n\n"

    if tool_override and opts.enable_verify:
        verification_items.extend(tool_override.get("verification_items", []))
        lv = tool_override.get("lean_verify")
        if isinstance(lv, dict):
            lean_verify = lv
        tv = tool_override.get("verdict")
        if isinstance(tv, dict) and tv:
            verdict = tv
        else:
            verdict = build_verdict(
                task,
                sympy_out,
                lean_first_out,
                lean_verify,
                {"enabled": bool(opts.enable_graph)},
                layers={
                    "lean": opts.enable_lean,
                    "sympy": opts.enable_sympy,
                    "verify": opts.enable_verify,
                    "graph": opts.enable_graph,
                },
            )
        trace.append(
            NodeTrace(
                node="verify",
                status=str(verdict.get("verdict", "partial")),
                summary="Tool-provided evidence verdict applied.",
                payload={
                    "verdict": verdict.get("verdict"),
                    "confidence": verdict.get("confidence"),
                },
            )
        )
    elif opts.enable_verify:
        if sympy_status == "error":
            verification_items.append(
                f"SymPy stage error: `{sympy_out.get('message', 'unknown error')}`"
            )
        elif task.task_type == "solve":
            residuals = sympy_out.get("residuals", [])
            residual_exact_ok = sympy_out.get("residual_exact_ok", [])
            residual_abs = sympy_out.get("residual_abs", [])
            if isinstance(residual_exact_ok, list) and residual_exact_ok:
                symbolic_ok = all(bool(x) for x in residual_exact_ok)
            else:
                symbolic_ok = bool(residuals) and all(str(r) == "0" for r in residuals)
            numeric_ok = bool(residual_abs) and all(
                (r is not None and float(r) <= 1e-8) for r in residual_abs
            )
            sympy_ok = symbolic_ok or numeric_ok
            verification_items.append(
                f"SymPy back-substitution residuals: `{residuals}`"
            )
            if residual_exact_ok:
                verification_items.append(
                    f"SymPy exact residual flags: `{residual_exact_ok}`"
                )
            if residual_abs:
                verification_items.append(
                    f"SymPy residual abs values: `{[round(float(x), 12) if x is not None else None for x in residual_abs]}`"
                )
            verification_items.append(
                f"SymPy residual check: `{'pass' if sympy_ok else 'fail'}`"
            )
            if opts.enable_lean and lean_expr is not None:
                sols = [to_sympy(s) for s in sympy_out.get("solutions", [])]
                lean_verify = lean_verify_solutions(task, lean_expr, sols)
                verification_items.append(
                    f"Lean root proofs: `{lean_verify.get('status', 'unknown')}`"
                )
                if lean_verify.get("checks"):
                    verification_items.append(f"Lean checks: `{lean_verify['checks']}`")
        elif task.task_type == "simplify":
            verification_items.append(
                "SymPy equivalence simplify(original - result) == 0: "
                f"`{sympy_out.get('equivalent', False)}`"
            )
        elif task.task_type == "integrate":
            verification_items.append(
                "Derivative check d/d"
                f"{task.variable}(result) == integrand: `{sympy_out.get('derivative_check', False)}`"
            )
        elif task.task_type == "differentiate":
            verification_items.append(
                f"Derivative identity check: `{sympy_out.get('derivative_check', False)}`"
            )
        elif task.task_type == "ode":
            verification_items.append(
                f"SymPy ODE residual checks: `{sympy_out.get('residual_exact_ok', [])}`"
            )
        else:
            verification_items.append("No symbolic verification was applicable.")

        verdict = build_verdict(
            task,
            sympy_out,
            lean_first_out,
            lean_verify,
            {
                "enabled": bool(
                    opts.enable_graph
                    and sympy_status == "ok"
                    and task.task_type != "explain"
                )
            },
            layers={
                "lean": opts.enable_lean,
                "sympy": opts.enable_sympy,
                "verify": opts.enable_verify,
                "graph": opts.enable_graph,
            },
        )
        trace.append(
            NodeTrace(
                node="verify",
                status=str(verdict.get("verdict", "partial")),
                summary="Evidence verdict generated.",
                payload={
                    "verdict": verdict.get("verdict"),
                    "confidence": verdict.get("confidence"),
                },
            )
        )
    else:
        verification_items.append("Verification layer disabled by runtime options.")
        verdict = _verification_without_verifier(sympy_out)
        trace.append(
            NodeTrace(
                node="verify",
                status="skipped",
                summary="Verification layer disabled by runtime options.",
                payload={},
            )
        )

    if tool_override:
        if opts.enable_graph:
            graph = tool_override.get(
                "graph",
                {"enabled": False, "reason": "No graph artifacts from tool layer."},
            )
            if not isinstance(graph, dict):
                graph = {
                    "enabled": False,
                    "reason": "Invalid graph payload from tool layer.",
                }
        else:
            graph = {
                "enabled": False,
                "reason": "Graph layer disabled by runtime options.",
            }
    elif opts.enable_graph and sympy_status == "ok":
        graph = build_graph_artifacts(task, sympy_out)
    elif not opts.enable_graph:
        graph = {"enabled": False, "reason": "Graph layer disabled by runtime options."}
    elif sympy_status == "error":
        graph = {"enabled": False, "reason": "SymPy stage failed; graph stage skipped."}
    else:
        graph = {"enabled": False, "reason": "No symbolic object to graph."}

    trace.append(
        NodeTrace(
            node="graph",
            status=("ok" if graph.get("enabled") else "skipped"),
            summary=(
                "Graph evidence generated."
                if graph.get("enabled")
                else "Graph stage skipped."
            ),
            payload={
                "tool_calls": graph.get("tool_calls", []),
                "expressions": graph.get("desmos", {}).get("expressions", []),
            },
        )
    )

    if _is_math_mode(task) and sympy_status != "skipped":
        v = str(verdict.get("verdict", "partial"))
        c = float(verdict.get("confidence", 0.0))
        yield f"> **Verdict:** `{v}` (confidence: {c:.2f})\n\n"

    verification = {
        "items": verification_items,
        "lean_verify": lean_verify,
        "verdict": verdict,
    }
    evidence = {
        "parsed_task": task.__dict__,
        "lean_first": lean_first_out,
        "sympy": sympy_out,
        "verification": verification,
        "graph": graph,
        "runtime": opts.__dict__,
        "trace": [t.__dict__ for t in trace],
    }

    use_glm = opts.output_mode == "teach" and _env_bool("TB_TEACH_USE_GLM", False)
    glm_conversational: str | None = None
    nlg_note = ""
    if use_glm:
        tutor_timeout = _env_float("TB_GLM_TUTOR_TIMEOUT_SECONDS", 8.0)
        try:
            glm_conversational = await wait_for(
                glm_tutor_response(raw_question, evidence, style="socratic"),
                timeout=tutor_timeout,
            )
        except TimeoutError:
            nlg_note = f"Tutor NLG timed out after {tutor_timeout:.1f}s; used deterministic fallback."
    fallback_text = conversational_override or _fallback_conversation(task, sympy_out)
    if task.task_type == "explain":
        wolfram_hint = _wolfram_fallback_conversation(tool_out)
        if wolfram_hint:
            fallback_text = wolfram_hint
        elif image_urls:
            fallback_text = _image_explain_fallback(vision_out)
    used_glm_nlg = bool(glm_conversational)
    conversational = glm_conversational or fallback_text
    if nlg_note and opts.output_mode == "evidence":
        conversational = f"{conversational}\n\nNote: {nlg_note}"
    if task.task_type == "explain":
        vh = _vision_access_hint(vision_out)
        if vh:
            conversational = vh

    trace.append(
        NodeTrace(
            node="compose",
            status="ok",
            summary="Final response rendered.",
            payload={
                "used_glm_nlg": used_glm_nlg,
                "mode": opts.output_mode,
                "nlg_note": nlg_note,
            },
        )
    )

    if opts.output_mode == "evidence":
        final_answer = _render_evidence(
            task=task,
            lean_first_out=lean_first_out,
            sympy_out=sympy_out,
            verification=verification,
            graph=graph,
            verdict=verdict,
            conversational=conversational,
            trace=trace,
            vision=vision_out,
            tool_out=tool_out,
            opts=opts,
        )
    elif opts.output_mode == "teach":
        final_answer = _render_teach(
            task=task,
            sympy_out=sympy_out,
            lean_first_out=lean_first_out,
            graph=graph,
            verdict=verdict,
            tool_out=tool_out,
            conversational=conversational,
        )
    else:
        final_answer = conversational.strip()

    artifact = _render_inline_graph_artifact(graph, opts.embed_graph_artifact)
    if artifact:
        final_answer = f"{final_answer}\n\n{artifact}".strip()

    yield TutorResult(
        task=task,
        lean_first=lean_first_out,
        sympy=sympy_out,
        verification=verification,
        graph=graph,
        verdict=verdict,
        trace=trace,
        final_answer=final_answer,
        raw_question=raw_question,
    )


async def run_tutor(
    question: str,
    image_urls: list[str] | None = None,
    forward_headers: dict[str, str] | None = None,
) -> TutorResult:
    """Non-streaming wrapper: runs the pipeline and returns only the TutorResult."""
    result: TutorResult | None = None
    async for item in run_tutor_stream(
        question, image_urls=image_urls, forward_headers=forward_headers
    ):
        if isinstance(item, TutorResult):
            result = item
    assert result is not None, "Pipeline did not produce a TutorResult"
    return result
