## ADDED Requirements

### Requirement: Structured Verification Output Schema
The Socratic Explainer SHALL output strictly typed JSON mapping to physical UI modules (`LEAN Validation`, `SymPy Terminal`, `Graphical Insight`, `Origami Explanation`), rather than a single bulk markdown string.

#### Scenario: Socratic Pipeline Rendered
- **WHEN** the determinist SymPy pipeline yields a successful verified solution payload.
- **THEN** it generates a validation schema (which aligns with frontend Zod bindings) to seamlessly plug into DaisyUI templates.

### Requirement: DaisyUI Electric Green Aesthetics
The system SHALL mandate that success verification UI tokens natively utilize the color hex `#00ff00` (electric green equivalent) in the structured output template for validation highlights.

#### Scenario: Visual Truth Confirmation
- **WHEN** LEAN-lite checks return a zero-residual exact answer.
- **THEN** the `LEAN Validation` UI block applies an `electric_green` success styling tag as per the structured return.

### Requirement: Reverse Origami Pedagogy Flow
The LLM explainer logic SHALL be restricted to constructing atomic, Feynman-like reverse derivations from the pre-computed mathematical truth.

#### Scenario: Formulating the Explanation
- **WHEN** the numerical verification generates the correct solution.
- **THEN** the explainer prompt enforces a "reverse origami" reasoning trace that only breaks down the algebraic/calculus rules, never guessing the actual numbers.
