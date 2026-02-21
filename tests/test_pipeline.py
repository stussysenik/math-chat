import asyncio

from truthbattle.pipeline import run_tutor
from truthbattle.types import TaskSpec


async def _no_vision(*args, **kwargs):
    return None


async def _no_tutor(*args, **kwargs):
    return None


async def _vision_ok(*args, **kwargs):
    return {
        "normalized_problem": "solve x^2 - 1 = 0 for x",
        "transcription": "solve x^2 - 1 = 0",
        "hints": [],
        "confidence": 0.99,
    }


async def _vision_long_ode(*args, **kwargs):
    return {
        "normalized_problem": (
            "CAS PROJECT. Graphing Particular Solutions. "
            "(21) dy - y^2 sin x dx = 0. "
            "(a) Show that (21) is not exact. "
            "(b) Solve (21) by separating variables."
        ),
        "transcription": "",
        "hints": [],
        "confidence": 0.83,
    }


async def _vision_inaccessible(*args, **kwargs):
    return {
        "transcription": "",
        "normalized_problem": "",
        "hints": [],
        "confidence": 0.0,
        "note": "No accessible image could be sent to vision model. local image fetch failed: HTTP 401",
    }


async def _tool_wolfram_partial(*args, **kwargs):
    return {
        "status": "partial",
        "selected": "wolfram_alpha",
        "tool_calls": ["wolfram_alpha"],
        "notes": [],
        "wolfram": {
            "status": "ok",
            "pods": [{"title": "Result", "plaintext": ["x = 2, 3"]}],
        },
    }


async def _tool_incline_word_problem(*args, **kwargs):
    return {
        "status": "ok",
        "selected": "inclined_plane_friction_solver",
        "tool_calls": [
            "word_solver.incline_friction",
            "sympy",
            "lean",
            "desmos",
            "mafs",
        ],
        "notes": [],
        "word_problem": {
            "sympy": {
                "result": "8.0",
                "steps": ["Derived acceleration.", "Applied v^2 = v0^2 + 2as."],
            },
            "lean": {"status": "ok", "code": "import Std\n#check Nat"},
            "graph": {"enabled": True, "tool_calls": ["desmos", "mafs"]},
            "verification_items": ["SymPy residual check: pass", "Lean check: ok"],
            "verdict": {"verdict": "pass", "confidence": 0.9},
            "answer": "Final speed is approximately 8.0 m/s.",
            "parameters": {
                "mu": 0.2,
                "angle_deg": 30.0,
                "length_m": 10.0,
                "v0": 0.0,
                "g": 9.81,
            },
        },
    }


def _fake_lean_first(*args, **kwargs):
    return {"status": "ok", "code": "import Std\n#check Nat"}


def _fake_lean_verify(*args, **kwargs):
    return {"status": "ok", "checks": [{"solution": "2", "status": "proved"}]}


async def _parse_bad_equation(*args, **kwargs):
    return TaskSpec(
        task_type="solve",
        lhs="x**2+",
        rhs="0",
        variable="x",
        domain="real",
        assumptions=[],
        reasoning="bad parse",
    )


async def _repair_good_equation(*args, **kwargs):
    return TaskSpec(
        task_type="solve",
        lhs="x**2-1",
        rhs="0",
        variable="x",
        domain="real",
        assumptions=["x in R"],
        reasoning="repaired parse",
    )


async def _parse_bad_natural_language_math(*args, **kwargs):
    return TaskSpec(
        task_type="solve",
        lhs="Hi #### Tools Available 1. Code interpreter",
        rhs="0",
        variable="x",
        domain="unspecified",
        assumptions=[],
        reasoning="bad parser output",
    )


async def _repair_none(*args, **kwargs):
    return None


def test_pipeline_answer_first_and_trace(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)

    result = asyncio.run(
        run_tutor("[tb: mode=evidence trace=on] solve x^2 - 5x + 6 = 0")
    )

    assert result.final_answer.startswith("## Final Answer")
    assert "## LEAN Layer" in result.final_answer
    assert "## SymPy Layer" in result.final_answer
    assert "## Graph Layer" in result.final_answer
    assert "## Node Trace" in result.final_answer

    nodes = [n.node for n in result.trace]
    assert nodes == [
        "ingest",
        "parse",
        "tools",
        "lean_first",
        "sympy",
        "verify",
        "graph",
        "compose",
    ]
    assert result.verdict["verdict"] in {"pass", "partial", "fail"}


def test_pipeline_vision_merge(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _vision_ok)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)

    result = asyncio.run(run_tutor("", image_urls=["https://x.test/math.png"]))
    assert result.task.task_type == "solve"
    assert result.trace[0].node == "ingest"
    assert result.trace[0].status == "ok"


def test_pipeline_vision_generic_prompt_promotes_symbolic(monkeypatch):
    monkeypatch.setattr(
        "truthbattle.pipeline.glm_extract_from_images", _vision_long_ode
    )
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)

    result = asyncio.run(
        run_tutor("how to solve this?", image_urls=["https://x.test/cas.png"])
    )
    assert result.task.task_type == "ode"
    assert "I can solve equations" not in result.final_answer
    assert any(
        (n.node == "parse" and n.payload.get("task") == "ode")
        or (n.node == "parse_vision" and n.status == "ok")
        for n in result.trace
    )


def test_pipeline_conversational_mode(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)

    result = asyncio.run(run_tutor("hi"))
    assert result.final_answer
    assert "LEAN Layer" not in result.final_answer


def test_pipeline_image_access_hint_in_conversational_mode(monkeypatch):
    monkeypatch.setattr(
        "truthbattle.pipeline.glm_extract_from_images", _vision_inaccessible
    )
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)

    result = asyncio.run(
        run_tutor(
            "how to solve this?",
            image_urls=["http://127.0.0.1:3000/api/v1/files/x/content"],
        )
    )
    assert "could not access its bytes for vision parsing" in result.final_answer


def test_pipeline_repair_loop_after_sympy_error(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)
    monkeypatch.setattr("truthbattle.pipeline.parse_task", _parse_bad_equation)
    monkeypatch.setattr("truthbattle.pipeline.repair_task", _repair_good_equation)

    result = asyncio.run(run_tutor("solve x^2-1=0"))
    nodes = [n.node for n in result.trace]

    assert "repair" in nodes
    assert result.sympy["status"] == "ok"
    assert set(result.sympy["solutions"]) == {"-1", "1"}


def test_pipeline_sanitizes_invalid_symbolic_parse(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr(
        "truthbattle.pipeline.parse_task", _parse_bad_natural_language_math
    )
    monkeypatch.setattr("truthbattle.pipeline.repair_task", _repair_none)

    result = asyncio.run(run_tutor("how to solve this?"))
    assert result.task.task_type == "explain"
    assert result.final_answer
    assert any(n.node == "sanitize" for n in result.trace)


def test_pipeline_default_answer_mode_is_compact(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)

    result = asyncio.run(run_tutor("solve x^2 - 1 = 0"))
    assert "## Final Answer" not in result.final_answer
    assert "x = -1" in result.final_answer
    assert "x = 1" in result.final_answer


def test_pipeline_layer_toggles_disable_symbolic(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)

    result = asyncio.run(
        run_tutor(
            "[tb: mode=evidence sympy=off lean=off verify=off graph=off] solve x^2=1"
        )
    )
    assert "SymPy layer disabled by runtime options" in result.final_answer
    assert "Lean layer disabled by runtime options" in result.final_answer


def test_pipeline_auto_teach_mode_without_directive(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)

    result = asyncio.run(run_tutor("solve x^2 - 1 = 0 for x, step by step"))
    assert "## Atomic Walkthrough" in result.final_answer


def test_pipeline_teach_mode_includes_symbolic_numerical_graphical(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)

    result = asyncio.run(run_tutor("solve x^2 - 1 = 0 for x, how to solve this?"))
    assert "## Symbolic Solution" in result.final_answer
    assert "## Numerical Checks" in result.final_answer
    assert "## Graphical Solution" in result.final_answer
    assert "$$" in result.final_answer


def test_pipeline_auto_evidence_mode_without_directive(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)

    result = asyncio.run(
        run_tutor("solve x^2 - 1 = 0 for x and show lean and sympy evidence")
    )
    assert "## LEAN Layer" in result.final_answer
    assert "## SymPy Layer" in result.final_answer


def test_pipeline_uses_wolfram_fallback_for_explain(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.run_tool_layer", _tool_wolfram_partial)

    result = asyncio.run(run_tutor("[tb: mode=answer] how to solve this?"))
    assert "Wolfram fallback" in result.final_answer
    assert any(n.node == "tools" for n in result.trace)


def test_pipeline_tool_promotes_word_problem(monkeypatch):
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr(
        "truthbattle.pipeline.run_tool_layer", _tool_incline_word_problem
    )

    result = asyncio.run(run_tutor("[tb: mode=evidence] how to solve this?"))
    assert result.task.task_type == "solve"
    assert result.task.variable == "v"
    assert "Final speed is approximately 8.0 m/s." in result.final_answer
    assert any(n.node == "tool_promote" for n in result.trace)
