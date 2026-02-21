from __future__ import annotations

import re
from typing import Any

from sympy import (
    Derivative,
    Eq,
    Function,
    N,
    Symbol,
    diff,
    dsolve,
    integrate,
    nsimplify,
    nsolve,
    simplify,
    solve,
    sympify,
)
from sympy.core.expr import Expr
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from truthbattle.types import TaskSpec

_TRANSFORMS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)
_ODE_IC_RE = re.compile(r"^\s*y\s*\(\s*(.+?)\s*\)\s*=\s*(.+?)\s*$", re.IGNORECASE)


def _parse_math(s: str, variable: str = "x") -> Expr:
    local = {variable: Symbol(variable)}
    return parse_expr(s, transformations=_TRANSFORMS, local_dict=local, evaluate=True)


def _parse_ode_residual(s: str, variable: str = "x", dependent: str = "y") -> Expr:
    x = Symbol(variable)
    y = Function(dependent)
    local = {
        variable: x,
        dependent: y,
        "Derivative": Derivative,
    }
    return parse_expr(s, transformations=_TRANSFORMS, local_dict=local, evaluate=True)


def _expr_to_str(obj: Any) -> str:
    return str(obj).replace("**", "^")


def _exactify(expr: Expr) -> Expr:
    try:
        return nsimplify(expr, rational=True)
    except Exception:
        return expr


def _is_zero_expr(expr: Expr) -> bool:
    try:
        if expr == 0:
            return True
        z = simplify(_exactify(expr))
        if z == 0:
            return True
        e = z.equals(0)
        return bool(e) if e is not None else False
    except Exception:
        return False


def _has_positive_constraint(assumptions: list[str] | None, var: str) -> bool:
    if not assumptions:
        return False
    for raw in assumptions:
        s = raw.replace(" ", "").lower()
        if s in {f"{var}>0", f"{var}>=0"}:
            return True
        if re.search(rf"\b{re.escape(var)}\b.*\bpositive\b", raw, re.IGNORECASE):
            return True
    return False


def _has_negative_constraint(assumptions: list[str] | None, var: str) -> bool:
    if not assumptions:
        return False
    for raw in assumptions:
        s = raw.replace(" ", "").lower()
        if s in {f"{var}<0", f"{var}<=0"}:
            return True
        if re.search(rf"\b{re.escape(var)}\b.*\bnegative\b", raw, re.IGNORECASE):
            return True
    return False


def _parse_ode_initial_conditions(
    assumptions: list[str] | None,
    variable: str,
) -> list[tuple[str, Expr, Expr]]:
    if not assumptions:
        return []
    x = Symbol(variable)
    local = {variable: x}
    parsed: list[tuple[str, Expr, Expr]] = []
    for raw in assumptions:
        m = _ODE_IC_RE.match(raw)
        if not m:
            continue
        x0_raw = m.group(1).strip()
        y0_raw = m.group(2).strip()
        try:
            x0 = parse_expr(
                x0_raw, transformations=_TRANSFORMS, local_dict=local, evaluate=True
            )
            y0 = parse_expr(
                y0_raw, transformations=_TRANSFORMS, local_dict=local, evaluate=True
            )
            parsed.append((raw.strip(), x0, y0))
        except Exception:
            continue
    return parsed


def _solve_ode_particulars(
    rhs_expr: Expr,
    variable: Symbol,
    initial_conditions: list[tuple[str, Expr, Expr]],
) -> list[dict[str, Any]]:
    constants = sorted(
        [s for s in rhs_expr.free_symbols if s != variable], key=lambda s: s.name
    )
    if not constants or not initial_conditions:
        return []

    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for label, x0, y0 in initial_conditions:
        try:
            eq_ic = Eq(simplify(rhs_expr.subs(variable, x0)), y0)
            constant_maps = solve(eq_ic, constants, dict=True)
        except Exception:
            constant_maps = []
        for c_map in constant_maps:
            if not isinstance(c_map, dict):
                continue
            try:
                particular_rhs = simplify(rhs_expr.subs(c_map))
                residual = simplify(particular_rhs.subs(variable, x0) - y0)
            except Exception:
                continue
            signature = (label, str(particular_rhs))
            if signature in seen:
                continue
            seen.add(signature)
            found.append(
                {
                    "condition": label,
                    "solution": str(particular_rhs),
                    "constants": {str(k): str(v) for k, v in c_map.items()},
                    "residual": str(residual),
                    "residual_exact_ok": _is_zero_expr(residual),
                }
            )
    return found


def _filter_solutions_by_assumptions(
    solutions: list[Expr],
    var: str,
    assumptions: list[str] | None,
) -> tuple[list[Expr], str | None]:
    want_pos = _has_positive_constraint(assumptions, var)
    want_neg = _has_negative_constraint(assumptions, var)
    if not want_pos and not want_neg:
        return solutions, None

    out: list[Expr] = []
    for s in solutions:
        v: float | None = None
        try:
            v = float(N(s, 30))
        except Exception:
            try:
                subs = {sym: 1 for sym in s.free_symbols if sym.name != var}
                if subs:
                    v = float(N(s.subs(subs), 30))
            except Exception:
                v = None
        if v is None:
            out.append(s)
            continue
        if want_pos and v < 0:
            continue
        if want_neg and v > 0:
            continue
        out.append(s)
    if want_pos:
        return out, f"Applied assumption filter: {var} >= 0."
    return out, f"Applied assumption filter: {var} <= 0."


def run_sympy(task: TaskSpec) -> dict[str, Any]:
    var = Symbol(task.variable)
    steps: list[str] = []

    try:
        if task.task_type == "solve":
            lhs_raw = _parse_math(task.lhs, task.variable)
            rhs_raw = _parse_math(task.rhs, task.variable)
            lhs = _exactify(lhs_raw)
            rhs = _exactify(rhs_raw)
            eq = Eq(lhs, rhs)
            solutions = solve(eq, var)
            if not solutions:
                residual_expr = simplify(lhs - rhs)
                if residual_expr.free_symbols.issubset({var}):
                    guesses = [-10, -3, -1, 0, 1, 3, 10]
                    numeric: list[Expr] = []
                    for g in guesses:
                        try:
                            root = nsolve(residual_expr, var, g)
                            root = _exactify(root)
                            if all(
                                not _is_zero_expr(simplify(root - r)) for r in numeric
                            ):
                                numeric.append(root)
                        except Exception:
                            continue
                    if numeric:
                        solutions = numeric
                        steps.append(
                            f"SymPy symbolic solve returned no roots; nsolve fallback produced {len(numeric)} root(s)."
                        )
            filtered, filter_note = _filter_solutions_by_assumptions(
                list(solutions),
                task.variable,
                task.assumptions,
            )
            residual = [simplify(lhs.subs(var, s) - rhs.subs(var, s)) for s in filtered]
            residual_exact_ok: list[bool] = [_is_zero_expr(r) for r in residual]
            residual_abs: list[float | None] = []
            for r in residual:
                try:
                    residual_abs.append(float(abs(N(r, 40))))
                except Exception:
                    residual_abs.append(None)
            if str(lhs_raw) != str(lhs) or str(rhs_raw) != str(rhs):
                steps.append(
                    "Exactification applied: converted decimal constants to rational-safe form."
                )
            steps.append(f"Parsed equation: {_expr_to_str(lhs)} = {_expr_to_str(rhs)}")
            steps.append(f"SymPy solve -> {[_expr_to_str(s) for s in solutions]}")
            if filter_note:
                steps.append(filter_note)
            return {
                "status": "ok",
                "task_type": task.task_type,
                "variable": task.variable,
                "equation": _expr_to_str(eq),
                "solutions": [str(s) for s in filtered],
                "raw_solutions": [str(s) for s in solutions],
                "residuals": [str(r) for r in residual],
                "residual_exact_ok": residual_exact_ok,
                "residual_abs": residual_abs,
                "steps": steps,
            }

        if task.task_type == "ode":
            x = Symbol(task.variable)
            y = Function("y")
            residual = _parse_ode_residual(task.expression, task.variable, "y")
            eq = Eq(residual, 0)
            out_raw = dsolve(eq)
            solutions_raw = out_raw if isinstance(out_raw, list) else [out_raw]
            rendered_solutions: list[str] = []
            residuals: list[str] = []
            residual_exact_ok: list[bool] = []

            for sol in solutions_raw:
                if isinstance(sol, Eq):
                    rendered_solutions.append(str(sol.rhs))
                    try:
                        sub_expr = simplify(
                            residual.subs(
                                {
                                    y(x): sol.rhs,
                                    Derivative(y(x), x): diff(sol.rhs, x),
                                }
                            )
                        )
                    except Exception:
                        sub_expr = simplify(residual.subs({y(x): sol.rhs}))
                else:
                    rendered_solutions.append(str(sol))
                    sub_expr = simplify(residual)
                residuals.append(str(sub_expr))
                residual_exact_ok.append(_is_zero_expr(sub_expr))

            initial_conditions = _parse_ode_initial_conditions(
                task.assumptions, task.variable
            )
            particular_solutions: list[dict[str, Any]] = []
            for sol in solutions_raw:
                if not isinstance(sol, Eq):
                    continue
                particular_solutions.extend(
                    _solve_ode_particulars(sol.rhs, x, initial_conditions)
                )

            steps.append(f"Parsed ODE residual: {_expr_to_str(residual)} = 0")
            steps.append(f"SymPy dsolve -> {[str(s) for s in solutions_raw]}")
            if initial_conditions:
                if particular_solutions:
                    steps.append(
                        f"Applied {len(initial_conditions)} initial condition(s) -> "
                        f"{len(particular_solutions)} particular solution(s)."
                    )
                else:
                    steps.append(
                        "Initial conditions were detected, but no closed-form "
                        "constant fit was resolved."
                    )

            return {
                "status": "ok",
                "task_type": task.task_type,
                "variable": task.variable,
                "equation": f"{_expr_to_str(residual)} = 0",
                "solutions": rendered_solutions,
                "raw_solutions": [str(s) for s in solutions_raw],
                "residuals": residuals,
                "residual_exact_ok": residual_exact_ok,
                "residual_abs": [0.0 if ok else None for ok in residual_exact_ok],
                "particular_solutions": particular_solutions,
                "steps": steps,
            }

        if task.task_type == "simplify":
            expr = _parse_math(task.expression, task.variable)
            out = simplify(expr)
            equivalent = simplify(expr - out) == 0
            steps.append(f"Parsed expression: {_expr_to_str(expr)}")
            steps.append(f"SymPy simplify -> {_expr_to_str(out)}")
            return {
                "status": "ok",
                "task_type": task.task_type,
                "expression": _expr_to_str(expr),
                "result": str(out),
                "equivalent": bool(equivalent),
                "steps": steps,
            }

        if task.task_type == "differentiate":
            expr = _parse_math(task.expression, task.variable)
            out = diff(expr, var)
            derivative_check = simplify(diff(expr, var) - out) == 0
            steps.append(f"Parsed expression: {_expr_to_str(expr)}")
            steps.append(f"SymPy diff wrt {task.variable} -> {_expr_to_str(out)}")
            return {
                "status": "ok",
                "task_type": task.task_type,
                "expression": _expr_to_str(expr),
                "result": str(out),
                "derivative_check": bool(derivative_check),
                "steps": steps,
            }

        if task.task_type == "integrate":
            expr = _parse_math(task.expression, task.variable)
            out = integrate(expr, var)
            derivative_check = simplify(diff(out, var) - expr) == 0
            steps.append(f"Parsed expression: {_expr_to_str(expr)}")
            steps.append(f"SymPy integrate wrt {task.variable} -> {_expr_to_str(out)}")
            return {
                "status": "ok",
                "task_type": task.task_type,
                "expression": _expr_to_str(expr),
                "result": str(out),
                "derivative_check": bool(derivative_check),
                "steps": steps,
            }
    except Exception as e:
        return {
            "status": "error",
            "task_type": task.task_type,
            "message": f"SymPy execution error: {e}",
            "steps": [f"SymPy failed: {e}"],
        }

    return {
        "status": "skipped",
        "task_type": "explain",
        "message": (
            "I can solve equations, simplify, differentiate, integrate, or solve basic ODEs. "
            "Please ask in one of those formats."
        ),
        "steps": ["No symbolic action executed."],
    }


def parse_for_lean(task: TaskSpec) -> tuple[Expr, Expr | None, Symbol]:
    var = Symbol(task.variable)
    if task.task_type == "solve":
        lhs = _parse_math(task.lhs, task.variable)
        rhs = _parse_math(task.rhs, task.variable)
        return lhs, rhs, var
    if task.task_type == "ode":
        raise ValueError("ODE bridge to Lean is not supported yet.")
    expr = _parse_math(task.expression, task.variable)
    return expr, None, var


def to_sympy(s: str) -> Expr:
    return sympify(s)
