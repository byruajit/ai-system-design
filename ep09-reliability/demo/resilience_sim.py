"""
Ep 9 demo — the same month-end outage under three designs (simulated clock, runs instantly).

    python resilience_sim.py

Scenario: 3,000 requests over 10 minutes (month-end burst). The primary LLM provider
goes down from minute 2 to minute 6 (requests hang until timeout).

Designs:
  A. naive:     30 s timeout, 3 immediate retries, no fallback
  B. retries:   8 s timeout, exponential backoff + jitter, fallback provider
  C. resilient: B + circuit breaker (skip the dead provider instantly) + degraded mode
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

random.seed(9)
N, WINDOW_S = 3000, 600
OUTAGE = (120, 360)


def primary(t: float) -> tuple[bool, float]:
    if OUTAGE[0] <= t < OUTAGE[1]:
        return False, float("inf")                 # hangs until timeout
    return random.random() > 0.01, random.uniform(1.0, 3.0)


def backup(t: float) -> tuple[bool, float]:
    return random.random() > 0.02, random.uniform(1.5, 3.5)


@dataclass
class Breaker:
    threshold: int = 5          # consecutive failures to open
    cooldown_s: float = 30      # then allow one probe (half-open)
    fails: int = 0
    opened_at: float | None = None
    log: list = field(default_factory=list)

    def allow(self, t: float) -> bool:
        if self.opened_at is None:
            return True
        if t - self.opened_at >= self.cooldown_s:   # half-open: let one probe through
            return True
        return False

    def record(self, ok: bool, t: float) -> None:
        if ok:
            if self.opened_at is not None:
                self.log.append((round(t), "CLOSED (probe succeeded)"))
            self.fails, self.opened_at = 0, None
        else:
            self.fails += 1
            if self.opened_at is not None and t - self.opened_at >= self.cooldown_s:
                self.opened_at = t
                self.log.append((round(t), "half-open probe failed → OPEN"))
            elif self.opened_at is None and self.fails >= self.threshold:
                self.opened_at = t
                self.log.append((round(t), "OPEN"))


def call_with_timeout(fn, t, timeout):
    ok, lat = fn(t)
    return (ok and lat <= timeout), min(lat, timeout)


def design_a(t):
    total, calls = 0.0, 0
    for _ in range(4):                               # 1 try + 3 immediate retries
        ok, lat = call_with_timeout(primary, t + total, 30)
        total += lat
        calls += 1
        if ok:
            return "ok", total, calls
    return "error", total, calls


def design_b(t):
    total, calls = 0.0, 0
    for attempt in range(3):
        ok, lat = call_with_timeout(primary, t + total, 8)
        total += lat
        calls += 1
        if ok:
            return "ok", total, calls
        total += min(4, 0.5 * 2 ** attempt) * random.uniform(0.5, 1.5)   # backoff + jitter
    ok, lat = call_with_timeout(backup, t + total, 8)
    return ("fallback" if ok else "error"), total + lat, calls


BREAKER = Breaker()


def design_c(t):
    total, calls = 0.0, 0
    if BREAKER.allow(t):
        ok, lat = call_with_timeout(primary, t, 8)
        calls += 1
        BREAKER.record(ok, t)
        total += lat
        if ok:
            return "ok", total, calls
    ok, lat = call_with_timeout(backup, t + total, 8)
    if ok:
        return "fallback", total + lat, calls
    return "degraded", total + lat, calls            # e.g. keyword search results + "AI is busy" banner


def run(name, fn):
    arrivals = sorted(random.uniform(0, WINDOW_S) for _ in range(N))
    res = [fn(t) for t in arrivals]
    lat = sorted(r[1] for r in res)
    p95 = lat[int(0.95 * len(lat)) - 1]
    outcome = {k: sum(r[0] == k for r in res) for k in ("ok", "fallback", "degraded", "error")}
    primary_calls = sum(r[2] for r in res)
    print(f"{name:<30} p95 {p95:6.1f}s   calls to primary {primary_calls:5}   " +
          "  ".join(f"{k} {v}" for k, v in outcome.items()))


if __name__ == "__main__":
    print(f"{N} requests in {WINDOW_S // 60} min; primary down from minute {OUTAGE[0] // 60} to {OUTAGE[1] // 60}\n")
    run("A naive (30 s, 3 retries)", design_a)
    run("B backoff + fallback", design_b)
    run("C + circuit breaker", design_c)
    print("\nCircuit breaker transitions (t in seconds):")
    for t, ev in BREAKER.log[:2] + [("…", "…")] + BREAKER.log[-2:]:
        print(f"   {t:>5}  {ev}")
    print("\nA hammers a dead provider (a retry storm) and users wait minutes. B survives but every request")
    print("still burns 3 timeouts first. C stops calling the dead provider within seconds and probes for recovery.")
