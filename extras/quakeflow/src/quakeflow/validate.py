"""Data-quality gate. Nothing reaches the warehouse without passing these checks."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .logging_utils import get_logger
from .transform import SILVER_COLUMNS

log = get_logger(__name__)


class DataQualityError(RuntimeError):
    """Raised when a blocking expectation fails."""


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    blocking: bool = True


@dataclass
class ValidationReport:
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "", blocking: bool = True) -> None:
        self.checks.append(CheckResult(name, passed, detail, blocking))

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and c.blocking]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed and not c.blocking]

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        lines = []
        for check in self.checks:
            if check.passed:
                icon = "PASS"
            else:
                icon = "FAIL" if check.blocking else "WARN"
            lines.append(f"  [{icon}] {check.name}{(' - ' + check.detail) if check.detail else ''}")
        return "\n".join(lines)


def _between(series: pd.Series, low: float, high: float) -> int:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return int(((values < low) | (values > high)).sum())


def validate_events(df: pd.DataFrame, allow_empty: bool = False) -> ValidationReport:
    report = ValidationReport()

    missing = [c for c in SILVER_COLUMNS if c not in df.columns]
    report.add("schema.columns_present", not missing, f"missing: {missing}" if missing else "")
    if missing:
        raise DataQualityError(f"silver frame is missing columns: {missing}")

    report.add(
        "volume.not_empty",
        allow_empty or not df.empty,
        f"{len(df)} rows",
        blocking=not allow_empty,
    )
    if df.empty:
        log.warning("validation ran on an empty frame")
        _finish(report)
        return report

    null_ids = int(df["event_id"].isna().sum())
    report.add("keys.event_id_not_null", null_ids == 0, f"{null_ids} nulls")

    dupes = int(df["event_id"].duplicated().sum())
    report.add("keys.event_id_unique", dupes == 0, f"{dupes} duplicates")

    bad_mag = _between(df["magnitude"], -2.0, 10.5)
    report.add("range.magnitude", bad_mag == 0, f"{bad_mag} rows outside [-2, 10.5]")

    bad_lat = _between(df["latitude"], -90.0, 90.0)
    bad_lon = _between(df["longitude"], -180.0, 180.0)
    report.add("range.coordinates", bad_lat + bad_lon == 0, f"{bad_lat} lat / {bad_lon} lon")

    bad_depth = _between(df["depth_km"], -10.0, 800.0)
    report.add(
        "range.depth_km", bad_depth == 0, f"{bad_depth} rows outside [-10, 800]", blocking=False
    )

    future = int((df["event_time"] > pd.Timestamp.utcnow() + pd.Timedelta(hours=2)).sum())
    report.add("time.no_future_events", future == 0, f"{future} future-dated rows")

    unknown_regions = int((df["region"] == "Unknown").sum())
    share = unknown_regions / len(df)
    report.add(
        "enrichment.region_coverage",
        share <= 0.20,
        f"{unknown_regions}/{len(df)} unknown ({share:.1%})",
        blocking=False,
    )

    _finish(report)
    return report


def _finish(report: ValidationReport) -> None:
    log.info("data quality report:\n%s", report.summary())
    for warning in report.warnings:
        log.warning("non-blocking check failed: %s (%s)", warning.name, warning.detail)
    if report.failures:
        names = ", ".join(f.name for f in report.failures)
        raise DataQualityError(f"blocking data-quality checks failed: {names}")
