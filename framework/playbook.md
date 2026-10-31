# The AI System Design Playbook (9 steps, 45 minutes)

Use the same nine steps for every AI system design question, whether it's in an interview or a design review. Times assume a 45-minute interview.

| # | Step | Time | What a strong answer does | Common miss |
| --- | --- | --- | --- | --- |
| 1 | **Clarify** | 3 min | Restates the problem; asks who the users are, what "good" means, and what is out of scope | Jumps to "I'd use a vector DB" |
| 2 | **Requirements** | 4 min | Functional + non-functional + **AI-specific** (quality, hallucination tolerance, cost per request, data sensitivity, explainability) | Lists only latency and scale |
| 3 | **Estimates** | 4 min | Users → queries/day → peak QPS → tokens/request → cost/request → monthly bill → storage | Skips cost entirely |
| 4 | **High-level design** | 8 min | Boxes and arrows for client, gateway, orchestrator, model layer, retrieval/tools, data stores; one sentence per box | A box nobody can explain |
| 5 | **Deep dive** | 10 min | Picks the 1–2 hardest components (usually retrieval or the agent loop) and goes deep | Stays shallow everywhere |
| 6 | **Data flow & APIs** | 4 min | Walks one request end to end; names the APIs and the payloads | No request walk-through |
| 7 | **Scale, reliability, security** | 6 min | Bottlenecks, caching, fallbacks, failure modes, PII, access control, prompt injection | Treats security as "add auth" |
| 8 | **Evals & monitoring** | 3 min | How you know it works: golden set, offline metrics, online signals, feedback loop | No mention of evaluation |
| 9 | **Trade-offs & wrap** | 3 min | 3 explicit decisions with the rejected alternative; what you'd do with more time | Defends every choice as perfect |

## AI-specific requirements checklist

Classic system design asks about latency, throughput and availability. AI systems add:

- **Answer quality:** what does a correct answer look like, and who judges it?
- **Hallucination tolerance:** is a wrong answer an annoyance or a regulatory breach?
- **Grounding & citations:** must every answer cite a source?
- **Cost per request / per task:** is there a budget ceiling?
- **Token budget:** context window limits and how much context each request needs
- **Data sensitivity:** PII, confidential data, data residency, which data may reach which model
- **Freshness:** how quickly must new or changed data show up?
- **Explainability & audit:** can you reconstruct why the system said something?
- **Non-determinism:** how do you test something that answers differently each time?
- **Human in the loop:** which decisions must a human approve?

## When NOT to use an LLM

Say this out loud in interviews, because it shows judgement:

- The answer is a **lookup** (balance, status) → call the API directly
- The decision needs **calibrated probability** (fraud, credit risk) → classic ML, and the LLM explains
- The logic is **fixed rules** (eligibility) → a rules engine
- **Latency under ~100 ms** at high volume → no LLM in the hot path

## Generic reference architecture

```
Client (web / mobile / Teams)
        │
   API Gateway  ── auth (SSO/JWT), rate limits, request IDs
        │
   Orchestrator / App service ── prompt assembly, routing, guardrails
        │            │              │
   Model layer   Retrieval      Tools / APIs (via MCP)
  (LLM gateway)  (vector + BM25) (core banking, CRM, LOS)
        │            │              │
   ─────────── Data stores: docs, vectors, cache, state, audit log ───────────
   Cross-cutting: observability (traces, metrics, logs) · evals · security · cost
```
