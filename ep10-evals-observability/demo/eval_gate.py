"""
Ep 10 demo — an eval gate for the policy bot (eval-driven development).

    python eval_gate.py --config release       # passes the gate → exit 0
    python eval_gate.py --config regression    # a "small tweak" that fails the gate → exit 1

Metrics (offline, deterministic, so CI is cheap and stable):
  context_recall    expected source sections retrieved
  answer_correct    answer contains the required facts
  faithfulness      every sentence of the answer is supported by the retrieved context
  refusal_ok        unanswerable questions are refused
  acl_leak          restricted questions (HR-only) asked by a credit officer must NOT be answered (must be 0)

The answerer here is EXTRACTIVE (returns the best supporting sentence) so the demo needs no LLM.
Swap in your real pipeline, and add LLM-judged metrics (Ragas / DeepEval) for answer quality,
calibrated against human labels.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from nwlib import Retriever, load_chunks, load_golden, recall_at_k  # noqa: E402

CONFIGS = {
    "release":    {"k": 3, "filter_status": True, "acl": True, "min_score": 7.0},  # tuned on the golden set
    "regression": {"k": 3, "filter_status": False, "acl": False, "min_score": 0.0},  # "simplified" retrieval
}
THRESHOLDS = {"context_recall": 0.90, "answer_correct": 0.85, "faithfulness": 0.95, "refusal_ok": 1.0, "acl_leak": 0}
PERSONA_GROUPS = {"all-staff", "lending", "risk", "compliance"}  # eval persona: a credit officer (no HR access)
REFUSAL = "I couldn't find this in current policy."


def answer(r: Retriever, q: str, cfg: dict):
    mask = np.array([(c.status == "active" or not cfg["filter_status"]) and
                     (bool(set(c.groups) & PERSONA_GROUPS) or not cfg["acl"]) for c in r.chunks])
    hits = r.hybrid(q, cfg["k"], mask=mask)
    scores = r.bm25.scores(q)
    pos = {c.chunk_id: i for i, c in enumerate(r.chunks)}
    if not hits or max(scores[pos[h.chunk_id]] for h in hits) < cfg["min_score"]:
        return REFUSAL, []          # relevance gate: nothing confidently relevant → refuse
    top = max(hits, key=lambda h: scores[pos[h.chunk_id]])
    return f"{top.text} [{top.doc_id} §{top.section}]", hits


def supported(ans: str, ctx: list) -> bool:
    body = re.sub(r"\[.*?\]", "", ans).strip()
    return any(body in c.text for c in ctx) if ctx else body == REFUSAL


def trace(event: dict) -> None:
    """In production: an OpenTelemetry span / Langfuse trace per step."""
    with open("eval_traces.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=list(CONFIGS), default="release")
    cfg = CONFIGS[ap.parse_args().config]
    r = Retriever(load_chunks(), force_offline=True)
    rows = {k: [] for k in ("context_recall", "answer_correct", "faithfulness", "refusal_ok")}
    leaks = 0
    for g in load_golden():
        t0 = time.perf_counter()
        ans, ctx = answer(r, g["question"], cfg)
        trace({"id": g["id"], "config": cfg, "retrieved": [c.chunk_id for c in ctx],
               "answer": ans, "ms": round(1000 * (time.perf_counter() - t0), 1)})
        if g.get("restricted_to"):
            leaks += ans != REFUSAL
            continue
        if g.get("unanswerable"):
            rows["refusal_ok"].append(float(ans == REFUSAL))
            continue
        rows["context_recall"].append(recall_at_k(ctx, g["expected_sources"]))
        rows["answer_correct"].append(float(all(f.lower() in ans.lower() for f in g["answer_must_contain"])))
        rows["faithfulness"].append(float(supported(ans, ctx)))

    results = {k: round(float(np.mean(v)), 3) for k, v in rows.items()}
    results["acl_leak"] = leaks
    failed = []
    print(f"{'metric':<16}{'value':>8}{'threshold':>12}  status")
    for k, v in results.items():
        thr = THRESHOLDS[k]
        ok = v <= thr if k == "acl_leak" else v >= thr
        failed += [] if ok else [k]
        print(f"{k:<16}{v:>8}{('≤ ' if k == 'acl_leak' else '≥ ') + str(thr):>12}  {'PASS' if ok else 'FAIL'}")
    print("\nGATE:", "PASS ✅ deploy allowed" if not failed else f"FAIL ❌ blocked by {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
