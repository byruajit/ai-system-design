# Ep 8 · Fast & Cheap LLM Apps — Cheat Sheet

## Measure first
Budget every stage at p95: gateway · embed · search · rerank · **TTFT** · generation. Users judge by **time to first token**: stream.

## Cost levers (biggest first)
1. **Route** easy → small model
2. **Fewer chunks** (rerank to 3)
3. **Prompt caching**: stable prefix first
4. **Exact + semantic cache** (safely)
5. Concise output, `max_tokens`
6. **Batch API** for offline jobs
7. **Self-host** past break-even

## Safe semantic cache
| Risk | Guard |
| --- | --- |
| Personal data | Never cache "my/me" questions; scope keys |
| Near-miss | **Slot guard**: numbers & qualifiers match |
| Stale | Store doc versions; invalidate on change |
| Permissions | ACL scope in the cache key |

Tune the threshold on labelled pairs: ship **zero wrong hits**.

## Self-hosting checklist
vLLM/TGI continuous batching · quantise only after evals · autoscale on queue depth · keep 1 warm replica · overflow to an API

## Metrics
TTFT p95 · total p95 · tokens/request · cost/request · cache hit **and wrong-hit** rate · GPU utilisation

## Say this
"Streaming fixes perception; routing and chunk count fix the bill; the cache must be scoped, guarded and versioned."
