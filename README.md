# AI System Design — from whiteboard to production

A free 12-episode YouTube series on **AI Engineering with Ajit** (@AjitByru). Starting 31 Oct 2026, with new sessions every Wednesday, Saturday and Sunday, each episode designs one real AI system for **Northwind Bank** (fictional) and defends it the way you would in an interview *and* in an architecture review.

> **Promise:** after each episode you can whiteboard the system in 45 minutes and defend it in a design review.

## Episodes

| # | Date | Episode | Interview question | Demo |
| --- | --- | --- | --- | --- |
| 1 | Sat 31 Oct 2026 | [The AI System Design Interview Playbook](ep01-playbook/) | "How would you approach any AI system design question?" | Token & cost estimator |
| 2 | Wed 4 Nov 2026 | [Policy Q&A Bot: RAG from First Principles](ep02-rag-policy-bot/) | "Chatbot over 50,000 internal documents" | Dense vs keyword vs hybrid scoreboard |
| 3 | Sat 7 Nov 2026 | [Permission-Aware RAG at Scale](ep03-permission-aware-rag/) | "Keep RAG fresh and stop it leaking" | ACLs, tombstones, blue-green index |
| 4 | Sun 8 Nov 2026 | [Design an LLM Gateway](ep04-llm-gateway/) | "Choose and route between multiple LLMs" | Routing, budgets, outage simulation |
| 5 | Wed 11 Nov 2026 | [Loan Document Processing](ep05-loan-doc-processing/) | "Extract data from 100,000 scanned pages a day" | Validation, cross-checks, idempotency |
| 6 | Sat 14 Nov 2026 | [Tool-Calling Agent with MCP](ep06-mcp-agent/) | "An agent that acts on accounts safely" | MCP server + injection vs guardrails |
| 7 | Sun 15 Nov 2026 | [Multi-Agent Systems](ep07-multi-agent/) | "Multi-agent credit memos" | LangGraph critic loop + checkpoint |
| 8 | Wed 18 Nov 2026 | [Make It Fast and Cheap](ep08-fast-and-cheap/) | "Bill tripled, p95 is 9 s" | Safe semantic cache |
| 9 | Sat 21 Nov 2026 | [Make It Survive Month-End](ep09-reliability/) | "The provider went down at peak" | Circuit breaker simulation |
| 10 | Sun 22 Nov 2026 | [Evals and Observability](ep10-evals-observability/) | "How do you know answers are correct?" | Eval gate for CI |
| 11 | Wed 25 Nov 2026 | [Secure and Govern It](ep11-security-governance/) | "Secure an LLM app in a regulated bank" | Guardrails + promptfoo red-team |
| 12 | Sat 28 Nov 2026 | [Capstone: KYC & Fraud Copilot](ep12-capstone-kyc-fraud/) | "AI-assisted KYC and fraud review" | ML scores, LLM explains |

## Repo map

```
framework/   9-step playbook · estimation formulas · interview rubric
northwind/   case study · assumptions (every number) · synthetic policy corpus · golden set
tools/       cost_estimator.py · nwlib.py (retrieval helpers) · render.py (cheat sheets + diagrams)
epNN-*/      README (design + model answers) · cheatsheet.pdf · diagrams/ (Mermaid + PNG) · demo/ (runnable code)
```

## Run the demos

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python tools/cost_estimator.py --compare --route small=0.7,large=0.3
python ep02-rag-policy-bot/demo/rag_demo.py
```

Every demo runs **offline** (no API keys). Where an LLM call adds value (Ep 2), set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` for any OpenAI-compatible endpoint (Groq free tier, or Ollama locally). Install `sentence-transformers` for real embeddings; otherwise an offline stand-in is used and labelled on screen.

## Honesty notes
- **Northwind Bank is fictional.** Its policies, people and numbers are invented for teaching.
- **Prices are illustrative tiers** (`tools/prices.json`), not any provider's price list. Update them before quoting.
- Toy corpora make some retrieval differences look small; the scripts say so, and you should run them on your own data.

## Design challenge
Each episode ends with a design challenge. Answer in the YouTube comments or open a PR; the best answer is featured in the next session.
