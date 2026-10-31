# Northwind Bank — the running case study

> **Northwind Bank is fictional.** All of its people, numbers, policies and incidents are invented for teaching. Any resemblance to a real bank is coincidental.

Each episode of the series opens with a new demand from Northwind. The platform you design grows week by week, from a policy Q&A bot into a governed, agentic AI platform.

## Company profile

| Attribute | Value |
| --- | --- |
| Type | Mid-size retail + SME bank |
| Customers | 4 million retail, 120,000 SME |
| Employees | 9,000 (5,500 branch & operations, 1,800 technology, 900 risk & compliance, 800 other) |
| Geography | India (HQ Hyderabad) and a US subsidiary (Charlotte, NC) |
| Regulators (illustrative) | Indian banking regulator + India's DPDP Act for personal data; US federal and state regulators, model risk guidance (SR 11-7) |
| Core systems | Core banking, loan origination system (LOS), CRM, document management (SharePoint + a DMS), identity provider (Entra ID / Okta-style SSO) |
| Data residency | Indian customer data must stay in India; US data stays in the US |
| Risk appetite | Low. "Nothing leaves without an audit trail." |

## Cast of characters (used in cold opens)

| Name | Role | Typical demand |
| --- | --- | --- |
| Priya Raman | Chief Digital Officer | "Ship something useful by quarter-end." |
| Daniel Brooks | CISO | "Show me how it can't leak." |
| Meera Iyer | Head of Retail Lending | "Loan files take 6 days to process. Make it 1." |
| Arjun Shah | Platform engineering lead | "Who's paying for all these tokens?" |
| Karen Liu | Internal audit (US) | "Why did the bot say this on 3 March?" |
| You | AI solutions architect | Design it, defend it, ship it |

## The platform's evolution

| Arc | Episodes | Northwind's demand | What gets built |
| --- | --- | --- | --- |
| Foundations | 1–4 | "Employees can't find policies. Fix it without leaking anything, and control the cost." | Design framework → RAG v1 → permission-aware RAG → LLM gateway |
| Automation | 5–7 | "Process loan documents automatically, then let agents act." | Document pipeline → MCP tool-calling agent → multi-agent credit memo |
| Hardening | 8–11 | "It's slow, expensive, fell over at month-end, and audit wants proof." | Caching & routing → resilience → evals & observability → security & governance |
| Capstone | 12 | "Design our KYC and fraud copilot." | Full reference architecture, defended in a mock interview |

See [assumptions.md](assumptions.md) for every number used in the estimates.
