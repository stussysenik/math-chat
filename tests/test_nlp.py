import asyncio

from truthbattle.nlp import parse_task


def test_parse_solve_heuristic():
    task = asyncio.run(parse_task("solve x^2 - 5x + 6 = 0 for x"))
    assert task.task_type == "solve"
    assert task.lhs.replace(" ", "") == "x**2-5x+6"
    assert task.rhs == "0"
    assert task.variable == "x"


def test_parse_solve_heuristic_with_assuming_clause():
    task = asyncio.run(
        parse_task("solve v^2 = 2*g*10*(sin(pi/6)-0.2*cos(pi/6)) for v assuming v >= 0")
    )
    assert task.task_type == "solve"
    assert "v**2" in task.lhs
    assert task.variable == "v"
    assert "v >= 0" in (task.assumptions or [])


def test_parse_domain_real():
    task = asyncio.run(parse_task("solve x^2+1=0 over reals"))
    assert task.task_type == "solve"
    assert task.domain == "real"


def test_parse_differentiate():
    task = asyncio.run(parse_task("differentiate x^3 + 2x"))
    assert task.task_type == "differentiate"
    assert "x**3" in task.expression


def test_parse_ode_differential_form():
    task = asyncio.run(parse_task("dy - y^2 sin x dx = 0"))
    assert task.task_type == "ode"
    assert "Derivative(y(x), x)" in task.expression


def test_parse_ode_from_long_cas_text():
    task = asyncio.run(
        parse_task(
            """
CAS PROJECT. Graphing Particular Solutions.
Graph particular solutions of the following ODE as explained.
(21) dy - y^2 sin x dx = 0.
(a) Show that (21) is not exact. Find an integrating factor.
(b) Solve (21) by separating variables.
(c) Graph solutions for y(0)=1 and y(pi/2)=+/-1/2.
""".strip()
        )
    )
    assert task.task_type == "ode"
    assert "Derivative(y(x), x)" in task.expression


def test_parse_ode_extracts_initial_conditions_and_plus_minus():
    task = asyncio.run(
        parse_task("dy - y^2 sin x dx = 0, y(0)=1, y(pi/2)=±1/2, ±2/3, ±1")
    )
    assumptions = task.assumptions or []
    assert task.task_type == "ode"
    assert "y(0) = 1" in assumptions
    assert "y(pi/2) = 1/2" in assumptions
    assert "y(pi/2) = -1/2" in assumptions
    assert "y(pi/2) = 2/3" in assumptions
    assert "y(pi/2) = -2/3" in assumptions
    assert "y(pi/2) = 1" in assumptions
    assert "y(pi/2) = -1" in assumptions


async def _glm_explain(*args, **kwargs):
    return {
        "task_type": "explain",
        "expression": "word problem",
        "lhs": "",
        "rhs": "",
        "variable": "x",
        "domain": "unspecified",
        "assumptions": [],
        "reasoning": "glm explain",
    }


async def _glm_repair_to_solve(*args, **kwargs):
    return {
        "task_type": "solve",
        "expression": "",
        "lhs": "v**2",
        "rhs": "2*9.81*(sin(pi/6)-0.2*cos(pi/6))*10",
        "variable": "v",
        "domain": "real",
        "assumptions": ["v >= 0"],
        "reasoning": "repaired to symbolic equation",
    }


def test_parse_promotes_explain_with_repair(monkeypatch):
    monkeypatch.setattr("truthbattle.nlp.glm_extract_task", _glm_explain)
    monkeypatch.setattr("truthbattle.nlp.glm_repair_task", _glm_repair_to_solve)

    task = asyncio.run(parse_task("Find velocity at end of friction slide."))
    assert task.task_type == "solve"
    assert task.variable == "v"
    assert task.assumptions == ["v >= 0"]
