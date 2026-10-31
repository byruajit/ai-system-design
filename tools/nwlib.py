"""
Shared helpers for the Northwind demos: load the synthetic corpus, chunk it,
and run keyword (BM25), dense and hybrid retrieval.

Dense embeddings:
  * If `sentence-transformers` is installed (and can download a model), it is used
    (default model: BAAI/bge-small-en-v1.5).
  * Otherwise an OFFLINE fallback is used: TF-IDF + truncated SVD (latent semantic
    analysis). It's weaker than a real embedding model but runs anywhere, so demos
    still work in a classroom with no internet. The fallback is printed on screen.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "northwind" / "corpus.json"
GOLDEN = ROOT / "northwind" / "golden_set.json"

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*%?")
STOP = set("a an the of to for is are be in on at by with and or than this that it its as from up per must may can will under above below".split())


GLOSSARY = {
    "fd": "fixed deposit", "pl": "privileged leave", "ltv": "loan to value", "foir": "fixed obligation to income ratio",
    "kyc": "know your customer", "tm": "transaction monitoring", "str": "suspicious transaction report",
    "ctr": "cash transaction report", "wfh": "work from home", "emi": "monthly instalment", "dpd": "days past due",
}


def expand_glossary(text: str) -> str:
    words = re.findall(r"\w+|\W+", text.lower())
    return "".join(f"{w} {GLOSSARY[w]}" if w in GLOSSARY else w for w in words)


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOP]


@dataclass
class Chunk:
    chunk_id: str              # e.g. "POL-RET-207#4.2 Senior citizen waiver"
    doc_id: str
    title: str
    section: str
    text: str
    version: int
    effective: str
    status: str
    groups: list[str] = field(default_factory=list)

    @property
    def indexed_text(self) -> str:
        # Contextual header: title + section are prepended so short chunks stay findable.
        return f"{self.title}. {self.section}. {self.text}"


def load_chunks(path: Path = CORPUS) -> list[Chunk]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for d in data["documents"]:
        for sec, txt in d["sections"].items():
            out.append(Chunk(f"{d['doc_id']}#{sec}", d["doc_id"], d["title"], sec, txt,
                             d["version"], d["effective"], d["status"], d["groups"]))
    return out


def load_golden(path: Path = GOLDEN) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["items"]


# ---------------------------------------------------------------- BM25
class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.toks = [tokenize(d) for d in docs]
        self.k1, self.b = k1, b
        self.avgdl = sum(map(len, self.toks)) / len(self.toks)
        df: dict[str, int] = {}
        for t in self.toks:
            for w in set(t):
                df[w] = df.get(w, 0) + 1
        n = len(docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}

    def scores(self, query: str) -> np.ndarray:
        q = tokenize(query)
        out = np.zeros(len(self.toks))
        for i, t in enumerate(self.toks):
            dl = len(t)
            for w in q:
                f = t.count(w)
                if f:
                    out[i] += self.idf.get(w, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return out


# ---------------------------------------------------------------- Dense
class Embedder:
    """Real embeddings when available, LSA fallback otherwise."""

    def __init__(self, fit_texts: list[str], model: str = "BAAI/bge-small-en-v1.5", force_offline: bool = False):
        self.kind = "lsa-offline"  # placeholder until a backend loads
        if not force_offline:
            try:
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(model)
                self.kind = f"sentence-transformers:{model}"
            except Exception:
                pass
        if self.kind == "lsa-offline":
            # Offline stand-in: character n-gram TF-IDF over glossary-expanded text.
            # Character n-grams catch morphology (withdraw/withdrawal); the glossary
            # expands bank acronyms (FD → fixed deposit), as real deployments do.
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.kind = "offline char-ngram TF-IDF + acronym glossary (install sentence-transformers for real embeddings)"
            self.tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
                                         preprocessor=expand_glossary)
            self.tfidf.fit(fit_texts)

    def encode(self, texts: list[str]) -> np.ndarray:
        if self.kind.startswith("sentence-transformers"):
            v = np.asarray(self.model.encode(texts, normalize_embeddings=True))
        else:
            v = self.tfidf.transform(texts).toarray()
        n = np.linalg.norm(v, axis=1, keepdims=True)
        return v / np.where(n == 0, 1, n)


# ---------------------------------------------------------------- Retriever
class Retriever:
    def __init__(self, chunks: list[Chunk], force_offline: bool = False):
        self.chunks = chunks
        texts = [c.indexed_text for c in chunks]
        self.bm25 = BM25(texts)
        self.embedder = Embedder(texts, force_offline=force_offline)
        self.vecs = self.embedder.encode(texts)

    def _rank(self, scores: np.ndarray, mask: np.ndarray | None) -> list[int]:
        s = scores.astype(float).copy()
        if mask is not None:
            s[~mask] = -np.inf
        order = [int(i) for i in np.argsort(-s) if np.isfinite(s[i])]
        return order

    def keyword(self, q: str, k: int = 5, mask=None) -> list[Chunk]:
        return [self.chunks[i] for i in self._rank(self.bm25.scores(q), mask)[:k]]

    def dense(self, q: str, k: int = 5, mask=None) -> list[Chunk]:
        qv = self.embedder.encode([q])[0]
        return [self.chunks[i] for i in self._rank(self.vecs @ qv, mask)[:k]]

    def hybrid(self, q: str, k: int = 5, mask=None, rrf_k: int = 60, depth: int = 20) -> list[Chunk]:
        """Reciprocal Rank Fusion of keyword + dense rankings."""
        kw = self._rank(self.bm25.scores(q), mask)[:depth]
        qv = self.embedder.encode([q])[0]
        de = self._rank(self.vecs @ qv, mask)[:depth]
        fused: dict[int, float] = {}
        for ranking in (kw, de):
            for r, i in enumerate(ranking):
                fused[i] = fused.get(i, 0) + 1 / (rrf_k + r + 1)
        top = sorted(fused, key=fused.get, reverse=True)[:k]
        return [self.chunks[i] for i in top]


def recall_at_k(results: list[Chunk], expected: list[str]) -> float:
    if not expected:
        return 1.0
    got = {c.chunk_id for c in results}
    return sum(e in got for e in expected) / len(expected)
