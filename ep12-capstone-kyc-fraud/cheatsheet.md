# Ep 12 · KYC & Fraud Copilot — Reference Answer on One Page

## Shape of the system
Capture → **parallel checks** (OCR/doc · face/liveness · sanctions/PEP · device/graph) → features → **fraud model (classic ML)** → **rules** → auto-approve **or** analyst case → **LLM copilot** (read-only summary) → **analyst decides** → audit

## Roles
**Model scores** (calibrated, reason codes) · **LLM explains** (grounded summary, policy citations) · **Human decides** (flagged cases)

## Numbers (Northwind)
15k apps/day · burst ~2/s · 60% straight-through · 6k cases/day · 12 → 5 min/case · ~$0.004 LLM/case *(illustrative)* · ~45 GB images/day

## Must-say points
- Why not an LLM for scoring: calibration, validation, cost, latency
- Any potential sanctions hit → human
- Vendor down → fallback or analyst queue, **never auto-reject**
- OCR text is untrusted (injection)
- Audit: checks · score · reasons · versions · decision
- Residency: India and US stacks separate

## Evals
Risk model: AUC · calibration · FPR by segment · PSI drift · champion–challenger
Copilot: faithfulness (numbers ∈ facts) · analyst ratings · time/case
Fairness: no protected attributes; monitor outcomes

## The 9 steps, one more time
Clarify · Requirements · Estimates · HLD · Deep dive · Data flow · Scale/reliability/security · Evals · Trade-offs

**Hire bar:** rubric average ≥ 7, no dimension below 5
