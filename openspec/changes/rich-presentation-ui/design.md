## Context
The deterministic math engine successfully parses extracted tokens, verifies them against numerical sweeps, and outputs raw LaTeX. However, the exact prompt string formatting (relying on raw text instruction "output DaisyUI") is brittle. We need structured outputs via Zod schemas so the frontend can natively build the rich presentation, and we need DSPy logic to reliably tune the LLM's Socratic "Origami backwards" generation.

## Goals / Non-Goals
**Goals:**
- Enforce structured JSON output (`pydantic` / `zod` equivalent schemas) for the final Socratic Explainer prompt to ensure deterministic frontend rendering.
- Build the "Menu Recipe" using DaisyUI HTML templates in the frontend by binding strictly to the returned schema keys.
- Integrate Dev Mode feature flags to allow users to toggle raw token/residual telemetry vs. pedagogical views.

**Non-Goals:**
- Completely rewriting the underlying SymPy solver.
- Changing the extraction pipeline in this change.

## Decisions
- **Decision:** Shift from raw String prompt injection to a formal Pydantic Model (Zod schemas on the JS side) for the `SocraticExplainer` return type.
  - *Rationale*: A raw markdown block can easily break DaisyUI class assumptions. A JSON structure `html_lean_card`, `terminal_sympy_log`, `feynman_explanation` mapping exactly to the UI components guarantees resilience.
- **Decision:** Implement Dev Mode via a simple boolean flag in the pipeline that appends the telemetry payload to a generic UI component, conditionally rendered.

## Risks / Trade-offs
- Risk: Forcing the LLM into a strict JSON payload might reduce its conversational fluidity.
- Mitigation: Provide a specific "feynman_explanation" free-text string key inside the schema that allows it to generate unconstrained Markdown, while keeping the UI scaffold strict.
