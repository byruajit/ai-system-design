# Northwind — numbers used in the estimates

Every estimate in the series starts from this page. Change an assumption here and re-run `tools/cost_estimator.py`. Prices are **illustrative tiers** (see `tools/prices.json`), not any provider's list price. Exchange rate assumed: ₹88 per US$.

## Workforce and usage (policy bot, Ep 1–4)

| Assumption | Value | Why |
| --- | --- | --- |
| Employees with access | 9,000 | Whole bank |
| Daily active share | 30% | Typical for an internal knowledge tool after rollout |
| Questions per active user per day | 4 | |
| Workdays per month | 22 | |
| Peak window | 4 hours carries 60% of traffic | Branch opening + month-end |
| Burst factor inside peak | 5× | Policy circular released, everyone asks at once |

Derived:

- Queries/day = 9,000 × 0.30 × 4 = **10,800**
- Queries/month = 10,800 × 22 = **237,600**
- Average peak QPS = 10,800 × 0.60 / (4 × 3,600) = **0.45 QPS**
- Burst QPS = 0.45 × 5 ≈ **2.25 QPS** → design for **~5 QPS** with headroom

## Tokens per question (RAG)

| Part | Tokens |
| --- | --- |
| System prompt | 500 |
| Conversation history | 300 |
| Retrieved context (5 chunks × 400) | 2,000 |
| Question | 50 |
| **Input total** | **2,850** |
| Output (answer + citations) | 300 |

## Cost per question (illustrative tiers)

| Tier | Per question | Per month (237,600 q) |
| --- | --- | --- |
| Small | $0.00061 (₹0.05) | $144 (₹12,700) |
| Mid | $0.00405 (₹0.36) | $962 (₹84,700) |
| Frontier | $0.01305 (₹1.15) | $3,101 (₹2.73 lakh) |
| Routed: 70% small, 30% frontier | $0.00434 (₹0.38) | $1,031 (₹90,700) |

Lesson: model choice moves the bill ~20×; routing captures most of the saving.

## Document corpus (policy bot)

| Assumption | Value |
| --- | --- |
| Documents | 50,000 (policies, circulars, SOPs, product notes) |
| Avg pages per document | 8 |
| Tokens per page | ~500 |
| Daily change rate | 1% of documents (500 docs/day) |
| Chunk size / overlap | 500 tokens / 50 tokens |
| Embedding dimensions | 1,024 (float32) |

Derived:

- Pages = 50,000 × 8 = **400,000**; tokens ≈ 400,000 × 500 = **200M tokens**
- Chunks ≈ 200M / (500 − 50) ≈ **444,000**
- Raw vector storage = 444,000 × 1,024 × 4 bytes ≈ **1.8 GB**; with HNSW graph + payload overhead plan **~4 GB**
- One-time embedding cost ≈ 200M × $0.02/1M = **$4** (embedding is cheap; LLM calls are not)
- Daily re-embedding = 1% ≈ 2M tokens ≈ **$0.04/day**

## Loan documents (Ep 5)

| Assumption | Value |
| --- | --- |
| Loan files per day | 100,000 pages across ~4,000 applications (avg 25 pages each) |
| Processing window | 10 business hours |
| OCR/vision time per page (one worker) | ~2 s |

Derived: 100,000 / 36,000 s ≈ **2.8 pages/s** → at 2 s/page one worker does 0.5 pages/s → **~6 workers** steady state, **~15–20** for peaks and retries.

## Servicing agent (Ep 6–7)

| Assumption | Value |
| --- | --- |
| Agent tasks per day | 20,000 (contact-centre assists) |
| Steps (LLM calls) per task | 6 |
| Tokens per step | 3,000 in / 250 out (context grows each step) |

Derived: cost per task ≈ 6 × (3,000 × in + 250 × out). On the mid tier: 6 × ($0.003 + $0.001) = **$0.024/task** ≈ $480/day. **Agents are priced per task, not per request.**

## Availability targets (Ep 9)

| Component | Assumed availability |
| --- | --- |
| API gateway | 99.95% |
| App service | 99.9% |
| Vector DB | 99.9% |
| LLM provider | 99.5% |

Serial availability = 0.9995 × 0.999 × 0.999 × 0.995 ≈ **99.25%** (≈ 5.5 h downtime/month). Adding a second LLM provider as fallback lifts the LLM layer to ≈ 1 − 0.005² = 99.9975%, and the system to ≈ **99.75%**.
