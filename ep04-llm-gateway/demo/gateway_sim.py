"""
Ep 4 demo — an LLM gateway in ~150 lines: routing, fallbacks, budgets, logging.

    python gateway_sim.py               # replay 2,000 Northwind requests offline
    python gateway_sim.py --outage large-primary   # simulate a provider outage

Providers are SIMULATED (latency, failure rate, price) so the demo runs anywhere.
In production you'd put a real gateway (e.g. LiteLLM proxy, a cloud AI gateway, or
your own service) in front of real providers. See litellm_config.yaml for the same ideas
in config form.
"""
from __future__ import annotations

import argparse
import random
from collections import Counter, defaultdict
from dataclasses import dataclass

random.seed(42)


@dataclass
class Provider:
    name: str
    tier: str
    price_in: float      # $ per 1M tokens (illustrative)
    price_out: float
    p50_ms: int
    fail_rate: float
    up: bool = True

    def call(self, tin: int, tout: int) -> tuple[bool, int, float]:
        if not self.up or random.random() < self.fail_rate:
            return False, 30_000 if not self.up else 800, 0.0   # timeout or 5xx
        ms = int(random.gauss(self.p50_ms, self.p50_ms * 0.25))
        return True, max(ms, 50), tin * self.price_in / 1e6 + tout * self.price_out / 1e6


PROVIDERS = {
    "small-primary": Provider("small-primary", "small", 0.15, 0.60, 450, 0.01),
    "small-backup": Provider("small-backup", "small", 0.20, 0.80, 600, 0.01),
    "large-primary": Provider("large-primary", "large", 3.00, 15.00, 2200, 0.02),
    "large-backup": Provider("large-backup", "large", 2.50, 10.00, 2600, 0.02),
}
FALLBACKS = {"small": ["small-primary", "small-backup", "large-primary"],
             "large": ["large-primary", "large-backup", "small-primary"]}  # last resort: degrade

TEAM_BUDGET_USD = {"retail-ops": 40.0, "credit": 25.0, "hr": 0.05}  # HR set low on purpose to show budget enforcement


def route(task: str, question: str) -> str:
    """Difficulty router: cheap model unless the task needs reasoning."""
    hard_tasks = {"credit-memo", "policy-compare", "complaint-draft"}
    if task in hard_tasks or len(question.split()) > 60:
        return "large"
    return "small"


def gateway(team: str, task: str, question: str, spend: dict, log: list) -> dict:
    tier = route(task, question)
    if spend[team] >= TEAM_BUDGET_USD[team]:
        log.append((team, task, tier, "BUDGET_BLOCKED", 0, 0.0))
        return {"status": 429, "reason": "team budget exhausted"}
    tin, tout = (2850, 300) if tier == "small" else (6000, 800)
    total_ms = 0
    for attempt, pname in enumerate(FALLBACKS[tier]):
        ok, ms, cost = PROVIDERS[pname].call(tin, tout)
        total_ms += min(ms, 8000)   # gateway timeout: 8 s per attempt
        if ok:
            spend[team] += cost
            log.append((team, task, tier, pname, total_ms, cost))
            return {"status": 200, "provider": pname, "ms": total_ms, "fallback_used": attempt > 0}
    log.append((team, task, tier, "ALL_FAILED", total_ms, 0.0))
    return {"status": 503, "reason": "all providers failed — degraded mode"}


def traffic(n: int):
    mix = [("retail-ops", "policy-qa", 0.62), ("retail-ops", "complaint-draft", 0.08),
           ("credit", "credit-memo", 0.10), ("credit", "policy-qa", 0.10), ("hr", "policy-qa", 0.10)]
    for _ in range(n):
        r, acc = random.random(), 0
        for team, task, w in mix:
            acc += w
            if r <= acc:
                yield team, task, "What is the counter cash withdrawal limit?"
                break


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--outage", choices=list(PROVIDERS))
    a = ap.parse_args()
    if a.outage:
        PROVIDERS[a.outage].up = False
        print(f"!! simulating outage of {a.outage}\n")

    spend, log = defaultdict(float), []
    results = [gateway(t, k, q, spend, log) for t, k, q in traffic(a.n)]

    status = Counter(r["status"] for r in results)
    fb = sum(r.get("fallback_used", False) for r in results)
    by_provider = Counter(entry[3] for entry in log)
    lat = sorted(entry[4] for entry in log if entry[3] not in ("BUDGET_BLOCKED", "ALL_FAILED"))
    p95 = lat[int(0.95 * len(lat)) - 1] if lat else 0
    all_large = sum((6000 * 3 + 800 * 15) / 1e6 if route(k, q) == "large" else (2850 * 3 + 300 * 15) / 1e6
                    for _, k, q in traffic(a.n))
    random.seed(42)

    print(f"Requests: {a.n}   200 OK: {status[200]}   429 budget: {status[429]}   503 failed: {status[503]}")
    print(f"Fallbacks used: {fb}   p95 latency: {p95} ms")
    print("Calls by provider:", dict(by_provider))
    print("Spend by team ($):", {k: round(v, 2) for k, v in spend.items()}, " budgets:", TEAM_BUDGET_USD)
    print(f"Total spend: ${sum(spend.values()):.2f}   vs same traffic all on the large tier: ≈${all_large:.2f}")
    if a.outage:
        print("\nNote the p95: every request first waits for the dead provider's timeout before falling back."
              "\nThat's why Ep 9 adds a circuit breaker: after a few failures, skip the dead provider instantly.")


if __name__ == "__main__":
    main()
