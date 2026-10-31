# Back-of-envelope estimation for AI systems

Work these out on the whiteboard, left to right. Round aggressively: interviewers want the method and the right order of magnitude, not decimals.

## 1. Traffic

```
queries/day   = users × daily-active share × queries per user
peak QPS      = queries/day × peak share ÷ (peak hours × 3,600)
design QPS    = peak QPS × burst factor (3–10×), then round up
```

## 2. Tokens per request

```
input tokens  = system prompt + history + (k chunks × chunk size) + question
output tokens = answer length (≈ 0.75 words per token in English)
```

Rules of thumb: 1 page ≈ 500 tokens; 1 token ≈ 4 characters of English; Indian-language text usually tokenizes into more tokens per word, so measure it.

## 3. Cost

```
cost/request  = input × price_in/1M + output × price_out/1M
cost/month    = cost/request × requests/month
agent cost    = steps × (tokens_in per step × price_in + tokens_out per step × price_out)/1M
```

Agents are priced **per task**: context grows every step, so a 6-step task can cost 10–20× one chat answer.

## 4. Latency budget (p95)

| Stage | Typical budget |
| --- | --- |
| Gateway + auth | 20–50 ms |
| Query embedding | 20–80 ms |
| Vector + keyword search | 30–150 ms |
| Rerank | 50–300 ms |
| LLM time to first token | 300–1,500 ms |
| Generation (300 tokens) | 1–6 s, depending on tier and load |

Streaming hides generation time: users judge speed by **time to first token**.

## 5. Storage

```
chunks           ≈ corpus tokens ÷ (chunk size − overlap)
vector bytes     = chunks × dimensions × 4 (float32)   [× ~2 for index + payload]
audit log/year   = requests/year × bytes per record (prompt + response + metadata ≈ 5–20 KB)
```

## 6. Availability (serial dependencies multiply)

```
A_system = A_1 × A_2 × … × A_n
A_with_fallback(layer) = 1 − (1 − A_primary)(1 − A_secondary)
```

## Worked example: the Northwind policy bot

See [`../northwind/assumptions.md`](../northwind/assumptions.md):

- 10,800 queries/day → 0.45 QPS average peak → design for ~5 QPS
- 2,850 input + 300 output tokens per query
- $144 to $3,101 per month depending on model tier; ~$1,031 routed (illustrative prices)
- ~444k chunks → ~1.8 GB raw vectors
