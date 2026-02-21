## Context

The current Python/SymPy/DaisyUI architecture excels at immediate, simplistic real-time ODE and Algebraic walkthroughs. However, when faced with textbook setups containing extreme multi-part algebraic arrays (e.g., recursive sequences, limit generating functions, combinatorial logic like the Fibonacci Rabbit problem), the real-time SSE streamer becomes a liability. SymPy alone lacks the raw automated proving power of GNU Octave for matrix/sequence sweeps and Wolfram Alpha for deep symbolic limit proofs. We need to restructure the backend as an asynchronous, headless batch processor written in a highly efficient compiled language like `Nim`, and present the output in a static, deeply structured "Seminar Book" format horizontally and vertically using pure `LaTeX` and `Maf.js`.

## Goals / Non-Goals

**Goals:**
- Replace Python `asyncio` SSE stream with a Nim-based message queue / batch worker system.
- Introduce GNU Octave for numerical combinatorial/sequence limit proofs.
- Introduce Wolfram Alpha API for deep algebraic algebraic validation where SymPy falls short.
- Migrate the frontend UI layer away from DaisyUI components and chat interfaces into a static, horizontal-vertical seminar format rendered tightly with `Maf.js`.

**Non-Goals:**
- We are *not* keeping the real-time streaming feedback loop. The math payload is validated fully offline before the user sees anything.
- We are *not* migrating the actual core Python solver code to Nim; Nim will orchestrate the Python scripts, Octave instances, and HTTP requests.

## Decisions

- **Nim for Orchestration:** Nim is lightweight, compiled, and highly interoperable. It will serve as the master controller pulling jobs, calling Python/Octave, and building the final JSON artifact.
- **GNU Octave over SciPy for Sequences:** Octave natively supports the vectorized, deep recursive limit checks needed for textbook combinatorics without custom Python boilerplate.
- **Maf.js for UI:** The current chat constraint forces vertical scrolling. `Maf.js` will allow us to break mathematical "cards" out horizontally corresponding to a single thought, and vertically for progression, mimicking postgraduate math handouts.

## Risks / Trade-offs

- **Development Time:** Transitioning to batched Nim orchestration is a 6-month epic.
- **Response Latency:** Users will not see mathematical generation "typing" out. They will wait (potentially 30s-1m) for a complete, verified "Chapter" to appear.
- **Complexity:** Managing Wolfram API keys, headless Octave processes, and Nim compiles introduces significant DevOps overhead compared to pure Python.
