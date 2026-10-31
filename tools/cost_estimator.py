"""
Token & cost estimator for AI system design interviews (AI System Design series, Ep 1).

Usage:
    python cost_estimator.py                      # Northwind policy bot defaults
    python cost_estimator.py --users 9000 --active 0.3 --queries 4 --model large
    python cost_estimator.py --compare            # all tiers side by side
    python cost_estimator.py --route small=0.7,large=0.3   # blended cost with routing

Everything is plain arithmetic so viewers can redo it on a whiteboard:
    tokens_in  = system_prompt + history + retrieved_context + question
    cost/query = tokens_in * price_in/1e6 + tokens_out * price_out/1e6
    queries/day = employees * daily_active_share * queries_per_user
    peak QPS   = queries/day * peak_share / (peak_hours * 3600) * burst_factor
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

PRICES = json.loads((Path(__file__).parent / "prices.json").read_text())


@dataclass
class Workload:
    employees: int = 9000
    daily_active_share: float = 0.30
    queries_per_user: float = 4
    workdays_per_month: int = 22
    peak_share: float = 0.60       # share of daily traffic in the peak window
    peak_hours: float = 4          # length of the peak window
    burst_factor: float = 5        # spikes inside the peak window
    system_prompt_tokens: int = 500
    history_tokens: int = 300
    chunks: int = 5
    chunk_tokens: int = 400
    question_tokens: int = 50
    output_tokens: int = 300

    @property
    def input_tokens(self) -> int:
        return (self.system_prompt_tokens + self.history_tokens
                + self.chunks * self.chunk_tokens + self.question_tokens)

    @property
    def queries_per_day(self) -> float:
        return self.employees * self.daily_active_share * self.queries_per_user

    @property
    def queries_per_month(self) -> float:
        return self.queries_per_day * self.workdays_per_month

    @property
    def avg_peak_qps(self) -> float:
        return self.queries_per_day * self.peak_share / (self.peak_hours * 3600)

    @property
    def burst_qps(self) -> float:
        return self.avg_peak_qps * self.burst_factor


def cost_per_query(w: Workload, model: str) -> float:
    p = PRICES["models"][model]
    return w.input_tokens * p["input"] / 1e6 + w.output_tokens * p["output"] / 1e6


def blended_cost_per_query(w: Workload, route: dict[str, float]) -> float:
    assert abs(sum(route.values()) - 1) < 1e-6, "route shares must sum to 1"
    return sum(share * cost_per_query(w, m) for m, share in route.items())


def fmt_money(usd: float) -> str:
    inr = usd * PRICES["usd_to_inr"]
    if usd < 0.1:
        return f"${usd:.5f} (₹{inr:.3f})"
    return f"${usd:,.2f} (₹{inr:,.0f})"


def report(w: Workload, models: list[str], route: dict[str, float] | None = None) -> str:
    lines = [
        "WORKLOAD",
        f"  queries/day        = {w.employees:,} × {w.daily_active_share:.0%} × {w.queries_per_user} = {w.queries_per_day:,.0f}",
        f"  queries/month      = {w.queries_per_day:,.0f} × {w.workdays_per_month} workdays = {w.queries_per_month:,.0f}",
        f"  avg peak QPS       = {w.queries_per_day:,.0f} × {w.peak_share:.0%} / ({w.peak_hours} h × 3600) = {w.avg_peak_qps:.2f}",
        f"  burst QPS (×{w.burst_factor:g})    = {w.burst_qps:.2f}",
        "TOKENS PER QUERY",
        f"  input  = {w.system_prompt_tokens} sys + {w.history_tokens} history + {w.chunks}×{w.chunk_tokens} context + {w.question_tokens} question = {w.input_tokens:,}",
        f"  output = {w.output_tokens}",
        "COST (illustrative prices — verify before quoting)",
    ]
    for m in models:
        c = cost_per_query(w, m)
        lines.append(f"  {m:<7} per query {fmt_money(c):<26} per month {fmt_money(c * w.queries_per_month)}")
    if route:
        c = blended_cost_per_query(w, route)
        mix = ", ".join(f"{int(s*100)}% {m}" for m, s in route.items())
        lines.append(f"  routed ({mix}) per query {fmt_money(c)} per month {fmt_money(c * w.queries_per_month)}")
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # ₹ and × crash cp1252 Windows consoles
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--users", type=int, default=9000)
    ap.add_argument("--active", type=float, default=0.30)
    ap.add_argument("--queries", type=float, default=4)
    ap.add_argument("--chunks", type=int, default=5)
    ap.add_argument("--chunk-tokens", type=int, default=400)
    ap.add_argument("--output-tokens", type=int, default=300)
    ap.add_argument("--model", default="large", choices=[m for m in PRICES["models"] if m != "embedding"])
    ap.add_argument("--compare", action="store_true", help="show all chat tiers")
    ap.add_argument("--route", help="blend, e.g. small=0.7,large=0.3")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    w = Workload(employees=a.users, daily_active_share=a.active, queries_per_user=a.queries,
                 chunks=a.chunks, chunk_tokens=a.chunk_tokens, output_tokens=a.output_tokens)
    models = ["small", "medium", "large"] if a.compare else [a.model]
    route = None
    if a.route:
        route = {k: float(v) for k, v in (p.split("=") for p in a.route.split(","))}
    if a.json:
        print(json.dumps({"workload": asdict(w), "input_tokens": w.input_tokens,
                          "queries_per_month": w.queries_per_month,
                          "cost_per_query": {m: cost_per_query(w, m) for m in models}}, indent=2))
    else:
        print(report(w, models, route))


if __name__ == "__main__":
    main()
