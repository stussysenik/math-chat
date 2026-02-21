## ADDED Requirements

### Requirement: Horizontal-Vertical Math Layout
The frontend MUST render generated math "chapters" in a horizontal-vertical grid using `Maf.js` and standard LaTeX rather than a single scrolling chat window.

#### Scenario: Complex Fibonacci Limit Rendering
- **WHEN** the backend returns a fully verified multi-part proof for a generating function.
- **THEN** the UI parses the JSON block and renders part (a) horizontally adjacent to part (b), allowing the user to navigate the proof structure like a textbook page.
