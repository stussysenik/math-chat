## Context

The current Python/SymPy architecture is built on a basic string-formatting LLM templater and real-time streaming connections (SSE). However, to scale to complex combinatorial, recursion, and sequence limit mathematical textbook setups, we need a robust, heavy framework capable of running deep offline programmatic routines. A massive frontend shift to custom UI formats like `Maf.js` or `DaisyUI` is unnecessary overhead when Native ML UI environments like `OpenWebUI` provide the infrastructure required to natively host structured horizontal/vertical elements via their `ID-Message` architecture.

Furthermore, string templates for teaching physics/math are brittle. Transitioning the Socratic core into `DSPy` provides a compiled, optimizable, programmatic signature approach to "Reverse Origami" pedagogical outputs.

## Goals / Non-Goals

**Goals:**
- Replace raw prompt chains with compiled `DSPy` Signatures and Predictors.
- Discard the real-time SSE streamer in favor of Python asynchronous message queues (RabbitMQ/Celery) running background verification batches.
- Inject output seamlessly into OpenWebUI's native ID-Message semantic layer.
- Integrate Wolfram Alpha algorithms into the pipeline cleanly to augment SymPy.

**Non-Goals:**
- We are *not* building a dedicated, standalone web frontend server.
- We are *not* moving logic away from Python. The Python ML ecosystem (prepping for future Mojo/JAX integrations) will be our Moat.

## Decisions

- **DSPy for Orchestration:** DSPy is cutting-edge. It allows strict programmatic logic boundaries for the Socratic Explainer logic, making debugging math prompts as simple as debugging Python modules.
- **RabbitMQ Background Jobs:** Instead of hanging the UI window on 3-minute sequence evaluations, jobs will be submitted to RabbitMQ. The user can navigate away while Wolfram and Octave/SymPy run.
- **OpenWebUI Semantic Integration:** By formatting our outputs precisely into the schema OpenWebUI expects for ID-messages, we gain visual horizontal & vertical mathematical grouping out of the box natively.

## Risks / Trade-offs

- **Learning Curve:** Transitioning from simple `PromptTemplate` strings to `DSPy` signatures introduces cognitive complexity.
- **DevOps:** Standing up RabbitMQ/Celery workers adds infrastructural overhead locally.
