"""
Ep 1 demo — measure a real prompt's token budget, then price it.

    pip install tiktoken        # optional; falls back to ~4 chars/token
    python token_budget.py

Shows on screen why "retrieval design is cost design": the retrieved context
dominates the input tokens.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from cost_estimator import PRICES  # noqa: E402

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    count = lambda s: len(_enc.encode(s))  # noqa: E731
    METHOD = "tiktoken cl100k_base (a proxy — each provider tokenizes differently)"
except Exception:  # offline or not installed
    count = lambda s: max(1, round(len(s) / 4))  # noqa: E731
    METHOD = "heuristic ≈ 4 characters per token"

SYSTEM = (
    "You are Northwind Bank's internal policy assistant. Answer only from the "
    "provided context. Cite the document ID and section for every claim. If the "
    "answer is not in the context, say you don't know and suggest who to contact. "
    "Never reveal content from documents the user is not entitled to see. "
) * 4  # a realistic production system prompt is a few hundred tokens

HISTORY = (
    "User: What is the cash withdrawal limit at branches?\n"
    "Assistant: Per POL-OPS-114 §3.2, the counter limit is ₹2,00,000 per day ...\n"
) * 2

CHUNK = (
    "POL-RET-207 §4.1 Fixed deposit premature withdrawal. A penalty of 1% on the "
    "applicable rate applies to deposits withdrawn before maturity, except for "
    "senior citizens holding deposits under the Sanchay scheme, where the penalty "
    "is waived for tenures above 12 months. Branch managers may approve exceptions "
    "up to ₹5,00,000; amounts above require regional approval ... "
) * 5
CONTEXT = [CHUNK for _ in range(5)]

QUESTION = "Can a senior citizen break a 2-year FD early without penalty?"
ANSWER_TOKENS = 300


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # ≈ and █ crash cp1252 Windows consoles
    parts = {
        "system prompt": count(SYSTEM),
        "history": count(HISTORY),
        f"context ({len(CONTEXT)} chunks)": sum(count(c) for c in CONTEXT),
        "question": count(QUESTION),
    }
    total_in = sum(parts.values())
    print(f"Token counting: {METHOD}\n")
    for k, v in parts.items():
        print(f"  {k:<20} {v:>6,}  {v / total_in:>5.0%}  {'█' * int(40 * v / total_in)}")
    print(f"  {'INPUT TOTAL':<20} {total_in:>6,}")
    print(f"  {'output (assumed)':<20} {ANSWER_TOKENS:>6,}\n")
    for tier in ("small", "medium", "large"):
        p = PRICES["models"][tier]
        c = total_in * p["input"] / 1e6 + ANSWER_TOKENS * p["output"] / 1e6
        print(f"  {tier:<7} ${c:.5f} per question  (illustrative prices)")


if __name__ == "__main__":
    main()
