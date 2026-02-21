## CHANGED Requirements

### Requirement: Socratic Explainer Role
Previously, the Socratic Explainer streamed Markdown chunks directly to the UI. It MUST now generate massive, highly-structured Chapter Sections mapped precisely to the `Maf.js` grid.

#### Scenario: Explaining the Rabbit Problem
- **WHEN** the Socratic explainer receives the Octave-verified Fibonacci limit ($a_{12} = 233$).
- **THEN** it generates a strict JSON payload containing standalone LaTeX explanations that do not rely on chat continuity, but form a static "Seminar" page.
