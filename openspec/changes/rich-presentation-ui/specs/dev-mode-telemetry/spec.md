## ADDED Requirements

### Requirement: Deep System Telemetry Toggles
The server stream SHALL provide a configurable boolean feature flag (`dev_mode`) that injects internal algorithmic state payloads into the frontend data stream.

#### Scenario: Enabling Dev Mode Insight
- **WHEN** the `dev_mode` flag is activated in the request schema.
- **THEN** the pipeline Server-Sent Events append the raw SymPy calculation nodes, domain residual counts, and numerical tolerances to the final returned UI state.

### Requirement: Distinct Developer UI Rendering
The raw numerical validation telemetry SHALL be styled explicitly as developer constraints (e.g. raw terminal logs) distinct from the Socratic pedagogical explanation.

#### Scenario: Developer UI Segregation
- **WHEN** the structured prompt payload reaches the Socratic formatter.
- **THEN** the Dev Mode telemetry is isolated in an embedded sub-block within the returned Schema, ensuring it does not pollute the primary Feynman pedagogical narrative.
