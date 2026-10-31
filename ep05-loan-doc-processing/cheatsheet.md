# Ep 5 · Document AI Pipeline — Cheat Sheet

## Pipeline
1. Upload → object store → **queue** (return a job ID)
2. **Split pages** → classify each page
3. **Extract per doc type** → value · confidence · page
4. **Schema** validation (types, formats)
5. **Rules + cross-checks** (income vs payslip, LTV, FOIR)
6. Route: auto-accept or **field-level human review**
7. **Idempotent** write to the system of record + provenance
8. Corrections → **eval dataset**

## Three layers of trust
Schema → business rules → confidence. **Confidence alone is not enough.**

## Sizing
- pages/s = pages/day ÷ window seconds
- workers = pages/s × seconds per page (+ 2–3× for peaks)
- Northwind: 2.8 pages/s → ~6 workers

## OCR + LLM vs vision LLM
| Use | Pick |
| --- | --- |
| Typed / digital PDFs | OCR + small LLM |
| Photos, stamps, handwriting | Vision LLM |
| Decide by | field accuracy on 200 real pages |

## Metrics
Field precision/recall · **error rate in auto-accepted fields** · straight-through rate · review time per file

## Reliability
Idempotency key = hash(file) + pipeline version · DLQ for poison files · reprocess by version, never overwrite reviewed values

## PII
Mask Aadhaar (last 4) · least pages to the model · logs carry field names, not values
