## Why

The deterministic math pipeline is currently bound to Python streaming and simple SymPy algebra. However, to handle complex, seminar-style problems (e.g., recursive Fibonacci sequence generation, advanced generating functions shown in textbook sets), we need a massive capacity upgrade. We must transition from a lightweight real-time SSE streamer to a heavy, batched, "seminar book" generator. This architecture will pre-verify massive chunks of mathematics offline using powerful combinatorial engines (GNU Octave, Wolfram Alpha) and serialize them into beautiful, highly structured horizontal-vertical reading interfaces powered by `Maf.js` and strict LaTeX. To maintain productivity and speed over this 6-month epic, the core orchestration logic will be migrated to `Nim`.

## What Changes

- **BREAKING:** Rip out the real-time SSE streaming architecture. The frontend will no longer expect live progressive updates.
- **BREAKING:** Deprecate DaisyUI classes in favor of a custom, horizontal-vertical seminar book CSS/JS grid driven by `Maf.js`.
- Introduce GNU Octave and the Wolfram Alpha API to the Verification layer to handle combinatorics, sequence limit proofs, and recursion.
- Re-architect the backend glue and worker queues in `Nim` to handle the batch processing workloads efficiently.

## Capabilities

### New Capabilities
- `seminar-book-layout`: A new Maf.js/LaTeX powered rendering engine to layout math problems left-to-right, then down, mirroring postgraduate textbooks.
- `nim-batch-orchestrator`: A Nim-based high-performance job queue to dispatch complex algebraic validation to Octave/Wolfram.
- `wolfram-octave-provers`: Integration of rigorous numerical engines to prove recursive sequences and limit theorems.

### Modified Capabilities
- `socratic-explainer`: Shift from chat-based SSE prompts to massive, monolithic "chapter section" generations.

## Impact

- Retires `src/streamer.py`.
- Replaces parts of Python `src/solver.py` with Nim counterparts.
- Drastically changes frontend DOM assumptions.
