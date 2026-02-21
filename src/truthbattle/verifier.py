from __future__ import annotations

from typing import Any

from sympy import sympify

from truthbattle.types import TaskSpec


def _bool(v: Any) -> bool:
    return bool(v)


def _is_zero_residual(residual: Any) -> bool:
    if residual is None:
        return False
    s = str(residual).strip()
    if s in {"0", "0.0"}:
        return True
    try:
        expr = sympify(s)
        if expr == 0:
            return True
        eq = expr.equals(0)
        return bool(eq) if eq is not None else False
    except Exception:
        return False


def build_verdict(
    task: TaskSpec,
    sympy_out: dict[str, Any],
    lean_first_out: dict[str, Any],
    lean_verify: dict[str, Any] | None,
    graph_out: dict[str, Any],
    layers: dict[str, bool] | None = None,
) -> dict[str, Any]:
    layer_cfg = layers or {}
    lean_enabled = bool(layer_cfg.get("lean", True))
    graph_enabled = bool(layer_cfg.get("graph", True))

    verdict = "partial"
    confidence = 0.5
    issues: list[str] = []
    accepted_claims: list[str] = []
    missing_proofs: list[str] = []
    next_checks: list[str] = []

    sympy_status = str(sympy_out.get("status", "ok"))
    if sympy_status == "error":
        verdict = "fail"
        confidence = 0.15
        issues.append(str(sympy_out.get("message", "SymPy stage failed.")))
        missing_proofs.append("Symbolic execution did not complete.")
        next_checks.append("Repair parser output and rerun SymPy/Lean pipeline.")
    elif task.task_type == "solve":
        residuals = [str(x) for x in sympy_out.get("residuals", [])]
        residual_abs = sympy_out.get("residual_abs", [])
        residual_exact_ok = sympy_out.get("residual_exact_ok", [])
        if isinstance(residual_exact_ok, list) and residual_exact_ok:
            sympy_exact = all(bool(x) for x in residual_exact_ok)
        else:
            sympy_exact = bool(residuals) and all(
                _is_zero_residual(r) for r in residuals
            )
        sympy_numeric_ok = bool(residual_abs) and all(
            (r is not None and float(r) <= 1e-8) for r in residual_abs
        )
        sympy_ok = sympy_exact or sympy_numeric_ok

        if sympy_ok:
            accepted_claims.append("SymPy back-substitution residuals are all zero.")
        else:
            issues.append(
                "SymPy residual check did not pass cleanly for all solutions."
            )
            next_checks.append("Re-run solve with explicit domain assumptions.")

        if lean_enabled:
            if lean_verify is None:
                missing_proofs.append("No Lean root verification was executed.")
            else:
                status = str(lean_verify.get("status", "unknown"))
                if status == "ok":
                    accepted_claims.append(
                        "Lean root proofs succeeded for representable solutions."
                    )
                else:
                    missing_proofs.append(f"Lean root verification status: {status}.")
                    next_checks.append(
                        "Inspect non-rational or unsupported roots for Lean bridging."
                    )

        if (
            sympy_ok
            and lean_enabled
            and lean_verify
            and str(lean_verify.get("status", "")) == "ok"
        ):
            verdict = "pass"
            confidence = 0.98
        elif sympy_ok:
            verdict = "partial"
            confidence = 0.82
        else:
            verdict = "fail"
            confidence = 0.25

    elif task.task_type == "simplify":
        equivalent = _bool(sympy_out.get("equivalent", False))
        if equivalent:
            verdict = "pass"
            confidence = 0.97
            accepted_claims.append("Simplification equivalence check passed.")
        else:
            verdict = "fail"
            confidence = 0.2
            issues.append("Simplification equivalence check failed.")
            next_checks.append(
                "Compare original and simplified form symbolically under stated domain."
            )

    elif task.task_type == "differentiate":
        derivative_check = _bool(sympy_out.get("derivative_check", True))
        if derivative_check:
            verdict = "pass"
            confidence = 0.9
            accepted_claims.append("Derivative identity check passed in SymPy.")
        else:
            verdict = "fail"
            confidence = 0.3
            issues.append("Derivative check failed.")
            next_checks.append(
                "Re-derive derivative manually and compare term-by-term."
            )

    elif task.task_type == "integrate":
        derivative_check = _bool(sympy_out.get("derivative_check", False))
        if derivative_check:
            verdict = "pass"
            confidence = 0.94
            accepted_claims.append("Differentiating antiderivative returns integrand.")
        else:
            verdict = "fail"
            confidence = 0.2
            issues.append("Antiderivative derivative-check failed.")
            next_checks.append(
                "Apply integration constants and domain constraints before re-checking."
            )

    elif task.task_type == "ode":
        residual_exact_ok = sympy_out.get("residual_exact_ok", [])
        if isinstance(residual_exact_ok, list) and residual_exact_ok:
            all_ok = all(bool(x) for x in residual_exact_ok)
            if all_ok:
                verdict = "pass"
                confidence = 0.9
                accepted_claims.append("ODE solution residual check passed in SymPy.")
            else:
                verdict = "partial"
                confidence = 0.55
                issues.append(
                    "At least one ODE solution failed direct residual substitution."
                )
                next_checks.append(
                    "Substitute each ODE branch and simplify under domain assumptions."
                )
        else:
            verdict = "partial"
            confidence = 0.45
            missing_proofs.append("No ODE residual checks were available.")
            next_checks.append("Re-run with explicit ODE form and dependent variable.")

    else:
        verdict = "partial"
        confidence = 0.35
        issues.append("No symbolic workflow was executed for this prompt.")
        next_checks.append(
            "Provide an explicit symbolic objective (solve/simplify/diff/integrate)."
        )

    if graph_out.get("enabled"):
        accepted_claims.append("Graph artifacts generated for visual inspection.")
    elif graph_enabled:
        missing_proofs.append("No graph artifacts were generated.")

    if lean_enabled and lean_first_out.get("status") in {"unsupported", "error"}:
        missing_proofs.append(
            "Lean-first formalization could not be fully established."
        )

    return {
        "verdict": verdict,
        "confidence": confidence,
        "issues": issues,
        "accepted_claims": accepted_claims,
        "missing_proofs": missing_proofs,
        "next_checks": next_checks,
    }
