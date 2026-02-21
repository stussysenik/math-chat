## Why

The deterministic math pipeline currently relies on brittle string-based LLM prompts and synchronous/SSE real-time streaming. To handle advanced, multi-part mathematical verification tasks (like combinatorics and recursive sequences) effectively, we need to transition to a heavy, batched, fully asynchronous processing model. Furthermore, we must abandon custom frontend formatting (like `Maf.js` or `DaisyUI`) in favor of tight integration with OpenWebUI's native ID-Message components. To build a true "moat" into this product, the entire LLM orchestration layer will be migrated to `DSPy`, which allows for programmatic, optimizable, and modular pipeline development for the "Reverse Origami" pedagogical method. The workload will be orchestrated via an asynchronous queue system like RabbitMQ.

## What Changes

- **BREAKING:** Migrate the entire `SocraticExplainer` out of raw string templates and into a compiled `DSPy` signature.
- **BREAKING:** Rip out the real-time SSE streaming architecture (`src/streamer.py`).
- Implement an asynchronous task queue (RabbitMQ/Celery) to batch jobs to background worker processes where SymPy/Wolfram evaluation takes place.
- Deeply bind the pipeline's JSON output directly to OpenWebUI's ID-Message UI to render mathematical blocks native to the platform.

## Capabilities

### New Capabilities
- `dspy-orchestration`: A newly structured LLM compiler layer utilizing `DSPy` to manage Socratic reasoning without brittle string templates.
- `rabbitmq-worker-queue`: A background job queuing system to safely process long-running, multi-layered algebraic limits and verifications.
- `openwebui-native-ui`: Generating the exact JSON schema and message formatting required to map horizontal-vertical equations cleanly into OpenWebUI components.

### Modified Capabilities
- `socratic-explainer`: Shift from chat-based SSE generation to a programmatic DSPy compilation step yielding structured JSON.

## Impact

- Replaces `src/streamer.py` with asynchronous Django/Celery/RabbitMQ style hooks.
- Deprecates raw `src/socratic.py` prompt templates in favor of DSPy models.
- Integrates tightly with existing OpenWebUI UX environments instead of providing custom frontend glue.
