## 1. DSPy Orchestration Pipeline

- [x] 1.1 Install `dspy` via `uv add` and remove raw LLM API client wrappers from `src/socratic.py`.
- [x] 1.2 Define `dspy.Signature` formats for the `Reverse Origami` logic flow.
- [x] 1.3 Refactor the Explainer into a compiled `dspy.Module` that accepts the verified JSON math node and yields the resulting Socratic textual breakdown.

## 2. RabbitMQ & Asynchronous Task Queues

- [x] 2.1 Set up a `celery` or `fastapi` background task queue integrating a local RabbitMQ/Redis broker.
- [x] 2.2 Re-architect the main API endpoint to ingest the Math Payload and return an asynchronous `job_id`.
- [x] 2.3 Implement the worker function to run the `SymPy` solver and DSPy generator fully decoupled from the HTTP response loop.

## 3. OpenWebUI Semantic Integration

- [x] 3.1 Strip all DaisyUI string literals from the existing codebase prompts.
- [x] 3.2 Update the `SocraticUIBlock` Pydantic schema in `src/schema.py` to match the exact ID-Message `v1` payload OpenWebUI expects for tools.
- [x] 3.3 Ensure the worker node emits the final JSON precisely formatted for horizontal/vertical nested UI rendering inside OpenWebUI.

## 4. Wolfram Alpha API Prover 

- [x] 4.1 Scaffold a `wolfram` module extending the Numerical Verifier to prove sequence limits and generating functions (like the Fibonacci problem) using the `wolframalpha` python library.
