# ThetaWise+ Plan: Lean + SymPy + Graph Evidence

## Goal
For college-level math, always produce an evidence chain instead of NLP-only answers:
1. Parse
2. Lean formalize
3. SymPy compute
4. Verify + judge
5. Graph evidence
6. Neutral final explanation

## What ThetaWise appears to emphasize
From public metadata on its homepage:
- "Most Accurate Math AI Tutor"
- "Step-by-Step solutions"
- "Tutoring mode"
- "Advanced solver"
- "Practice sessions"

## How to make this system stronger

### 1) Mandatory proof chain for nontrivial math
- Always run Lean-first and SymPy, then verification aggregation.
- Never answer with fluent text only when symbolic content exists.

### 2) Evidence ledger in every response
- Lean status: compiled / proved / unsupported.
- SymPy status: operation + exact residual/equivalence checks.
- Graph status: Desmos expressions + key points.
- Verdict: pass / partial / fail with confidence.

### 3) Domain-aware college solving
- Parse and carry domain assumptions (real/complex/integer/unspecified).
- If domain is missing, state assumption and show how result changes by domain.

### 4) Neutral tutor policy
- If evidence conflicts, explicitly mark uncertainty.
- Do not over-claim.
- Give concise derivation first; expand only when asked.

### 5) Graphical reasoning by default
- Emit Desmos-ready expressions for copy/paste.
- Emit Mafs spec for interactive frontend rendering.
- Include intercepts/critical points when available.

### 6) Failure behavior
- If Lean cannot represent a result (e.g., non-rational roots in current bridge), mark "partial" not "pass".
- Ask one clarifying question only when parsing is ambiguous.

## Input contract for best results
User prompt template:
- "Solve/Prove [problem]. Domain: [R/C/Z]. Show concise derivation + verification status."

Example:
- "Solve x^4-5x^2+4=0 over reals. Show Lean+SymPy verification and graph evidence."

## Prompt stack
Use `PROMPTS.md`:
1. Orchestrator
2. Parser
3. Tutor
4. Verifier
