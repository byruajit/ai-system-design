# Ep 1 · The AI System Design Playbook

## The 9 steps (45 min)
1. **Clarify** (3): users, "good answer", scope
2. **Requirements** (4): functional · non-functional · AI-specific
3. **Estimates** (4): QPS · tokens · cost · storage
4. **High-level design** (8): simplest design that works
5. **Deep dive** (10): hardest 1–2 parts
6. **Data flow & APIs** (4): walk one request
7. **Scale · reliability · security** (6): what breaks first
8. **Evals & monitoring** (3): how you know it works
9. **Trade-offs** (3): 3 decisions + the rejected options

## AI-specific requirements
Quality · hallucination tolerance · citations · cost per request · token budget · PII & residency · freshness · audit · non-determinism · human-in-the-loop

## Estimation formulas
- `q/day = users × active% × q/user`
- `peak QPS = q/day × peak% ÷ (hours × 3600)`
- `tokens_in = sys + history + k×chunk + question`
- `$/q = in×P_in/1M + out×P_out/1M`
- `vectors = chunks × dims × 4 B (×2 index)`
- `A_serial = A1 × A2 × … × An`

## Northwind numbers
10,800 q/day · 0.45 QPS (design 5) · 2,850 in / 300 out · **$144–$3,101/month**, routed ≈ $1,031 *(illustrative prices)*

## Don't use an LLM for…
Lookups → API · Risk scores → ML · Fixed rules → rules engine · <100 ms hot path

## Say this
- "Let me confirm users and what a good answer looks like."
- "Cost is a requirement. Here's the bill by model tier."
- "Simplest design first, then I'll evolve it."
- "Here's what breaks first, and the fallback."
- "Three decisions, and what I gave up."
