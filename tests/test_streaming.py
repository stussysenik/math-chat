"""Tests for progressive streaming, SSE format, LaTeX rendering, and ODE regression.

Covers:
- run_tutor_stream yields correct progress strings in order
- _stream_progressive produces valid SSE chunks
- _to_latex / _display_math produce correct LaTeX
- ODE trailing * regression (dy - y^2 sin x dx = 0)
- FastAPI /v1/chat/completions with stream=true and stream=false
- Middleware console log output
"""

from __future__ import annotations

import asyncio
import json
from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest

from truthbattle.pipeline import (
    _display_math,
    _to_latex,
    run_tutor,
    run_tutor_stream,
)
from truthbattle.types import TaskSpec, TutorResult


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

async def _no_vision(*args, **kwargs):
    return None


async def _no_tutor(*args, **kwargs):
    return None


def _fake_lean_first(*args, **kwargs):
    return {"status": "ok", "code": "import Std\n#check Nat"}


def _fake_lean_verify(*args, **kwargs):
    return {"status": "ok", "checks": [{"solution": "2", "status": "proved"}]}


def _apply_core_monkeypatches(monkeypatch):
    """Apply the 4 standard monkeypatches every pipeline test needs."""
    monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _no_vision)
    monkeypatch.setattr("truthbattle.pipeline.glm_tutor_response", _no_tutor)
    monkeypatch.setattr("truthbattle.pipeline.lean_first", _fake_lean_first)
    monkeypatch.setattr("truthbattle.pipeline.lean_verify_solutions", _fake_lean_verify)


# ---------------------------------------------------------------------------
# 1. LaTeX rendering tests
# ---------------------------------------------------------------------------

class TestToLatex:
    def test_simple_expression(self):
        result = _to_latex("x**2 - 1")
        assert "x" in result
        assert "^" in result or "2" in result  # LaTeX power notation

    def test_function_application_preserved(self):
        result = _to_latex("y(x)")
        # Should NOT be x*y -- should be y(x) as a function
        assert "x y" not in result.replace(" ", "")
        # Should contain function-like rendering
        assert "y" in result and "x" in result

    def test_derivative(self):
        result = _to_latex("Derivative(y(x), x)")
        # Should produce a fraction-like derivative
        assert "frac" in result or "d" in result

    def test_trig_functions(self):
        result = _to_latex("sin(x)")
        assert "sin" in result

    def test_empty_string(self):
        assert _to_latex("") == ""
        assert _to_latex("  ") == ""

    def test_bad_expression_returns_original(self):
        bad = "this is not math !!!"
        result = _to_latex(bad)
        # Should fall back to original string
        assert result == bad


class TestDisplayMath:
    def test_simple_expression_wrapped(self):
        result = _display_math("x**2")
        assert result.startswith("$$")
        assert result.endswith("$$")

    def test_equation_with_equals(self):
        result = _display_math("y(x) = -1/(C1 - cos(x))")
        assert "=" in result
        assert "$$" in result

    def test_empty_string(self):
        result = _display_math("")
        assert "$$" in result

    def test_solve_display(self):
        result = _display_math("x = 1")
        assert "=" in result
        assert "x" in result


# ---------------------------------------------------------------------------
# 2. ODE trailing * regression tests
# ---------------------------------------------------------------------------

class TestOdeRegression:
    """Regression tests for the trailing * bug in ODE parsing.

    The original regex captured 'y**2*sin(x)*' (with trailing *) from
    'dy - y^2 sin x dx = 0'. This must never happen again.
    """

    def test_ode_diff_form_no_trailing_operator(self):
        """dy - y^2 sin x dx = 0 must NOT have trailing * in expression."""
        task = asyncio.run(
            __import__("truthbattle.nlp", fromlist=["parse_task"]).parse_task(
                "dy - y^2 sin x dx = 0"
            )
        )
        assert task.task_type == "ode"
        assert "Derivative(y(x), x)" in task.expression
        # The critical check: no trailing operator before the closing paren
        assert not task.expression.rstrip().endswith("*)")
        assert "sin(x)*)" not in task.expression

    def test_ode_diff_form_from_cas_project(self):
        """Long CAS project text must parse cleanly."""
        text = (
            "CAS PROJECT. Graphing Particular Solutions. "
            "(21) dy - y^2 sin x dx = 0. "
            "(a) Show that (21) is not exact. "
            "(b) Solve (21) by separating variables."
        )
        task = asyncio.run(
            __import__("truthbattle.nlp", fromlist=["parse_task"]).parse_task(text)
        )
        assert task.task_type == "ode"
        assert "Derivative(y(x), x)" in task.expression
        # Must not contain trailing dangling operators
        expr = task.expression.strip()
        for bad_suffix in ["*)", "+)", "-)", "/)"]:
            assert not expr.endswith(bad_suffix), f"Expression ends with {bad_suffix}: {expr}"


# ---------------------------------------------------------------------------
# 3. Streaming sub-step tests (run_tutor_stream yields)
# ---------------------------------------------------------------------------

class TestStreamingSubSteps:
    """Verify that run_tutor_stream yields the expected progress strings."""

    def _collect_stream(self, monkeypatch, question, **kwargs):
        """Run the stream generator and collect all yields."""
        _apply_core_monkeypatches(monkeypatch)

        items: list[str | TutorResult] = []

        async def _collect():
            async for item in run_tutor_stream(question, **kwargs):
                items.append(item)

        asyncio.run(_collect())
        return items

    def test_solve_yields_lean_and_sympy_progress(self, monkeypatch):
        items = self._collect_stream(monkeypatch, "solve x^2 - 4 = 0")
        strs = [i for i in items if isinstance(i, str)]
        results = [i for i in items if isinstance(i, TutorResult)]

        # Must have at least one TutorResult at the end
        assert len(results) == 1
        result = results[0]
        assert result.task.task_type == "solve"

        # Check for expected progress messages
        joined = "".join(strs)
        assert "Parsed as" in joined, "Should see parsed-as progress"
        assert "Lean" in joined, "Should see Lean-first progress"
        assert "SymPy" in joined, "Should see SymPy progress"
        assert "Solution" in joined or "Result" in joined, "Should see solution"
        assert "Verdict" in joined, "Should see verdict"

    def test_ode_yields_parsed_as_ode(self, monkeypatch):
        items = self._collect_stream(monkeypatch, "dy/dx = x + y")
        strs = [i for i in items if isinstance(i, str)]
        results = [i for i in items if isinstance(i, TutorResult)]

        assert len(results) == 1
        assert results[0].task.task_type == "ode"

        joined = "".join(strs)
        assert "Parsed as" in joined
        assert "`ode`" in joined

    def test_conversational_yields_no_symbolic_progress(self, monkeypatch):
        items = self._collect_stream(monkeypatch, "hi there")
        strs = [i for i in items if isinstance(i, str)]
        results = [i for i in items if isinstance(i, TutorResult)]

        assert len(results) == 1
        # Conversational mode should NOT yield Lean/SymPy progress
        joined = "".join(strs)
        assert "Lean-first" not in joined
        assert "SymPy" not in joined

    def test_stream_progress_order(self, monkeypatch):
        """Verify progress yields appear in the expected pipeline order."""
        items = self._collect_stream(monkeypatch, "solve x^2 - 1 = 0")
        strs = [i for i in items if isinstance(i, str)]

        # Find indices of key progress markers
        indices = {}
        for idx, s in enumerate(strs):
            if "Parsed as" in s:
                indices["parse"] = idx
            elif "Lean-first" in s or "Lean:" in s:
                indices.setdefault("lean", idx)
            elif "SymPy" in s and "computing" in s:
                indices["sympy"] = idx
            elif "Solution" in s or "Result" in s:
                indices["solution"] = idx
            elif "Verdict" in s:
                indices["verdict"] = idx

        # Parse should come before lean, lean before sympy, etc.
        if "parse" in indices and "lean" in indices:
            assert indices["parse"] < indices["lean"]
        if "lean" in indices and "sympy" in indices:
            assert indices["lean"] < indices["sympy"]
        if "sympy" in indices and "solution" in indices:
            assert indices["sympy"] < indices["solution"]
        if "solution" in indices and "verdict" in indices:
            assert indices["solution"] < indices["verdict"]

    def test_image_stream_yields_reading_image(self, monkeypatch):
        async def _vision_ok(*args, **kwargs):
            return {
                "normalized_problem": "solve x^2 - 1 = 0 for x",
                "transcription": "solve x^2 - 1 = 0",
                "hints": [],
                "confidence": 0.99,
            }

        _apply_core_monkeypatches(monkeypatch)
        # Override vision mock after core patches
        monkeypatch.setattr("truthbattle.pipeline.glm_extract_from_images", _vision_ok)

        items: list[str | TutorResult] = []

        async def _collect():
            async for item in run_tutor_stream(
                "", image_urls=["https://x.test/math.png"]
            ):
                items.append(item)

        asyncio.run(_collect())
        strs = [i for i in items if isinstance(i, str)]
        joined = "".join(strs)

        assert "Reading image" in joined, "Should see image reading progress"
        assert "Extracted" in joined, "Should see extraction result"

    def test_stream_final_result_is_last(self, monkeypatch):
        """The TutorResult must be the very last yielded item."""
        items = self._collect_stream(monkeypatch, "solve x^2 - 1 = 0")
        assert isinstance(items[-1], TutorResult)


# ---------------------------------------------------------------------------
# 4. SSE event format validation
# ---------------------------------------------------------------------------

class TestSSEFormat:
    """Validate Server-Sent Events format from _stream_progressive."""

    def _collect_sse(self, monkeypatch, question):
        """Run _stream_progressive and collect raw SSE bytes."""
        from truthbattle.main import _stream_progressive

        _apply_core_monkeypatches(monkeypatch)

        chunks: list[bytes] = []

        async def _collect():
            gen = run_tutor_stream(question)
            async for chunk in _stream_progressive(gen, "test-model"):
                chunks.append(chunk)

        asyncio.run(_collect())
        return chunks

    def test_sse_format_data_prefix(self, monkeypatch):
        """Every SSE chunk must start with 'data: '."""
        chunks = self._collect_sse(monkeypatch, "solve x^2 - 1 = 0")
        for chunk in chunks:
            text = chunk.decode("utf-8")
            assert text.startswith("data: "), f"Chunk missing data prefix: {text[:50]}"

    def test_sse_format_double_newline(self, monkeypatch):
        """Every SSE chunk must end with \\n\\n."""
        chunks = self._collect_sse(monkeypatch, "solve x^2 - 1 = 0")
        for chunk in chunks:
            text = chunk.decode("utf-8")
            assert text.endswith("\n\n"), f"Chunk missing \\n\\n: {text[-20:]}"

    def test_sse_first_chunk_has_role(self, monkeypatch):
        """First SSE chunk must contain role: assistant."""
        chunks = self._collect_sse(monkeypatch, "solve x + 1 = 0")
        first = json.loads(chunks[0].decode("utf-8").removeprefix("data: ").strip())
        assert first["choices"][0]["delta"]["role"] == "assistant"

    def test_sse_last_chunk_is_done(self, monkeypatch):
        """Last SSE chunk must be 'data: [DONE]\\n\\n'."""
        chunks = self._collect_sse(monkeypatch, "solve x + 1 = 0")
        last = chunks[-1].decode("utf-8")
        assert last.strip() == "data: [DONE]"

    def test_sse_stop_chunk_before_done(self, monkeypatch):
        """Second-to-last chunk must have finish_reason='stop'."""
        chunks = self._collect_sse(monkeypatch, "solve x + 1 = 0")
        stop_chunk = json.loads(
            chunks[-2].decode("utf-8").removeprefix("data: ").strip()
        )
        assert stop_chunk["choices"][0]["finish_reason"] == "stop"

    def test_sse_content_chunks_are_valid_json(self, monkeypatch):
        """All non-DONE chunks must be valid JSON with expected structure."""
        chunks = self._collect_sse(monkeypatch, "solve x^2 - 1 = 0")
        for chunk in chunks:
            text = chunk.decode("utf-8").strip()
            if text == "data: [DONE]":
                continue
            payload_str = text.removeprefix("data: ")
            payload = json.loads(payload_str)
            assert "id" in payload
            assert payload["object"] == "chat.completion.chunk"
            assert "model" in payload
            assert "choices" in payload
            assert len(payload["choices"]) == 1

    def test_sse_consistent_chunk_id(self, monkeypatch):
        """All chunks in one stream must share the same id."""
        chunks = self._collect_sse(monkeypatch, "solve x + 1 = 0")
        ids = set()
        for chunk in chunks:
            text = chunk.decode("utf-8").strip()
            if text == "data: [DONE]":
                continue
            payload = json.loads(text.removeprefix("data: "))
            ids.add(payload["id"])
        assert len(ids) == 1, f"Expected 1 chunk id, got {ids}"

    def test_sse_progress_separator_before_final(self, monkeypatch):
        """When progress yields exist, a --- separator should appear before the final answer."""
        chunks = self._collect_sse(monkeypatch, "solve x^2 - 1 = 0")
        full_content = ""
        for chunk in chunks:
            text = chunk.decode("utf-8").strip()
            if text == "data: [DONE]":
                continue
            payload = json.loads(text.removeprefix("data: "))
            delta = payload["choices"][0].get("delta", {})
            if "content" in delta:
                full_content += delta["content"]
        # Should have progress + separator + final answer
        assert "---" in full_content, "Missing --- separator between progress and final answer"


# ---------------------------------------------------------------------------
# 5. FastAPI endpoint tests
# ---------------------------------------------------------------------------

class TestAPIEndpoints:
    """Test the /v1/chat/completions endpoint with stream=true and stream=false."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        _apply_core_monkeypatches(monkeypatch)

    def _client(self):
        from httpx import ASGITransport, AsyncClient
        from truthbattle.main import app

        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    def test_health_endpoint(self):
        async def _run():
            async with self._client() as client:
                resp = await client.get("/health")
                assert resp.status_code == 200
                assert resp.json() == {"status": "ok"}

        asyncio.run(_run())

    def test_models_endpoint(self):
        async def _run():
            async with self._client() as client:
                resp = await client.get("/v1/models")
                assert resp.status_code == 200
                data = resp.json()
                assert data["object"] == "list"
                assert len(data["data"]) == 1
                assert data["data"][0]["id"] == "truthbattle-lean-sympy"

        asyncio.run(_run())

    def test_chat_completions_non_streaming(self):
        async def _run():
            async with self._client() as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={
                        "messages": [
                            {"role": "user", "content": "solve x^2 - 1 = 0"}
                        ],
                        "stream": False,
                    },
                )
                assert resp.status_code == 200
                body = resp.json()

                # OpenAI-compatible structure
                assert body["object"] == "chat.completion"
                assert body["model"] == "truthbattle-lean-sympy"
                assert len(body["choices"]) == 1
                assert body["choices"][0]["message"]["role"] == "assistant"
                assert body["choices"][0]["finish_reason"] == "stop"

                content = body["choices"][0]["message"]["content"]
                assert "x" in content  # Should contain a solution

                # TruthBattle extensions
                assert "truthbattle_trace" in body
                assert "truthbattle_verdict" in body
                assert body["truthbattle_verdict"]["verdict"] in {"pass", "partial", "fail"}

                # Trace should have expected nodes
                trace_nodes = [t["node"] for t in body["truthbattle_trace"]]
                assert "ingest" in trace_nodes
                assert "parse" in trace_nodes
                assert "compose" in trace_nodes

        asyncio.run(_run())

    def test_chat_completions_streaming(self):
        async def _run():
            async with self._client() as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={
                        "messages": [
                            {"role": "user", "content": "solve x + 1 = 0"}
                        ],
                        "stream": True,
                    },
                )
                assert resp.status_code == 200
                assert "text/event-stream" in resp.headers.get("content-type", "")

                # Parse SSE events from the response body
                raw = resp.content.decode("utf-8")
                events = [
                    line.strip()
                    for line in raw.split("\n\n")
                    if line.strip()
                ]
                assert len(events) >= 3  # at least role + content + stop + DONE

                # First event must set role
                first_data = events[0].removeprefix("data: ")
                first = json.loads(first_data)
                assert first["choices"][0]["delta"]["role"] == "assistant"

                # Last must be [DONE]
                assert events[-1] == "data: [DONE]"

                # Second-to-last must be finish_reason=stop
                stop_data = events[-2].removeprefix("data: ")
                stop = json.loads(stop_data)
                assert stop["choices"][0]["finish_reason"] == "stop"

        asyncio.run(_run())

    def test_chat_completions_empty_messages_returns_400(self):
        async def _run():
            async with self._client() as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={"messages": [], "stream": False},
                )
                assert resp.status_code == 400

        asyncio.run(_run())

    def test_chat_completions_image_content_structure(self):
        """Test with OpenAI multi-part content (text + image_url)."""
        async def _run():
            async with self._client() as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "solve x^2 = 4"},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": "https://example.com/math.png"
                                        },
                                    },
                                ],
                            }
                        ],
                        "stream": False,
                    },
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["choices"][0]["message"]["content"]

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# 6. Middleware console log output
# ---------------------------------------------------------------------------

class TestMiddlewareLogging:
    """Test that the log_requests middleware prints [truthbattle] console logs."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        _apply_core_monkeypatches(monkeypatch)

    def test_request_log_printed(self, monkeypatch, capsys):
        async def _run():
            from httpx import ASGITransport, AsyncClient
            from truthbattle.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

        asyncio.run(_run())
        captured = capsys.readouterr()
        assert "[truthbattle]" in captured.out
        assert "GET" in captured.out
        assert "/health" in captured.out

    def test_input_summary_log(self, monkeypatch, capsys):
        async def _run():
            from httpx import ASGITransport, AsyncClient
            from truthbattle.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/v1/chat/completions",
                    json={
                        "messages": [
                            {"role": "user", "content": "solve x = 1"}
                        ],
                        "stream": False,
                    },
                )

        asyncio.run(_run())
        captured = capsys.readouterr()
        assert "input_summary" in captured.out
        assert "prompt_chars=" in captured.out
        assert "images=" in captured.out


# ---------------------------------------------------------------------------
# 7. Trace node completeness for different modes
# ---------------------------------------------------------------------------

class TestTraceNodes:
    """Verify trace contains expected nodes for different pipeline paths."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        _apply_core_monkeypatches(monkeypatch)

    def test_solve_trace_has_all_nodes(self):
        result = asyncio.run(run_tutor("solve x^2 - 4 = 0"))
        nodes = [n.node for n in result.trace]
        for expected in ["ingest", "parse", "tools", "lean_first", "sympy", "verify", "graph", "compose"]:
            assert expected in nodes, f"Missing node {expected} in trace: {nodes}"

    def test_explain_trace_nodes(self):
        result = asyncio.run(run_tutor("hello"))
        nodes = [n.node for n in result.trace]
        assert "ingest" in nodes
        assert "parse" in nodes
        assert "compose" in nodes

    def test_ode_trace_has_lean_unsupported(self):
        result = asyncio.run(run_tutor("dy/dx = x + y"))
        nodes = [n.node for n in result.trace]
        assert "lean_first" in nodes
        lean_trace = next(n for n in result.trace if n.node == "lean_first")
        # ODE Lean bridge is not implemented
        assert lean_trace.payload.get("status") in {"unsupported", "ok", "skipped"}

    def test_trace_statuses_are_valid(self):
        result = asyncio.run(run_tutor("solve x^2 - 9 = 0"))
        valid_statuses = {"ok", "pass", "partial", "fail", "skipped", "unsupported", "error"}
        for node in result.trace:
            assert node.status in valid_statuses, (
                f"Node {node.node} has invalid status: {node.status}"
            )

    def test_trace_payloads_are_dicts(self):
        result = asyncio.run(run_tutor("solve x^2 - 1 = 0"))
        for node in result.trace:
            assert isinstance(node.payload, dict), (
                f"Node {node.node} payload is {type(node.payload)}, expected dict"
            )


# ---------------------------------------------------------------------------
# 8. Result structure validation
# ---------------------------------------------------------------------------

class TestResultStructure:
    """Verify the TutorResult has all expected fields populated."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        _apply_core_monkeypatches(monkeypatch)

    def test_solve_result_fields(self):
        result = asyncio.run(run_tutor("solve x^2 - 1 = 0"))
        assert isinstance(result, TutorResult)
        assert result.task.task_type == "solve"
        assert result.sympy["status"] == "ok"
        assert isinstance(result.sympy["solutions"], list)
        assert len(result.sympy["solutions"]) > 0
        assert result.verdict["verdict"] in {"pass", "partial", "fail"}
        assert isinstance(result.verdict["confidence"], (int, float))
        assert result.final_answer
        assert result.raw_question == "solve x^2 - 1 = 0"

    def test_ode_result_fields(self):
        result = asyncio.run(run_tutor("dy/dx = sin(x)"))
        assert result.task.task_type == "ode"
        assert result.sympy["status"] in {"ok", "error"}
        assert result.final_answer
        assert result.verdict["verdict"] in {"pass", "partial", "fail"}

    def test_explain_result_fields(self):
        result = asyncio.run(run_tutor("what is math"))
        assert result.task.task_type == "explain"
        assert result.final_answer

    def test_result_verdict_has_required_keys(self):
        result = asyncio.run(run_tutor("solve x = 5"))
        verdict = result.verdict
        for key in ["verdict", "confidence"]:
            assert key in verdict, f"Missing verdict key: {key}"


# ---------------------------------------------------------------------------
# 9. Display math in final output
# ---------------------------------------------------------------------------

class TestDisplayMathInOutput:
    """Verify that final answers use display-math LaTeX, not inline backticks."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        _apply_core_monkeypatches(monkeypatch)

    def test_solve_answer_uses_display_math(self):
        result = asyncio.run(run_tutor("solve x^2 - 1 = 0"))
        # Answer mode should use $$ display math blocks
        assert "$$" in result.final_answer, (
            f"Expected display math in answer, got: {result.final_answer[:200]}"
        )

    def test_ode_answer_uses_display_math(self):
        result = asyncio.run(run_tutor("dy/dx = sin(x)"))
        if result.sympy["status"] == "ok":
            assert "$$" in result.final_answer, (
                f"Expected display math in ODE answer, got: {result.final_answer[:200]}"
            )

    def test_evidence_mode_has_verdict_line(self):
        result = asyncio.run(
            run_tutor("[tb: mode=evidence] solve x^2 - 4 = 0")
        )
        assert "Verdict:" in result.final_answer
        assert "Confidence:" in result.final_answer


# ---------------------------------------------------------------------------
# 10. Streaming with different output modes
# ---------------------------------------------------------------------------

class TestStreamingModes:
    """Test streaming behaviour varies correctly by output mode."""

    def _collect_stream(self, monkeypatch, question):
        _apply_core_monkeypatches(monkeypatch)
        items: list[str | TutorResult] = []

        async def _collect():
            async for item in run_tutor_stream(question):
                items.append(item)

        asyncio.run(_collect())
        return items

    def test_evidence_mode_stream(self, monkeypatch):
        items = self._collect_stream(
            monkeypatch, "[tb: mode=evidence] solve x^2 - 1 = 0"
        )
        result = [i for i in items if isinstance(i, TutorResult)][0]
        assert "## LEAN Layer" in result.final_answer
        assert "## SymPy Layer" in result.final_answer

    def test_teach_mode_stream(self, monkeypatch):
        items = self._collect_stream(
            monkeypatch, "solve x^2 - 1 = 0, step by step"
        )
        result = [i for i in items if isinstance(i, TutorResult)][0]
        assert "## Atomic Walkthrough" in result.final_answer

    def test_answer_mode_stream_is_compact(self, monkeypatch):
        items = self._collect_stream(
            monkeypatch, "[tb: mode=answer] solve x^2 - 1 = 0"
        )
        result = [i for i in items if isinstance(i, TutorResult)][0]
        assert "## Final Answer" not in result.final_answer
        assert "## LEAN Layer" not in result.final_answer
