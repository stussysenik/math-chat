# TruthBattle Math Tutor

**Lean-first + SymPy verified math tutor with OpenAI-compatible API**

Every math query flows through a formal verification pipeline:
Parse -> Lean formalize -> SymPy compute -> Verify -> Graph -> Respond

## Pipeline

```
User prompt --> [Ingest] --> [Vision?] --> [Parse] --> [Lean 4]
                                                          |
                    [Compose] <-- [Graph] <-- [Verify] <-- [SymPy]
```

| Stage | What it does |
|-------|-------------|
| Lean-first | Compile formal residual function, prove rational solutions via `native_decide` |
| SymPy | Symbolic solve/simplify/diff/integrate/ode with repair loops |
| Verify | Aggregate evidence into pass/partial/fail with confidence scoring |
| Graph | Desmos expressions + Mafs specs for visualization |
| Tools | Deterministic word-problem solver + Wolfram Alpha fallback |
| Vision | GLM-4.6v multi-image math extraction |

## Stack

- **Backend**: FastAPI + SymPy + Lean 4 + GLM-4.7
- **UI**: OpenWebUI (wired to backend)
- **Package manager**: uv

## Quick Start

```bash
# 1. Install deps
uv sync

# 2. Install OpenWebUI
uv tool install --python 3.11 open-webui

# 3. Configure
cp .env.example .env
# Set GLM_BASE_URL, GLM_API_KEY, GLM_MODEL

# 4. Run backend (:8080)
uv run truthbattle-api

# 5. Run UI (:3000)
./scripts/run-openwebui.sh
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/v1/models` | List models |
| POST | `/v1/chat/completions` | Chat (stream + non-stream) |

Model ID: `truthbattle-lean-sympy`

## Runtime Controls

Per-message directives — auto-inferred or explicit:

```
[tb: mode=evidence lean=on sympy=on verify=on graph=on]
```

| Mode | Behavior |
|------|----------|
| `answer` | Compact result (default) |
| `teach` | Socratic step-by-step with recursive question loop |
| `evidence` | Full Lean + SymPy + Graph + Verdict ledger |

Slash form: `/tb mode=teach lean=off`

## Testing

```bash
uv run pytest -q              # unit tests
./scripts/e2e-tail.sh         # e2e with log tailing
```

## Documentation

| File | Contents |
|------|----------|
| [docs.md](docs.md) | Architecture, layer map, design decisions |
| [progress.md](progress.md) | Status tracker, roadmap, git layer guide |
| [PROMPTS.md](PROMPTS.md) | LLM system prompts (Orchestrator, Parser, Vision, Tutor, Verifier) |
| [THETAWISE_PLUS_PLAN.md](THETAWISE_PLUS_PLAN.md) | Evidence chain architecture plan |
| [DEEPSEEK_PUTNAM_NOTES.md](DEEPSEEK_PUTNAM_NOTES.md) | Formal verification loop design notes |

## Git Layers

This repo uses stacked commits organized by feature layer:

```
15. Documentation        README, docs, progress, design notes
14. AI Tooling           Claude Code + OpenSpec workflow configs
13. OpenSpec             Spec-driven change proposals
12. Tests                Unit + integration test suite
11. Scripts              run-api, run-openwebui, e2e-tail
10. Legacy Modules       Early prototypes (pre-truthbattle)
 9. API Server           FastAPI, OpenAI-compatible endpoints
 8. Pipeline             Full orchestration, streaming, modes
 7. Tool Layer           Word problems, Wolfram fallback
 6. Verification         Verdict aggregation, Desmos + Mafs
 5. Symbolic Engines     SymPy computation, Lean 4 proofs
 4. NLP Parsing          Heuristic + GLM task extraction
 3. Input Processing     Message ingestion, GLM API
 2. Core Types           TaskSpec, prompts, data models
 1. Foundation           pyproject.toml, env, deps
```
