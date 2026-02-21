# Architecture Documentation

## System Overview

TruthBattle is a **Lean-first + SymPy verified math tutor** exposed as an OpenAI-compatible API. Every mathematical query flows through a formal verification pipeline before reaching the user.

```
User prompt
  |
  v
[Ingest] --> extract text + images from OpenAI-style messages
  |
  v
[Vision] --> GLM-4.6v extracts math from images (optional)
  |
  v
[Parse] --> heuristic regex + GLM-4.7 fallback --> TaskSpec
  |
  v
[Lean-first] --> compile formal residual function in Lean 4
  |
  v
[SymPy] --> symbolic solve/simplify/diff/integrate/ode
  |           + repair loop on failure
  v
[Verify] --> aggregate evidence --> pass | partial | fail
  |
  v
[Graph] --> Desmos expressions + Mafs specs
  |
  v
[Compose] --> evidence / teach / answer mode output
  |
  v
FastAPI response (stream or non-stream)
```

## Layer Map

| Layer | Module(s) | Purpose |
|-------|-----------|---------|
| 1 - Foundation | `pyproject.toml`, `.env.example` | Project config, deps, env vars |
| 2 - Core Types | `types.py`, `prompts.py` | TaskSpec, NodeTrace, TutorResult, LLM prompts |
| 3 - Input | `ingest.py`, `glm.py` | Message extraction, GLM API calls |
| 4 - NLP | `nlp.py` | Heuristic + GLM task parsing, ODE detection |
| 5 - Engines | `sympy_engine.py`, `lean_engine.py` | Symbolic computation + formal proofs |
| 6 - Verification | `verifier.py`, `graph_engine.py` | Verdict aggregation, Desmos/Mafs output |
| 7 - Tools | `tool_layer.py`, `word_problems.py` | Deterministic solvers, Wolfram fallback |
| 8 - Pipeline | `pipeline.py` | Full orchestration, streaming, mode routing |
| 9 - API | `main.py` | FastAPI server, OpenAI-compatible endpoints |

## Key Design Decisions

### Lean-first, not Lean-only
Lean 4 compiles a residual function for every symbolic query. Rational solutions get full `native_decide` proofs. Non-rational roots fall back to SymPy symbolic verification and are marked `partial` — never `pass`.

### Repair Loops
When SymPy fails on a parsed task, the pipeline sends the error back through GLM for task repair (up to N retries). This catches NLP-to-symbolic translation errors without user intervention.

### Three Output Modes
- **answer**: compact result (default)
- **teach**: Socratic step-by-step with recursive question loop
- **evidence**: full Lean + SymPy + Graph + Verdict ledger

Mode is auto-inferred from prompt keywords or set explicitly via `[tb: mode=...]` directives.

### Conservative Verification
The verifier never over-claims. No evidence = no claim. Conflicts between engines produce `partial` verdicts with explicit `missing_proofs` and `next_checks`.

## File Structure

```
src/truthbattle/          # Main package (layers 2-9)
  __init__.py
  types.py                # Data models: TaskSpec, NodeTrace, TutorResult
  prompts.py              # All LLM system prompts
  ingest.py               # OpenAI message content extraction
  glm.py                  # GLM API: parse, repair, vision, tutor
  nlp.py                  # Heuristic + GLM task parsing
  sympy_engine.py         # SymPy: solve, ode, simplify, diff, integrate
  lean_engine.py          # Lean 4: residual compilation, proof generation
  verifier.py             # Evidence aggregation, verdict scoring
  graph_engine.py         # Desmos + Mafs graph artifact generation
  tool_layer.py           # Tool routing, Wolfram Alpha fallback
  word_problems.py        # Deterministic physics word problem solver
  pipeline.py             # Full orchestration pipeline
  main.py                 # FastAPI application entry point

src/                      # Legacy standalone modules (pre-truthbattle)
  desmos.py, solver.py, verifier.py, schema.py,
  socratic.py, worker.py, tool.py, wolfram.py

tests/                    # Unit + integration tests
scripts/                  # run-api.sh, run-openwebui.sh, e2e-tail.sh
openspec/                 # Spec-driven change proposals
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/v1/models` | List available models |
| POST | `/v1/chat/completions` | Chat completions (stream + non-stream) |

Model ID: `truthbattle-lean-sympy`

## Runtime Directives

Per-message control via inline directives:

```
[tb: mode=evidence lean=on sympy=on verify=on graph=on vision=on trace=on]
```

Or slash form: `/tb mode=teach lean=off`

## Environment Variables

See `.env.example` for the full list. Key groups:
- **GLM endpoints**: `GLM_BASE_URL`, `GLM_API_KEY`, `GLM_MODEL`, `GLM_VISION_MODEL`
- **Feature toggles**: `TB_ENABLE_LEAN`, `TB_ENABLE_SYMPY`, `TB_ENABLE_GRAPH`, etc.
- **Timeouts**: `TB_VISION_TIMEOUT_SECONDS`, `TB_PARSE_TIMEOUT_SECONDS`, etc.
- **Wolfram**: `WOLFRAM_APP_ID`
