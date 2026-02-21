## ADDED Requirements

### Requirement: Nim Job Queues
The root orchestration layer MUST be rewritten in Nim to accept image payloads and dispatch batched verification jobs to Python, Octave, and Wolfram.

#### Scenario: Long-Running Combinatorics Job
- **WHEN** a complex recursive definition is extracted.
- **THEN** Nim creates an asynchronous batch job, holds the HTTP connection, dispatches sub-processes to GNU Octave, and only returns when the 100% verified LaTeX chapter is fully compiled.
