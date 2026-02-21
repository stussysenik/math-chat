# DeepSeek-Prover + Putnam-Style Notes

## Why this matters for this stack
DeepSeek-Prover publicly frames theorem proving as a pipeline with formal verification loops. The useful design pattern for this project is:
1. formal target first,
2. candidate derivation,
3. verifier pass,
4. iterative repair.

That maps directly to this stack:
- Lean-first formalization
- SymPy symbolic candidate
- Verdict + missing-proof detection
- User-visible trace + next checks

## Practical adaptation used here
- Every query now emits a node trace (`ingest -> parse -> lean_first -> sympy -> verify -> graph -> compose`).
- The verifier emits `pass|partial|fail` with confidence and missing proof items.
- Non-representable Lean cases are intentionally `partial` instead of over-claiming.

## Putnam-style behavioral guardrails (for future prompt tuning)
- State assumptions explicitly (domain, constraints).
- Reduce to lemmas/subgoals before final claim.
- Verify each claim with exact algebraic/formal checks where possible.
- Mark uncertainty immediately when a proof obligation remains open.

## References
- DeepSeek-Prover repo: https://github.com/deepseek-ai/DeepSeek-Prover-V1.5
- DeepSeek-Prover paper entry: https://arxiv.org/abs/2405.14333
