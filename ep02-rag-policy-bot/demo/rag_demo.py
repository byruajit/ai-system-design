"""
Ep 2 demo — RAG v1 vs v2 on Northwind's policy corpus.

    python rag_demo.py                 # retrieval scoreboard (offline OK)
    python rag_demo.py --ask "Can a senior citizen break a 2-year FD early?"
    python rag_demo.py --ask "..." --llm    # also generate an answer

LLM step (optional) uses any OpenAI-compatible endpoint:
    export LLM_BASE_URL=https://api.groq.com/openai/v1   # or http://localhost:11434/v1 for Ollama
    export LLM_API_KEY=...                                # "ollama" for Ollama
    export LLM_MODEL=llama-3.1-8b-instant                 # or llama3.1 for Ollama
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from nwlib import Retriever, load_chunks, load_golden, recall_at_k  # noqa: E402

PROMPT = """You are Northwind Bank's internal policy assistant.
Answer ONLY from the context below. Cite every fact as [doc_id §section].
If the context does not contain the answer, reply exactly: "I couldn't find this in current policy. Please contact the policy desk."

Context:
{context}

Question: {question}
Answer:"""


def scoreboard(r: Retriever, k: int) -> None:
    golden = [g for g in load_golden() if not g.get("unanswerable") and not g.get("restricted_to")]
    active = np.array([c.status == "active" for c in r.chunks])
    strategies = {
        "v1  dense top-k": lambda q: r.dense(q, k),
        "    keyword (BM25)": lambda q: r.keyword(q, k),
        "v2  hybrid (RRF)": lambda q: r.hybrid(q, k),
        "v2+ hybrid + active-only filter": lambda q: r.hybrid(q, k, mask=active),
    }
    print(f"Embeddings: {r.embedder.kind}\nGolden questions: {len(golden)}   metric: recall@{k}\n")
    for name, fn in strategies.items():
        rec, stale = [], 0
        for g in golden:
            res = fn(g["question"])
            rec.append(recall_at_k(res, g["expected_sources"]))
            stale += any(c.status == "superseded" for c in res)
        print(f"  {name:<34} recall@{k} = {np.mean(rec):.2f}   answers exposed to superseded policy: {stale}")
    print("\nRead the scoreboard honestly: on a 12-document toy corpus every method scores about the same;"
          "\nthe gap between dense, keyword and hybrid widens on a real 50,000-document corpus (run it on yours)."
          "\nWhat the toy corpus DOES show: without a status/version filter, superseded policy reaches the prompt.")


def llm(prompt: str) -> str:
    base, key, model = os.getenv("LLM_BASE_URL"), os.getenv("LLM_API_KEY"), os.getenv("LLM_MODEL")
    if not (base and key and model):
        return "(LLM not configured — set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL. Prompt shown above.)"
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": model, "temperature": 0,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)["choices"][0]["message"]["content"]


def ask(r: Retriever, q: str, k: int, use_llm: bool) -> None:
    active = np.array([c.status == "active" for c in r.chunks])
    hits = r.hybrid(q, k, mask=active)
    context = "\n".join(f"[{c.doc_id} §{c.section}] (v{c.version}, effective {c.effective}) {c.text}" for c in hits)
    prompt = PROMPT.format(context=context, question=q)
    print(prompt)
    if use_llm:
        print("\n--- model answer ---\n" + llm(prompt))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--ask")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--offline", action="store_true", help="force the LSA fallback embedder")
    a = ap.parse_args()
    r = Retriever(load_chunks(), force_offline=a.offline)
    if a.ask:
        ask(r, a.ask, a.k, a.llm)
    else:
        scoreboard(r, a.k)


if __name__ == "__main__":
    main()
