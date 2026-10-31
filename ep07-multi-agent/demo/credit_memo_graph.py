"""
Ep 7 demo — a credit-memo workflow as a LangGraph state graph (offline, stubbed LLM).

    pip install langgraph
    python credit_memo_graph.py

Design shown:
  * deterministic data gathering (no agent needed to call 3 known APIs)
  * ONE drafting agent + ONE critic, sharing a TYPED state (not free-form chat)
  * critic loop with a hard retry cap
  * checkpointer, so the run can pause for human sign-off and resume later
  * a cost comparison against a five-agent "crew"

Replace `draft_llm` / `critic_llm` with real model calls through your gateway (Ep 4).
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

MAX_REVISIONS = 2


class MemoState(TypedDict, total=False):
    application_id: str
    facts: dict            # from systems of record: never invented by a model
    draft: str
    critique: list[str]
    revisions: int
    tokens: int
    status: str
    officer_decision: str


# ---- nodes -------------------------------------------------------------------
def gather(state: MemoState) -> MemoState:
    """Deterministic: call LOS, bureau and bank-statement APIs (stubbed)."""
    facts = {"applicant": "Kavya Menon", "loan_inr": 48_00_000, "property_inr": 65_00_000,
             "net_income_inr": 1_44_200, "existing_emi_inr": 12_000, "proposed_emi_inr": 42_500,
             "bureau_score": 772, "dpd_12m": 0}
    facts["ltv"] = round(facts["loan_inr"] / facts["property_inr"], 3)
    facts["foir"] = round((facts["existing_emi_inr"] + facts["proposed_emi_inr"]) / facts["net_income_inr"], 3)
    return {"facts": facts, "revisions": 0, "tokens": 0}


def draft_llm(facts: dict, critique: list[str]) -> str:
    """Stub for the drafting model. First draft forgets the policy citations, like real models often do."""
    memo = (f"Applicant {facts['applicant']} seeks INR {facts['loan_inr']:,} against a property valued at "
            f"INR {facts['property_inr']:,}. LTV is {facts['ltv']:.1%}; FOIR is {facts['foir']:.1%}. "
            f"Bureau score {facts['bureau_score']} with {facts['dpd_12m']} DPD in 12 months. Recommend approval.")
    if critique:
        memo += " Policy checks: LTV within 80% cap (POL-CRD-212 §5.1); FOIR within 55% (POL-CRD-212 §5.3)."
    return memo


def critic_llm(draft: str, facts: dict) -> list[str]:
    """Stub for the critic. In production: a model with a checklist + deterministic checks."""
    issues = []
    if "POL-CRD-212" not in draft:
        issues.append("Cite the policy sections for LTV and FOIR.")
    for key in ("ltv", "foir"):
        if f"{facts[key]:.1%}" not in draft:
            issues.append(f"{key.upper()} in memo does not match source facts.")
    return issues


def draft(state: MemoState) -> MemoState:
    return {"draft": draft_llm(state["facts"], state.get("critique", [])),
            "tokens": state["tokens"] + 4_000}


def critic(state: MemoState) -> MemoState:
    return {"critique": critic_llm(state["draft"], state["facts"]),
            "revisions": state["revisions"] + 1, "tokens": state["tokens"] + 3_000}


def route_after_critic(state: MemoState) -> str:
    if not state["critique"]:
        return "human_signoff"
    return "draft" if state["revisions"] <= MAX_REVISIONS else "escalate"


def human_signoff(state: MemoState) -> MemoState:
    decision = state.get("officer_decision")
    return {"status": f"SIGNED_OFF: {decision}" if decision else "AWAITING_CREDIT_OFFICER_SIGNOFF"}


def escalate(state: MemoState) -> MemoState:
    return {"status": "ESCALATED_TO_ANALYST (critic not satisfied after retries)"}


# ---- graph -------------------------------------------------------------------
def build():
    g = StateGraph(MemoState)
    for name, fn in [("gather", gather), ("draft", draft), ("critic", critic),
                     ("human_signoff", human_signoff), ("escalate", escalate)]:
        g.add_node(name, fn)
    g.add_edge(START, "gather")
    g.add_edge("gather", "draft")
    g.add_edge("draft", "critic")
    g.add_conditional_edges("critic", route_after_critic, ["draft", "human_signoff", "escalate"])
    g.add_edge("human_signoff", END)
    g.add_edge("escalate", END)
    # interrupt_before pauses the run so a credit officer can review; state is checkpointed
    return g.compile(checkpointer=MemorySaver(), interrupt_before=["human_signoff"])


def main() -> None:
    app = build()
    cfg = {"configurable": {"thread_id": "LN-1001"}}
    for event in app.stream({"application_id": "LN-1001"}, cfg, stream_mode="updates"):
        node, update = next(iter(event.items()))
        if node == "__interrupt__":
            continue
        detail = update.get("critique", update.get("status", ""))
        print(f"  {node:<14} {detail if detail != [] else 'critic: no issues'}")
    snap = app.get_state(cfg)
    print(f"\nPaused before: {snap.next}  (checkpointed — a credit officer reviews the draft)")
    print("Draft:\n  " + snap.values["draft"])
    app.update_state(cfg, {"officer_decision": "approved by credit officer O-42"})
    for event in app.stream(None, cfg, stream_mode="updates"):
        pass
    final = app.get_state(cfg).values
    print(f"\nFinal status: {final['status']}   revisions: {final['revisions']}   tokens: {final['tokens']:,}")

    crew_tokens = 5 * 4 * 6_000   # ASSUMPTION: 5 agents × 4 turns each × ~6k-token shared transcript
    print(f"Five-agent 'crew' (assumed 5 agents × 4 turns × 6k tokens): ~{crew_tokens:,} tokens "
          f"→ {crew_tokens / final['tokens']:.1f}× this graph")


if __name__ == "__main__":
    main()
