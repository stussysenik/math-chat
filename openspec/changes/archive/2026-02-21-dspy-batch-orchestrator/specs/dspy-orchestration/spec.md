## ADDED Requirements

### Requirement: Compiled Socratic Reasoning Engine
The Socratic Explainer logic MUST be extracted from string prompt templates and implemented as a strict, programmatic `DSPy` Module. It must utilize `dspy.Signature` formats defining precise inputs and outputs.

#### Scenario: Compiling the Reverse Origami Pipeline
- **WHEN** the backend receives a SymPy-verified mathematical goal.
- **THEN** it executes the `DSPy` Reverse Origami Pipeline, generating intermediate breakdown thoughts (`dspy.Predict`/`dspy.ChainOfThought`) culminating in the structured `SocraticUIBlock` JSON.
