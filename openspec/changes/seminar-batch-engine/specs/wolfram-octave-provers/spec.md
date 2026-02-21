## ADDED Requirements

### Requirement: Deep Algebraic Proving Engines
The numerical verifier MUST route sequence limit checks and combinatorics to GNU Octave, and deep symbolic integrations to the Wolfram Alpha API, falling back to SymPy only for basic algebra.

#### Scenario: Validating a Generating Function
- **WHEN** the LLM extracts a request to prove a Fibonacci generating function $f(z) = 1/(1 - z - z^2)$.
- **THEN** the Nim orchestrator routes the symbolic validation to GNU Octave/Wolfram to deterministically prove the Taylor series expansion coefficients match the Fibonacci sequence before saving the math block.
