# Ep 9 · Reliable AI Systems — Cheat Sheet

## Failure-mode table (always draw it)
Component → failure → symptom → mitigation. LLM · vector DB · embeddings · tools · cache · app · region

## Availability
- Serial: `A = A1 × A2 × … × An`
- Fallback layer: `1 − (1−Ap)(1−Ab)`
- Northwind: 99.25% → **99.75%** with a 2nd provider

## The resilience toolkit
1. **Timeouts** from the latency budget
2. **Retry** only retryable errors; backoff + **jitter**; retry budget ≤ 10%
3. **Circuit breaker:** closed → open → half-open → closed
4. **Fallback chain:** backup → small model → **degraded mode** → queue
5. **Bulkheads:** pools/limits per use case
6. **Load shedding:** customer-facing first
7. **Async** for non-urgent work
8. **Idempotent** writes
9. Health checks · canary · multi-region (per residency zone)
10. **Runbooks + game days**

## Retry rules
Retry: timeouts, 5xx, 429 (+Retry-After). Don't: 4xx, non-idempotent writes, bad-content outputs (re-prompt instead).

## Capacity check
`burst QPS × tokens/request × 60` vs the provider's **tokens/min** limit. Rate limits hit before servers do.

## Demo result
Naive p95 120 s → backoff 31 s → **breaker 3 s**, 0 errors
