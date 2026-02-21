from sympy import N

from truthbattle.sympy_engine import run_sympy, to_sympy
from truthbattle.types import TaskSpec


def test_sympy_solve_quadratic():
    out = run_sympy(
        TaskSpec(task_type="solve", lhs="x**2-5*x+6", rhs="0", variable="x")
    )
    assert out["solutions"] == ["2", "3"]
    assert out["residuals"] == ["0", "0"]


def test_sympy_differentiate_check():
    out = run_sympy(
        TaskSpec(task_type="differentiate", expression="x**3 + 2*x", variable="x")
    )
    assert out["result"] == "3*x**2 + 2"
    assert out["derivative_check"] is True


def test_sympy_integrate_check():
    out = run_sympy(TaskSpec(task_type="integrate", expression="3*x**2", variable="x"))
    assert out["result"] == "x**3"
    assert out["derivative_check"] is True


def test_sympy_error_is_structured():
    out = run_sympy(TaskSpec(task_type="solve", lhs="x**2+", rhs="0", variable="x"))
    assert out["status"] == "error"
    assert "SymPy execution error" in out["message"]


def test_sympy_solve_honors_positive_assumption():
    out = run_sympy(
        TaskSpec(
            task_type="solve",
            lhs="v**2",
            rhs="64.05",
            variable="v",
            assumptions=["v > 0"],
        )
    )
    assert out["status"] == "ok"
    assert len(out["solutions"]) == 1
    assert float(N(to_sympy(out["solutions"][0]))) > 0
    assert len(out["raw_solutions"]) == 2
    assert out["residual_abs"][0] is not None


def test_sympy_solve_symbolic_pair_honors_positive_assumption():
    out = run_sympy(
        TaskSpec(
            task_type="solve",
            lhs="v**2",
            rhs="g",
            variable="v",
            assumptions=["v >= 0"],
        )
    )
    assert out["status"] == "ok"
    assert out["solutions"] == ["sqrt(g)"]


def test_sympy_ode_solve_residual_check():
    out = run_sympy(
        TaskSpec(
            task_type="ode",
            expression="Derivative(y(x), x) - y(x)",
            variable="x",
        )
    )
    assert out["status"] == "ok"
    assert out["task_type"] == "ode"
    assert out["solutions"]
    assert any("exp(x)" in s for s in out["solutions"])


def test_sympy_ode_particular_solutions_from_initial_conditions():
    out = run_sympy(
        TaskSpec(
            task_type="ode",
            expression="Derivative(y(x), x) - y(x)**2*sin(x)",
            variable="x",
            assumptions=[
                "y(0) = 1",
                "y(pi/2) = 1/2",
                "y(pi/2) = -1/2",
            ],
        )
    )
    particulars = out.get("particular_solutions", [])
    assert out["status"] == "ok"
    assert particulars
    assert any(p.get("condition") == "y(0) = 1" for p in particulars)
    assert all(bool(p.get("residual_exact_ok")) for p in particulars)
