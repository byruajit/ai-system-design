# Ep 10 · Evals & Observability — Cheat Sheet

## Two loops
**Offline:** golden set → metrics → CI gate → canary
**Online:** traces → sampled review → feedback → alerts → **new golden items**

## Metrics by layer
| Layer | Metric |
| --- | --- |
| Retrieval | context recall / precision @k |
| Answer | correctness · faithfulness |
| Safety | refusal on unanswerable · **ACL leak = 0** · injection pass rate |
| Ops | TTFT · p95 · tokens · cost/answer |
| Users | thumbs · escalations · re-asks |

## Golden set
50–100 real questions → expected sources + required facts + labels (answerable / unanswerable / restricted / adversarial). In Git. Grows weekly.

## LLM-as-judge
Calibrate vs ~100 human labels · pin the judge version · deterministic checks first

## CI gate
Path-filtered trigger · deterministic metrics block merges · judged metrics nightly · traces as artifacts

## Tracing (per request)
Spans: retrieval · rerank · LLM · tools. Attributes: model + prompt version, tokens, cost, chunk IDs. **Redact payloads.**

## Alert on quality
Refusal-rate spike · faithfulness drop · cost/answer drift · retrieval score shift

## Ownership
Product: pipeline + gate · Domain experts: answers · Risk/audit: safety tests + thresholds
