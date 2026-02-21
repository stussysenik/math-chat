from truthbattle.types import TaskSpec
from truthbattle.verifier import build_verdict


def test_verdict_solve_pass_with_lean():
    task = TaskSpec(task_type="solve", lhs="x**2-5*x+6", rhs="0", variable="x")
    sympy_out = {"residuals": ["0", "0"], "solutions": ["2", "3"]}
    lean_first = {"status": "ok"}
    lean_verify = {"status": "ok", "checks": []}
    graph = {"enabled": True}

    v = build_verdict(task, sympy_out, lean_first, lean_verify, graph)
    assert v["verdict"] == "pass"
    assert v["confidence"] > 0.9


def test_verdict_solve_partial_without_lean_verify():
    task = TaskSpec(task_type="solve", lhs="x**2-5*x+6", rhs="0", variable="x")
    sympy_out = {"residuals": ["0", "0"], "solutions": ["2", "3"]}
    lean_first = {"status": "ok"}
    graph = {"enabled": True}

    v = build_verdict(task, sympy_out, lean_first, None, graph)
    assert v["verdict"] == "partial"


def test_verdict_solve_partial_with_numeric_residuals():
    task = TaskSpec(task_type="solve", lhs="v**2", rhs="64.05", variable="v")
    sympy_out = {
        "status": "ok",
        "residuals": ["1.0e-12"],
        "residual_abs": [1.0e-12],
        "solutions": ["8.003"],
    }
    v = build_verdict(
        task, sympy_out, {"status": "unsupported"}, None, {"enabled": True}
    )
    assert v["verdict"] == "partial"


def test_verdict_solve_accepts_symbolic_zero_equivalent_residual():
    task = TaskSpec(task_type="solve", lhs="v**2", rhs="64.05", variable="v")
    sympy_out = {
        "status": "ok",
        "residuals": ["g*(-3.46410161513775 + 2.0*sqrt(3))"],
        "residual_exact_ok": [True],
        "residual_abs": [None],
        "solutions": ["2.5565403155167*sqrt(g)"],
    }
    v = build_verdict(
        task, sympy_out, {"status": "unsupported"}, None, {"enabled": False}
    )
    assert v["verdict"] == "partial"


def test_verdict_simplify_fail():
    task = TaskSpec(task_type="simplify", expression="x+x")
    sympy_out = {"equivalent": False}
    v = build_verdict(task, sympy_out, {"status": "ok"}, None, {"enabled": True})
    assert v["verdict"] == "fail"
