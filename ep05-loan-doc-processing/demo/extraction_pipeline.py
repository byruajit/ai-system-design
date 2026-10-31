"""
Ep 5 demo — the hard part of document AI is not extraction, it's TRUST.

    python extraction_pipeline.py

Pipeline per loan file:
  extract (simulated model output: per-field value + confidence + source page)
  → schema validation (Pydantic)
  → business rules (PAN format, salary cross-check, LTV and FOIR from POL-CRD-212)
  → routing: auto-accept / human review (only the failing fields)
  → idempotent write (key = file hash + pipeline version), so retries never duplicate

Swap `simulated_extract()` for a real OCR+LLM or vision-model call that returns the
same JSON shape (structured output / JSON schema mode).
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

PIPELINE_VERSION = "extract-v3.2"
CONFIDENCE_THRESHOLD = 0.85
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


class Extracted(BaseModel):
    value: Optional[str]
    confidence: float = Field(ge=0, le=1)
    page: Optional[int] = None          # provenance: where the value was read


class LoanApplication(BaseModel):
    applicant_name: Extracted
    pan: Extracted
    employer: Extracted
    monthly_net_income_inr: Extracted
    payslip_net_income_inr: Extracted   # read from the payslip page, for cross-check
    existing_emi_inr: Extracted
    loan_amount_inr: Extracted
    property_value_inr: Extracted
    proposed_emi_inr: Extracted

    @field_validator("pan")
    @classmethod
    def pan_format(cls, v: Extracted) -> Extracted:
        if v.value and not PAN_RE.match(v.value):
            raise ValueError(f"PAN '{v.value}' fails format AAAAA9999A")
        return v


def num(x: Extracted) -> float:
    return float(str(x.value).replace(",", ""))


def ltv_cap(loan: float) -> float:          # POL-CRD-212 §5.1 (synthetic)
    if loan <= 30_00_000:
        return 0.90
    return 0.80 if loan <= 75_00_000 else 0.75


def business_rules(app: LoanApplication) -> list[str]:
    issues = []
    stated, payslip = num(app.monthly_net_income_inr), num(app.payslip_net_income_inr)
    if abs(stated - payslip) / payslip > 0.05:
        issues.append(f"monthly_net_income_inr: form says {stated:,.0f}, payslip says {payslip:,.0f} (>5% gap)")
    loan, prop = num(app.loan_amount_inr), num(app.property_value_inr)
    if loan / prop > ltv_cap(loan):
        issues.append(f"loan_amount_inr: LTV {loan / prop:.0%} exceeds cap {ltv_cap(loan):.0%} (POL-CRD-212 §5.1)")
    foir = (num(app.existing_emi_inr) + num(app.proposed_emi_inr)) / payslip
    if foir > 0.55:
        issues.append(f"proposed_emi_inr: FOIR {foir:.0%} exceeds 55% for salaried (POL-CRD-212 §5.3)")
    return issues


def simulated_extract(file_name: str) -> dict:
    """Stands in for OCR+LLM / vision model output. File C contains a typical hallucination."""
    base = {
        "applicant_name": {"value": "Kavya Menon", "confidence": 0.98, "page": 1},
        "pan": {"value": "ABCPM1234K", "confidence": 0.97, "page": 2},
        "employer": {"value": "Infotech Solutions Pvt Ltd", "confidence": 0.93, "page": 4},
        "monthly_net_income_inr": {"value": "1,45,000", "confidence": 0.95, "page": 1},
        "payslip_net_income_inr": {"value": "1,44,200", "confidence": 0.96, "page": 4},
        "existing_emi_inr": {"value": "12,000", "confidence": 0.91, "page": 6},
        "loan_amount_inr": {"value": "48,00,000", "confidence": 0.99, "page": 1},
        "property_value_inr": {"value": "65,00,000", "confidence": 0.94, "page": 9},
        "proposed_emi_inr": {"value": "42,500", "confidence": 0.92, "page": 1},
    }
    if file_name == "LN-1002.pdf":   # blurry scan: low confidence on PAN, and the PAN fails format
        base["pan"] = {"value": "ABCPM12З4K", "confidence": 0.61, "page": 2}
    if file_name == "LN-1003.pdf":   # model "fills in" income: payslip unreadable, value invented
        base["payslip_net_income_inr"] = {"value": "92,000", "confidence": 0.88, "page": 4}
        base["employer"] = {"value": "Infotech Solutions", "confidence": 0.72, "page": 4}
    return base


STORE: dict[str, dict] = {}   # pretend database, keyed by idempotency key


def process(file_name: str, file_bytes: bytes) -> dict:
    key = hashlib.sha256(file_bytes + PIPELINE_VERSION.encode()).hexdigest()[:16]
    if key in STORE:                                   # retry / duplicate delivery
        return {**STORE[key], "note": "duplicate delivery ignored (idempotent)"}
    raw = simulated_extract(file_name)
    review: list[str] = []
    try:
        app = LoanApplication.model_validate(raw)
        review += business_rules(app)
    except ValidationError as e:
        review += [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
    review += [f"{k}: low confidence {v['confidence']:.2f} (page {v['page']})"
               for k, v in raw.items() if v["confidence"] < CONFIDENCE_THRESHOLD]
    result = {"file": file_name, "key": key,
              "status": "AUTO_ACCEPTED" if not review else "HUMAN_REVIEW",
              "review_fields": sorted(set(review))}
    STORE[key] = result
    return result


def main() -> None:
    files = {"LN-1001.pdf": b"%PDF clean scan", "LN-1002.pdf": b"%PDF blurry scan", "LN-1003.pdf": b"%PDF payslip smudged"}
    for name, data in files.items():
        r = process(name, data)
        print(f"\n{r['file']}  →  {r['status']}   (idempotency key {r['key']})")
        for issue in r["review_fields"]:
            print(f"    ⚑ {issue}")
    print("\nRetry storm: the queue redelivers LN-1001.pdf twice")
    for _ in range(2):
        print("   ", process("LN-1001.pdf", files["LN-1001.pdf"]).get("note", "processed"))
    print(f"\nRecords stored: {len(STORE)} (not 5)")


if __name__ == "__main__":
    main()
