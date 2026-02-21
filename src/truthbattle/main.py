from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator  # noqa: F811 (also used from pipeline)
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from truthbattle.ingest import extract_latest_user_input
from truthbattle.pipeline import run_tutor, run_tutor_stream
from truthbattle.types import TutorResult

load_dotenv()
MODEL_ID = "truthbattle-lean-sympy"
app = FastAPI(title="TruthBattle Math Tutor API", version="0.1.0")


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None


@app.middleware("http")
async def log_requests(request, call_next):
    started = time.time()
    response = await call_next(request)
    elapsed_ms = (time.time() - started) * 1000
    print(
        f"[truthbattle] {request.method} {request.url.path} -> {response.status_code} ({elapsed_ms:.1f} ms)",
        flush=True,
    )
    return response


def _response_payload(
    text: str,
    model: str = MODEL_ID,
    trace: list[dict[str, Any]] | None = None,
    verdict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
    if trace is not None:
        payload["truthbattle_trace"] = trace
    if verdict is not None:
        payload["truthbattle_verdict"] = verdict
    return payload


async def _stream_chunks(text: str, model: str) -> AsyncGenerator[bytes, None]:
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    first = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
        ],
    }
    yield f"data: {json.dumps(first)}\n\n".encode()

    chunk_size = 180
    for i in range(0, len(text), chunk_size):
        line = text[i : i + chunk_size]
        chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {"index": 0, "delta": {"content": line}, "finish_reason": None}
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n".encode()

    end = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(end)}\n\n".encode()
    yield b"data: [DONE]\n\n"


def _sse_content(
    chunk_id: str, created: int, model: str, content: str
) -> bytes:
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {"index": 0, "delta": {"content": content}, "finish_reason": None}
        ],
    }
    return f"data: {json.dumps(chunk)}\n\n".encode()


async def _stream_progressive(
    gen: AsyncGenerator[Any, None], model: str
) -> AsyncGenerator[bytes, None]:
    """Consume run_tutor_stream and emit SSE events progressively.

    Progress strings are streamed as they arrive. The final TutorResult's
    final_answer is chunked at the end, separated by a horizontal rule.
    """
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    first = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
        ],
    }
    yield f"data: {json.dumps(first)}\n\n".encode()

    has_progress = False
    try:
        async for item in gen:
            if isinstance(item, str):
                has_progress = True
                yield _sse_content(chunk_id, created, model, item)
            elif isinstance(item, TutorResult):
                if has_progress:
                    yield _sse_content(chunk_id, created, model, "\n---\n\n")
                text = item.final_answer
                chunk_size = 180
                for i in range(0, len(text), chunk_size):
                    yield _sse_content(
                        chunk_id, created, model, text[i : i + chunk_size]
                    )
    except Exception as e:
        error_text = (
            "\n\n## Final Answer\n"
            "The request could not complete symbolic parsing for this turn. "
            f"Error: {e}\n\n"
            "- Verdict: `fail`\n"
            "- Confidence: `0.1`\n"
        )
        yield _sse_content(chunk_id, created, model, error_text)

    end = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(end)}\n\n".encode()
    yield b"data: [DONE]\n\n"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
def list_models() -> dict:
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "created": now,
                "owned_by": "truthbattle",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    model = req.model or MODEL_ID
    try:
        if not req.messages:
            raise HTTPException(status_code=400, detail="messages must not be empty")

        prompt, image_urls = extract_latest_user_input(req.messages)
        if not prompt.strip() and not image_urls:
            raise HTTPException(status_code=400, detail="could not find user prompt")
        if not prompt.strip() and image_urls:
            prompt = "Solve the math problem from the attached image."
        first_image = image_urls[0] if image_urls else ""
        image_kind = (
            "data-url"
            if first_image.startswith("data:image/")
            else (
                "local-url"
                if "127.0.0.1" in first_image or "localhost" in first_image
                else "remote-url"
            )
        )
        print(
            f"[truthbattle] input_summary prompt_chars={len(prompt)} images={len(image_urls)} first_image_kind={image_kind}",
            flush=True,
        )

        forward_headers = {
            k.lower(): v
            for k, v in request.headers.items()
            if k.lower() in {"authorization", "cookie"}
        }

        if req.stream:
            gen = run_tutor_stream(
                prompt,
                image_urls=image_urls,
                forward_headers=forward_headers,
            )
            return StreamingResponse(
                _stream_progressive(gen, model), media_type="text/event-stream"
            )

        tutor = await run_tutor(
            prompt,
            image_urls=image_urls,
            forward_headers=forward_headers,
        )
        text = tutor.final_answer
        trace = [t.__dict__ for t in tutor.trace]
        return JSONResponse(
            _response_payload(text, model, trace=trace, verdict=tutor.verdict)
        )
    except HTTPException:
        raise
    except Exception as e:
        text = (
            "## Final Answer\n"
            "The request could not complete symbolic parsing for this turn. "
            "Please retry with a clearer math prompt or image.\n\n"
            "- Verdict: `fail`\n"
            "- Confidence: `0.1`\n"
        )
        trace = [
            {
                "node": "fatal",
                "status": "error",
                "summary": "Unhandled exception was caught and converted to JSON response.",
                "payload": {"error": str(e)},
            }
        ]
        verdict = {
            "verdict": "fail",
            "confidence": 0.1,
            "issues": [str(e)],
            "accepted_claims": [],
            "missing_proofs": ["Pipeline execution failed before verification."],
            "next_checks": [
                "Retry prompt with explicit symbolic target or clearer image."
            ],
        }
        if req.stream:
            return StreamingResponse(
                _stream_chunks(text, model), media_type="text/event-stream"
            )
        return JSONResponse(
            _response_payload(text, model, trace=trace, verdict=verdict)
        )


def run() -> None:
    import uvicorn

    uvicorn.run("truthbattle.main:app", host="0.0.0.0", port=8080, reload=False)
