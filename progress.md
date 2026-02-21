# Progress Tracker

## Current Status: v0.1.0 — Core Pipeline Complete

### What Works

- [x] **FastAPI server** — OpenAI-compatible `/v1/chat/completions` (stream + non-stream)
- [x] **NLP parsing** — heuristic regex + GLM-4.7 fallback for solve/simplify/diff/integrate/ode/explain
- [x] **SymPy engine** — full symbolic execution with residual checks and repair loops
- [x] **Lean 4 engine** — residual compilation + `native_decide` proofs for rational solutions
- [x] **Verification** — evidence aggregation with pass/partial/fail verdicts and confidence scoring
- [x] **Graph generation** — Desmos expressions + Mafs specs for all task types
- [x] **Vision input** — GLM-4.6v multi-image extraction with timeout + retry
- [x] **Word problems** — deterministic inclined-plane friction solver with kinematics
- [x] **Wolfram fallback** — async query with configurable timeout
- [x] **Three output modes** — answer (compact), teach (Socratic), evidence (full ledger)
- [x] **Runtime directives** — per-message `[tb: ...]` and `/tb` control
- [x] **OpenWebUI integration** — wired via scripts, model appears in UI
- [x] **Test suite** — 13 test files covering all modules

### What's Partial

- [ ] **Lean ODE bridge** — marked unsupported; ODE verification is SymPy-only
- [ ] **Non-rational Lean proofs** — irrational/complex roots skip formal proof (marked `partial`)
- [ ] **Word problem coverage** — only inclined-plane friction; needs expansion
- [ ] **GLM dependency** — parsing/repair/vision all require GLM endpoint; no offline fallback

### Roadmap (OpenSpec Proposals)

| Proposal | Status | Description |
|----------|--------|-------------|
| **DSPy Batch Orchestrator** | proposed | DSPy-based orchestration + RabbitMQ worker queue + OpenWebUI native UI |
| **Seminar Batch Engine** | proposed | Nim-based batch engine + Wolfram/Octave provers + seminar book layout |
| **Rich Presentation UI** | proposed | Rich rendering + dev-mode telemetry dashboard |

### Git Layers (Stacked Commits)

This repo is organized as stacked feature layers for clean code review:

| # | Layer | What It Contains |
|---|-------|-----------------|
| 1 | Foundation | pyproject.toml, .env.example, .gitignore, uv.lock |
| 2 | Core Types | TaskSpec, NodeTrace, TutorResult, LLM prompts |
| 3 | Input Processing | Message ingestion, GLM API integration |
| 4 | NLP Parsing | Heuristic + GLM task extraction, ODE detection |
| 5 | Symbolic Engines | SymPy computation, Lean 4 formal proofs |
| 6 | Verification & Graphs | Verdict aggregation, Desmos + Mafs output |
| 7 | Tool Layer | Word problem solver, Wolfram Alpha fallback |
| 8 | Pipeline | Full orchestration, streaming, mode routing |
| 9 | API Server | FastAPI endpoints, OpenAI compatibility |
| 10 | Legacy Modules | Early prototypes (pre-truthbattle package) |
| 11 | Scripts | run-api, run-openwebui, e2e-tail |
| 12 | Tests | Unit + integration test suite |
| 13 | OpenSpec | Spec-driven change proposals |
| 14 | AI Tooling | Claude Code + OpenSpec workflow configs |
| 15 | Documentation | README, docs, progress, design notes |
