# Ep 3 · Permission-Aware RAG — Cheat Sheet

## Golden rules
1. **Store groups, not users** on every chunk
2. Resolve user → groups **at query time** (IdP, short TTL)
3. **Pre-filter** inside the vector query
4. **Re-check** ACLs on final chunks (defence in depth)
5. **Audit:** user · chunk IDs · versions · time

## Freshness pipeline
- Source webhooks → **queue** → idempotent workers
- IDs: `doc_id#version#section` (replay-safe)
- Content hash → skip unchanged sections
- **Nightly reconciliation** catches lost events

## Deletes
- **Tombstone** now (filtered instantly)
- **Purge** later: vectors, chunks, caches
- Log the deletion; test that it's gone

## Re-index without downtime
Build green → backfill → replay events → **evals** → flip alias → keep blue for rollback

## Isolation levels
| Need | Pattern |
| --- | --- |
| Department access | Metadata filter |
| Strict tenant / residency | Separate index per region |
| Regulator-mandated | Separate deployment |

## Targets (Northwind)
New doc ≤ 15 min · delete ≤ 5 min · mover ≤ 15 min · rebuild ≈ 17 min

## Say this
- "Freshness isn't a throughput problem; it's event correctness."
- "Post-filtering can starve k and can leak on a bug."
