# Ep 4 · LLM Gateway — Cheat Sheet

## Inside the gateway (in order)
1. **Auth:** virtual key → team
2. **Policy:** data class → allowed models / regions
3. **Budget & rate limit** per team
4. **Router:** task · length · difficulty
5. **Fallback chain:** timeouts + cooldown
6. **Log:** team · model · tokens · cost · latency

## Model selection (in order)
Task quality on **your** golden set → data constraints → latency → cost per answer → context window → ops (limits, SLA, regions)

## Routing patterns
- **Rules:** task type, prompt length
- **Classifier:** cheap difficulty model
- **Cascade:** try small → check → escalate

## Availability math
- One provider at 99.5% ≈ 3.6 h down/month
- Two independent: 1 − 0.005² ≈ **99.9975%**

## Cost (Northwind, illustrative)
All frontier **$3,101/mo** → routed 70/30 **$1,031/mo**

## Self-host break-even
`tokens/month at which (GPU + ops people) = API cost`
Self-host if: data can't leave, sustained high utilisation, fine-tuned open model.

## Change safety
Pin versions · shadow on golden set · canary 5→25→100% · instant rollback

## Never
Keys in code · "latest" aliases · raw PII in logs · fallbacks that break residency
