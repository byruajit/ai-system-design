"""
Ep 3 demo — permission-aware retrieval, deletions and zero-downtime re-indexing.

    python acl_rag.py

Scenes (each prints a short, on-screen-friendly result):
  1. The leak: v1 index with no ACLs, so an intern sees director pay bands.
  2. Pre-filter vs post-filter: post-filtering can silently return fewer than k results.
  3. ACL change event: an employee moves Retail → HR leadership; access follows the identity provider (IdP) groups.
  4. Deletion: a tombstone event removes a document from answers immediately.
  5. Blue-green index: rebuild "nw-policies-v2" and swap the alias atomically.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from nwlib import Retriever, load_chunks  # noqa: E402


# ---------------------------------------------------------------- identity
@dataclass
class User:
    name: str
    groups: set[str] = field(default_factory=set)


IDP = {  # pretend identity provider (Entra ID / Okta groups)
    "ravi.intern": User("ravi.intern", {"all-staff"}),
    "anita.hrlead": User("anita.hrlead", {"all-staff", "hr-leadership"}),
    "sam.us": User("sam.us", {"us-staff"}),
}


# ---------------------------------------------------------------- index with aliases
class Index:
    def __init__(self, name: str, chunks):
        self.name = name
        self.retriever = Retriever(chunks, force_offline=True)
        self.deleted: set[str] = set()  # tombstoned doc_ids

    def allowed_mask(self, user: User) -> np.ndarray:
        return np.array([bool(set(c.groups) & user.groups) and c.status == "active"
                         and c.doc_id not in self.deleted for c in self.retriever.chunks])

    def _confident(self, q: str, hits, min_score: float = 2.0):
        """Relevance gate: keep hits whose keyword score clears a threshold (tune on the golden set)."""
        scores = self.retriever.bm25.scores(q)
        pos = {c.chunk_id: i for i, c in enumerate(self.retriever.chunks)}
        return [c for c in hits if scores[pos[c.chunk_id]] >= min_score]

    def search_prefilter(self, q: str, user: User, k: int = 3):
        return self._confident(q, self.retriever.hybrid(q, k, mask=self.allowed_mask(user)))

    def search_postfilter(self, q: str, user: User, k: int = 3):
        raw = self.retriever.hybrid(q, k)  # rank everything, then drop forbidden
        kept = [c for c in raw if set(c.groups) & user.groups and c.status == "active" and c.doc_id not in self.deleted]
        return self._confident(q, kept)


ALIASES: dict[str, Index] = {}


def show(title: str, hits) -> None:
    print(f"  {title}")
    for c in hits or []:
        print(f"     → {c.chunk_id}  groups={c.groups}")
    if not hits:
        print("     → (nothing returned; the bot refuses)")


def main() -> None:
    chunks = load_chunks()
    q_pay = "What is the director pay band?"

    print("\n1) THE LEAK: v1 index, no ACL filter")
    v1 = Index("nw-policies-v1", chunks)
    show(f"ravi.intern asks: {q_pay}", v1.retriever.hybrid(q_pay, 2))

    print("\n2) PRE-FILTER vs POST-FILTER (k=3)")
    ALIASES["nw-policies"] = v1
    idx = ALIASES["nw-policies"]
    q_mix = "HR leadership pay band confidentiality and annual leave policy"
    print(f"  ravi.intern asks: {q_mix}")
    pre = idx.search_prefilter(q_mix, IDP["ravi.intern"])
    post = idx.search_postfilter(q_mix, IDP["ravi.intern"])
    show(f"pre-filter  → {len(pre)} results (filter inside the search)", pre)
    show(f"post-filter → {len(post)} results (search, then drop forbidden; can starve k)", post)
    show(f"ravi.intern asks: {q_pay} (pre-filter + relevance gate)", idx.search_prefilter(q_pay, IDP["ravi.intern"]))
    show("anita.hrlead asks the same", idx.search_prefilter(q_pay, IDP["anita.hrlead"], k=1))

    print("\n3) ACL CHANGE EVENT: ravi.intern is promoted into HR leadership")
    print("     IdP webhook: group_added(user=ravi.intern, group=hr-leadership)")
    IDP["ravi.intern"].groups.add("hr-leadership")  # groups resolved at query time, so no re-index needed
    show("ravi now", idx.search_prefilter(q_pay, IDP["ravi.intern"], k=1))
    IDP["ravi.intern"].groups.discard("hr-leadership")

    print("\n4) DELETION: POL-HR-031 (leave policy) withdrawn")
    q_leave = "How many days of PL can I carry forward?"
    show("before tombstone", idx.search_prefilter(q_leave, IDP["ravi.intern"], k=1))
    idx.deleted.add("POL-HR-031")
    print("     event: document.deleted(POL-HR-031) → tombstone written, purge job queued")
    show("after tombstone", idx.search_prefilter(q_leave, IDP["ravi.intern"], k=1))

    print("\n5) BLUE-GREEN RE-INDEX")
    print(f"     alias nw-policies → {ALIASES['nw-policies'].name} (serving)")
    green = Index("nw-policies-v2", [c for c in chunks if c.doc_id != "POL-HR-031"])
    print(f"     built {green.name} offline with new chunking: {len(green.retriever.chunks)} chunks; run golden-set evals…")
    ALIASES["nw-policies"] = green  # atomic pointer swap; the old index is kept for rollback
    print(f"     alias nw-policies → {ALIASES['nw-policies'].name} (serving). Rollback = swap back.")


if __name__ == "__main__":
    main()
