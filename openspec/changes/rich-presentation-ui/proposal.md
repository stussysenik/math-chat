## Why

The deterministic math pipeline is solidly built, but the textual output and information architecture needs to be upgraded. We are upgrading the visual layer to mimic Karpathy's research-style deep dives using an "Origami backwards" approach. This ensures students see the verification (LEAN, SymPy) explicitly, and explanations are presented via a structured, visually engaging menu recipe adorned with DaisyUI elements and electric green highlights for maximum clarity.

## What Changes

- Redesign the LLM prompt to output a highly structured "Menu Recipe" response layout.
- Introduce `dev_mode` feature flags to expose raw pipeline telemetry (max residuals, SymPy nodes) directly in the UI.
- Style the Socratic output using DaisyUI and Tailwind utility classes (e.g., `text-[#00ff00]`) to create an electric green highlight effect for mathematical validations.

## Capabilities

### New Capabilities
- `rich-presentation`: Introduces a structured UI recipe for Socratic mathematical explanations, complete with DaisyUI format.
- `dev-mode-telemetry`: Feature toggle that exposes the raw algorithmic boundaries and pipeline checks.

### Modified Capabilities

## Impact

- Modifies the `SocraticExplainer` logic in `src/socratic.py`.
- Alters the Server-Sent Events (SSE) output expected by frontends.
- Frontends using this tool must support rendering raw HTML/Markdown combined with DaisyUI classes.
