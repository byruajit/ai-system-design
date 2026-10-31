# Ep 2 · RAG Policy Bot — Design Cheat Sheet

## The v2 pipeline
1. Layout-aware parse → **section chunks**, tables whole
2. **Contextual header** on every chunk (title + section)
3. **Metadata:** doc_id · section · version · effective · status · groups
4. **Filter first:** status = active, effective ≤ today
5. **Hybrid:** BM25 + dense → top 20
6. **Fuse:** RRF score = Σ 1/(60 + rank)
7. **Rerank** (cross-encoder) → top 3–5
8. **Gate:** low confidence → fixed refusal
9. **Prompt contract:** context only, cite `[doc §sec]`
10. **Citation check** before returning

## Sizing
- chunks ≈ tokens ÷ (size − overlap)
- vectors = chunks × dims × 4 B (×2 indexed)
- Northwind: 444k chunks · 1.8 GB raw · ~$4 to embed

## Chunking rules of thumb
- 300–800 tokens, ~10% overlap
- Never split tables; repeat header rows
- Keep section numbers in metadata

## Index choice
| Size | Index |
| --- | --- |
| < 100k | Flat (exact) |
| 100k – 50M | **HNSW** |
| 50M+ | IVF + PQ |

## Failure → fix
- Acronym miss → **hybrid**
- Split table → **structure-aware chunks**
- Old policy → **status/version filter**
- Made-up answer → **gate + contract + check**

## Metrics to track
recall@k · faithfulness · citation accuracy · refusal rate on unanswerable questions
