"""
Ep 8 demo — a semantic cache that is fast AND safe.

    python semantic_cache.py

Shows:
  1. threshold tuning: hit rate vs WRONG-hit rate on labelled query pairs, and why a
     similarity threshold ALONE can't separate "same question" from "same question, different
     amount/segment" (numbers and qualifiers barely move the vector), so we add a slot guard
  2. scope: personal questions ("my balance") are never served from a shared cache
  3. invalidation: cache entries are tied to the source document versions they used

Uses the offline embedder from tools/nwlib.py (or sentence-transformers if installed).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import re

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from nwlib import Embedder, load_chunks  # noqa: E402

PERSONAL = re.compile(r"\b(my|mine|me|i|account number)\b", re.I)
CRITICAL = ["salaried", "self-employed", "high-risk", "medium-risk", "low-risk", "senior",
            "above", "below", "up to", "waived", "shadow"]


def slots(q: str) -> frozenset:
    """Numbers + business qualifiers that change the answer. Must match exactly for a hit."""
    ql = q.lower().replace("high risk", "high-risk").replace("low risk", "low-risk")
    nums = re.findall(r"\d+(?:[.,]\d+)*", ql)
    return frozenset(nums + [w for w in CRITICAL if w in ql])

# (cached question, new question, should it be a hit?)
PAIRS = [
    ("What is the daily cash withdrawal limit at the branch counter?", "Counter cash withdrawal limit per day?", True),
    ("What is the daily cash withdrawal limit at the branch counter?", "How much cash can a customer withdraw at the counter daily?", True),
    ("What is the penalty for premature FD withdrawal?", "Penalty for breaking a fixed deposit early?", True),
    ("How many days of PL can be carried forward?", "Privileged leave carry forward limit?", True),
    ("What is the maximum LTV for home loans up to 30 lakh?", "Max LTV for a home loan up to 30 lakh?", True),
    ("What is the maximum LTV for home loans up to 30 lakh?", "What is the maximum LTV for home loans above 75 lakh?", False),
    ("What FOIR is allowed for salaried applicants?", "What FOIR is allowed for self-employed applicants?", False),
    ("What is the penalty for premature FD withdrawal?", "Is the FD penalty waived for senior citizens?", False),
    ("How often is re-KYC required for high-risk customers?", "How often is re-KYC required for low-risk customers?", False),
    ("What is the debit card dispute window?", "What is the shadow credit rule for card disputes?", False),
]


@dataclass
class Entry:
    question: str
    vec: np.ndarray
    answer: str
    doc_versions: dict[str, int]


class SemanticCache:
    def __init__(self, embedder: Embedder, threshold: float, slot_guard: bool = True):
        self.e, self.t, self.guard, self.entries = embedder, threshold, slot_guard, []

    @staticmethod
    def cacheable(q: str) -> bool:
        return not PERSONAL.search(q)

    def put(self, q: str, answer: str, doc_versions: dict[str, int]) -> None:
        if self.cacheable(q):
            self.entries.append(Entry(q, self.e.encode([q])[0], answer, doc_versions))

    def get(self, q: str, live_versions: dict[str, int]):
        if not self.cacheable(q) or not self.entries:
            return None, 0.0
        v = self.e.encode([q])[0]
        sims = [float(en.vec @ v) for en in self.entries]
        i = int(np.argmax(sims))
        en = self.entries[i]
        stale = any(live_versions.get(d, ver) != ver for d, ver in en.doc_versions.items())
        slot_ok = (not self.guard) or slots(q) == slots(en.question)
        if sims[i] >= self.t and not stale and slot_ok:
            return en, sims[i]
        return None, sims[i]


def main() -> None:
    chunks = load_chunks()
    fit = [c.indexed_text for c in chunks] + [p for pair in PAIRS for p in pair[:2]]
    emb = Embedder(fit)
    print(f"Embeddings: {emb.kind}\n")

    print("1) THRESHOLD TUNING on labelled pairs")
    print("   similarity of each pair (should-hit pairs marked ✓):")
    for cached, new, should in PAIRS:
        v = emb.encode([cached, new])
        print(f"     {float(v[0] @ v[1]):.2f}  {'✓' if should else '✗'}  {new}")
    print("   Note: 'above 75 lakh' scores HIGHER than true paraphrases. Real embedding models show the same")
    print("   weakness with numbers and qualifiers, so no single threshold separates them.\n")
    print("   threshold   guard   hits (of 5 should-hit)   WRONG hits (of 5 should-miss)")
    for guard in (False, True):
        for t in (0.45, 0.60, 0.80):
            hits = wrong = 0
            for cached, new, should in PAIRS:
                c = SemanticCache(emb, t, slot_guard=guard)
                c.put(cached, "answer", {})
                got, _ = c.get(new, {})
                hits += bool(got) and should
                wrong += bool(got) and not should
            print(f"   {t:.2f}        {'on ' if guard else 'off'}     {hits}/5                      {wrong}/5")
    print("   → tune on YOUR labelled pairs; ship only a setting with zero wrong hits.\n")

    print("2) SCOPE: personal questions bypass the shared cache")
    c = SemanticCache(emb, 0.9)
    c.put("What's my account balance?", "₹48,210 (Kavya's balance)", {})
    print(f"   entries after caching a personal answer: {len(c.entries)}  (refused)")
    print(f"   lookup 'What is my balance?' → {c.get('What is my balance?', {})[0]}  (always goes to the API)\n")

    print("3) INVALIDATION by document version")
    c = SemanticCache(emb, 0.45)
    c.put("What is the penalty for premature FD withdrawal?", "1% (POL-RET-207 v3)", {"POL-RET-207": 3})
    hit, s = c.get("What's the penalty for premature FD withdrawal?", {"POL-RET-207": 3})
    print(f"   policy at v3 → {'HIT: ' + hit.answer if hit else 'MISS'} (similarity {s:.2f})")
    hit, s = c.get("What's the penalty for premature FD withdrawal?", {"POL-RET-207": 4})
    print(f"   policy now v4 → {'HIT' if hit else 'MISS (entry built on v3 is stale)'}")


if __name__ == "__main__":
    main()
