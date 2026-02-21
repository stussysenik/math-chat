from truthbattle.graph_engine import build_graph_artifacts
from truthbattle.types import TaskSpec


def test_graph_solve_has_desmos_lines_and_points():
    task = TaskSpec(task_type="solve", lhs="x**2-5*x+6", rhs="0", variable="x")
    sympy_out = {"solutions": ["2", "3"]}
    graph = build_graph_artifacts(task, sympy_out)

    assert graph["enabled"] is True
    assert "desmos" in graph
    assert "y=x^2-5*x+6" in graph["desmos"]["expressions"]
    assert graph["desmos"]["points"] == [{"x": 2.0, "y": 0.0}, {"x": 3.0, "y": 0.0}]
    assert "y=x^2-5*x+6" in graph["desmos"]["clipboard_text"]


def test_graph_explain_disabled():
    task = TaskSpec(task_type="explain", expression="what is math")
    graph = build_graph_artifacts(task, {"steps": []})
    assert graph["enabled"] is False


def test_graph_ode_uses_particular_solutions_and_ic_points():
    task = TaskSpec(
        task_type="ode",
        expression="Derivative(y(x), x) - y(x)**2*sin(x)",
        variable="x",
    )
    sympy_out = {
        "particular_solutions": [
            {"condition": "y(0) = 1", "solution": "sec(x)"},
            {"condition": "y(pi/2) = 1/2", "solution": "-1/(cos(x) - 2)"},
        ]
    }
    graph = build_graph_artifacts(task, sympy_out)
    expressions = graph["desmos"]["expressions"]
    points = graph["desmos"]["points"]

    assert graph["enabled"] is True
    assert "y=sec(x)" in expressions
    assert "y=-1/(cos(x) - 2)" in expressions
    assert {"x": 0.0, "y": 1.0} in points
