# AI System Design Interview Rubric

Score each dimension from 1 to 10. Used in every episode's "how would an interviewer grade this?" segment and in the Ep 12 mock interview.

| Dimension | 3/10 looks like | 7/10 looks like | 10/10 looks like |
| --- | --- | --- | --- |
| **Requirements** | Starts drawing immediately | Lists functional and non-functional requirements | Adds AI-specific needs (quality, cost ceiling, data sensitivity) and confirms scope |
| **Estimates** | None | Traffic and storage | Traffic, tokens, cost/request, monthly bill, used to justify design choices |
| **Architecture** | Boxes without purpose | Clear components and data flow | Every box justified; simplest design first, then evolves |
| **AI-specific depth** | "Call the LLM" | Sensible RAG/agent design | Chunking, retrieval quality, routing, context limits, tool safety, all with trade-offs |
| **Reliability** | Not mentioned | Retries and a fallback | Failure-mode table, timeouts, circuit breakers, degraded mode |
| **Security & compliance** | "Add auth" | RBAC + encryption | Prompt injection, PII flow, least-privilege tools, audit trail, data residency |
| **Evals & monitoring** | Not mentioned | Logs and latency dashboards | Golden set, offline metrics, regression gates, online feedback loop |
| **Trade-offs** | Every choice "best" | Mentions alternatives | Explicit decisions, the rejected options and why |
| **Communication** | Unstructured | Follows a structure | Drives the conversation, checks in, manages time |

**Bar for "hire":** average ≥ 7 with no dimension below 5.
