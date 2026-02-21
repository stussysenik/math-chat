from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

from sympy import Add, Expr, Integer, Mul, Pow, Rational, Symbol

from truthbattle.types import TaskSpec


@dataclass
class LeanRun:
    ok: bool
    stdout: str
    stderr: str
    code: str


def _num_to_lean(n: Expr) -> str:
    if isinstance(n, Integer):
        return str(int(n))
    if isinstance(n, Rational):
        if n.q == 1:
            return str(int(n.p))
        return f"({n.p} / {n.q} : Rat)"
    raise ValueError(f"Unsupported number for Lean Rat: {n}")


def sympy_to_lean(expr: Expr, var: str = "x") -> str:
    if isinstance(expr, Symbol):
        if expr.name != var:
            raise ValueError(f"Only variable '{var}' is supported in Lean mode")
        return var
    if isinstance(expr, (Integer, Rational)):
        return _num_to_lean(expr)
    if isinstance(expr, Add):
        return "(" + " + ".join(sympy_to_lean(a, var) for a in expr.args) + ")"
    if isinstance(expr, Mul):
        return "(" + " * ".join(sympy_to_lean(a, var) for a in expr.args) + ")"
    if isinstance(expr, Pow):
        base, exp = expr.args
        if isinstance(exp, Integer):
            e = int(exp)
            if e >= 0:
                return f"(({sympy_to_lean(base, var)}) ^ {e})"
            return f"((1 : Rat) / (({sympy_to_lean(base, var)}) ^ {-e}))"
    raise ValueError(f"Unsupported expression for Lean translation: {expr}")


def run_lean(code: str) -> LeanRun:
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        proc = subprocess.run(["lean", path], capture_output=True, text=True)
        return LeanRun(
            proc.returncode == 0,
            proc.stdout.strip(),
            proc.stderr.strip(),
            code,
        )
    except FileNotFoundError:
        return LeanRun(False, "", "Lean executable not found in PATH.", code)


def lean_first(task: TaskSpec, residual_expr: Expr | None) -> dict[str, Any]:
    if residual_expr is None:
        return {
            "supported": False,
            "status": "skipped",
            "reason": "No Lean expression generated.",
        }
    try:
        body = sympy_to_lean(residual_expr, task.variable)
    except Exception as e:
        return {"supported": False, "status": "unsupported", "reason": str(e)}

    code = (
        "import Std\n\n"
        f"def residual ({task.variable} : Rat) : Rat := {body}\n"
        "#check residual\n"
    )
    run = run_lean(code)
    return {
        "supported": True,
        "status": "ok" if run.ok else "error",
        "compiled": run.ok,
        "stdout": run.stdout,
        "stderr": run.stderr,
        "code": run.code,
    }


def lean_verify_solutions(
    task: TaskSpec, residual_expr: Expr, solutions: list[Expr]
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    proof_lines: list[str] = []

    try:
        residual = sympy_to_lean(residual_expr, task.variable)
    except Exception as e:
        return {
            "status": "unsupported",
            "reason": str(e),
            "checks": checks,
            "compiled": False,
            "code": "",
        }

    for i, sol in enumerate(solutions, 1):
        try:
            v = sympy_to_lean(sol, task.variable)
            proof_name = f"sol_{i}"
            proof_lines.append(f"example : residual ({v}) = 0 := by native_decide")
            checks.append(
                {"solution": str(sol), "lean_exact": True, "status": "queued"}
            )
        except Exception as e:
            checks.append(
                {
                    "solution": str(sol),
                    "lean_exact": False,
                    "status": "skipped",
                    "reason": str(e),
                }
            )

    if not proof_lines:
        return {
            "status": "skipped",
            "reason": "No solution was representable as Rat in Lean.",
            "checks": checks,
            "compiled": False,
            "code": "",
        }

    code = (
        "import Std\n\n"
        + f"def residual ({task.variable} : Rat) : Rat := {residual}\n\n"
        + "\n".join(proof_lines)
        + "\n"
    )
    run = run_lean(code)

    if run.ok:
        for c in checks:
            if c["status"] == "queued":
                c["status"] = "proved"
    else:
        for c in checks:
            if c["status"] == "queued":
                c["status"] = "failed"
                c["reason"] = run.stderr or "Lean proof failed"

    return {
        "status": "ok" if run.ok else "error",
        "checks": checks,
        "compiled": run.ok,
        "stdout": run.stdout,
        "stderr": run.stderr,
        "code": run.code,
    }
