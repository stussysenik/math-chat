## 1. Schema & Structured Outputs

- [x] 1.1 Update `src/schema.py` to include a new `SocraticUIBlock` Pydantic model for strict JSON extraction.
- [x] 1.2 Define the UI components within the model string fields (e.g. `lean_validation`, `sympy_terminal`, `feynman_explanation`).

## 2. Dev Mode Telemetry

- [x] 2.1 Update `DeterministicPipelineStreamer` in `src/streamer.py` and `solver.py` to capture exact residual outputs and tolerance limits.
- [x] 2.2 Wire up the `dev_mode` flag to conditionally inject these metrics into the final JSON output payload.

## 3. Pedagogical Explainer Overhaul

- [x] 3.1 Refactor `src/socratic.py` to enforce the generation of the `SocraticUIBlock` model.
- [x] 3.2 Inject the "Reverse Origami" instruction explicitly mapping to the `feynman_explanation` field.
- [x] 3.3 Ensure prompt explicitly enforces DaisyUI classes and `electric_green` (`#00ff00`) highlights where appropriate within the textual payload.

## 4. Robust SymPy & Latex Parsing

- [x] 4.1 Improve `src/solver.py` AST/string parsing capabilities to gracefully handle complex strings like Laplace notation (`L{...}`).
- [x] 4.2 Enforce strict LaTeX string formatting on the way out to guarantee clean frontend rendering via standard Desmos and Katex components.
- [x] 4.3 Expand tests in `tests/test_streamer_pipeline.py` and `tests/test_solver.py` to cover Laplace and probability domains mimicking the failures seen in recent image uploads.
