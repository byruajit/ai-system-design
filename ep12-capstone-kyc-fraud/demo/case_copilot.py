"""
Ep 12 demo — "The LLM is not the fraud model."

    python case_copilot.py

1. A classic ML model (logistic regression on SYNTHETIC onboarding data) scores fraud risk
   and gives reason codes (feature contributions). It's fast, calibrated and explainable to a validator.
2. The LLM's job is to write the analyst's case summary FROM those facts and reason codes,
   with citations to policy, and nothing else. The prompt is printed (offline); send it
   through your gateway to get the narrative.
3. The human analyst decides. Everything is logged.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

rng = np.random.default_rng(12)
FEATURES = ["face_match_score", "doc_tamper_score", "device_seen_on_other_accounts",
            "address_mismatch", "pep_or_sanctions_fuzzy_hit", "minutes_to_complete_onboarding"]


def synthetic(n: int = 20_000):
    X = np.column_stack([
        rng.beta(8, 2, n),                    # face match (higher = better)
        rng.beta(2, 8, n),                    # tamper score (higher = worse)
        rng.poisson(0.2, n),                  # device reuse count
        rng.binomial(1, 0.08, n),             # address mismatch
        rng.binomial(1, 0.01, n),             # fuzzy watchlist hit
        rng.gamma(4, 3, n),                   # onboarding minutes
    ])
    logit = (-4.0 - 4.0 * (X[:, 0] - 0.8) + 6.0 * (X[:, 1] - 0.2) + 1.2 * X[:, 2]
             + 1.0 * X[:, 3] + 1.5 * X[:, 4] - 0.05 * (X[:, 5] - 12))
    y = rng.random(n) < 1 / (1 + np.exp(-logit))
    return X, y.astype(int)


def main() -> None:
    X, y = synthetic()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=1, stratify=y)
    mu, sd = Xtr.mean(0), Xtr.std(0)
    model = LogisticRegression(max_iter=1000).fit((Xtr - mu) / sd, ytr)
    auc = roc_auc_score(yte, model.predict_proba((Xte - mu) / sd)[:, 1])
    print(f"1) FRAUD MODEL (classic ML)   fraud rate {y.mean():.1%}   test AUC {auc:.3f}")

    case = np.array([0.62, 0.71, 3, 1, 0, 2.5])        # one onboarding application
    z = (case - mu) / sd
    p = model.predict_proba(z.reshape(1, -1))[0, 1]
    contrib = model.coef_[0] * z
    reasons = sorted(zip(FEATURES, case, contrib), key=lambda r: -r[2])[:3]
    band = "HIGH" if p > 0.5 else "MEDIUM" if p > 0.1 else "LOW"
    print(f"   case NW-ONB-55102 → risk {p:.2f} ({band})")
    for f, v, c in reasons:
        print(f"     reason: {f} = {v:g}  (contribution {c:+.2f})")

    facts = "\n".join(f"- {f}: {v:g} (pushes risk {'up' if c > 0 else 'down'})" for f, v, c in reasons)
    prompt = f"""You are drafting a case summary for a Northwind KYC analyst. You do NOT decide.
Use only the facts below. Cite policy as [POL-KYC-009 §section] where relevant. 120 words max.
If a fact is missing, say so; never infer identity attributes.

Case: NW-ONB-55102   Model risk score: {p:.2f} ({band})   Model: onboarding-fraud-lr v3.1
Top reason codes:
{facts}
Other checks: sanctions/PEP screening = no confirmed hit; video KYC available (POL-KYC-009 §4.1).

Write: (1) what was observed, (2) why the score is {band}, (3) what the analyst should verify next."""
    print("\n2) LLM CASE-SUMMARY PROMPT (send via the gateway; the LLM explains, it doesn't score)\n")
    print(prompt)
    print("\n3) DECISION: analyst approves / rejects / requests V-CIP → logged with score, reasons, model versions.")


if __name__ == "__main__":
    main()
