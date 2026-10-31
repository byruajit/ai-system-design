# Ep 7 · Multi-Agent Design — Cheat Sheet

## An agent must earn its tokens
Add an agent only for: **separation of duties** (tools/permissions) · **parallelism** · **independent check** (critic)

## Patterns
| Pattern | Use when |
| --- | --- |
| Single agent + tools | Default |
| Pipeline / workflow | Known process |
| Orchestrator → workers | Parallel sources |
| Generator ↔ critic | Quality/compliance gate |
| Free-form crew | Demos only |

## v2 recipe (credit memo)
1. **Gather facts with code**
2. **Typed state**; facts read-only
3. One **drafter** + one **critic** (code checks + checklist)
4. **Retry cap** (2) → escalate
5. **Checkpoint** for human sign-off
6. Parallel branches only where slow

## Cost
Crew ≈ 5 agents × 4 turns × 6k = **120k tokens**
Graph ≈ **14k** → **~8.6× cheaper** *(assumptions)*

## Reproducibility
Fixed topology · temperature 0 · pinned models · structured output · checkpoints

## Debug & audit
Trace every node (inputs, outputs, model, tokens) · replay from checkpoints · prod failures → regression tests

## Say this
"Multi-agent is a pattern, not a goal. Here's what each agent buys us."
