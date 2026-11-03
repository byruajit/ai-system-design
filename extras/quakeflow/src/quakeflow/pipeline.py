"""Orchestration: extract -> transform -> validate -> load, with an audit trail."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import Engine

from .config import Settings, get_settings
from .extract import ExtractWindow, build_session, extract_events, save_bronze
from .load import (
    ensure_schema,
    finish_run,
    get_engine,
    latest_event_time,
    start_run,
    upsert_dataframe,
)
from .logging_utils import get_logger
from .transform import build_daily_stats, flatten_features, transform_events
from .validate import validate_events

log = get_logger(__name__)

# Re-fetch a little before the watermark: the USGS revises magnitudes for hours.
WATERMARK_OVERLAP = timedelta(hours=6)


@dataclass
class PipelineResult:
    run_id: str
    window: ExtractWindow
    rows_extracted: int = 0
    rows_events_loaded: int = 0
    rows_daily_loaded: int = 0
    status: str = "success"
    duration_seconds: float = 0.0
    bronze_path: str | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "window_start": self.window.start.isoformat(),
            "window_end": self.window.end.isoformat(),
            "rows_extracted": self.rows_extracted,
            "rows_events_loaded": self.rows_events_loaded,
            "rows_daily_loaded": self.rows_daily_loaded,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 2),
        }


def resolve_window(
    settings: Settings,
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = None,
    engine: Engine | None = None,
    events_table=None,
) -> ExtractWindow:
    """Explicit dates win; then --days; then the watermark; then the default lookback."""
    now = datetime.now(timezone.utc)
    end = end or now
    if start is not None:
        return ExtractWindow(start=start, end=end)
    if days is not None:
        return ExtractWindow(start=end - timedelta(days=days), end=end)
    if engine is not None and events_table is not None:
        watermark = latest_event_time(engine, events_table)
        if watermark is not None:
            log.info("incremental run from watermark %s (minus overlap)", watermark)
            return ExtractWindow(start=watermark - WATERMARK_OVERLAP, end=end)
    return ExtractWindow(start=end - timedelta(days=settings.lookback_days), end=end)


def run_pipeline(
    settings: Settings | None = None,
    window: ExtractWindow | None = None,
    days: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    dry_run: bool = False,
    session=None,
) -> PipelineResult:
    settings = settings or get_settings()
    started = time.perf_counter()
    run_id = str(uuid.uuid4())

    engine: Engine | None = None
    tables = None
    if not dry_run:
        engine = get_engine(settings)
        tables = ensure_schema(engine, settings)

    window = window or resolve_window(
        settings,
        start=start,
        end=end,
        days=days,
        engine=engine,
        events_table=tables["events"] if tables else None,
    )
    log.info("run %s | window %s | min magnitude %s", run_id, window, settings.min_magnitude)

    result = PipelineResult(run_id=run_id, window=window)
    if engine is not None and tables is not None:
        start_run(engine, tables["runs"], run_id, window.start, window.end)

    try:
        # ---------- EXTRACT ----------
        session = session or build_session(settings)
        raw = extract_events(window, settings, session=session, run_id=run_id)
        result.rows_extracted = raw.count
        bronze_path = save_bronze(raw, settings)
        result.bronze_path = str(bronze_path) if bronze_path else None

        # ---------- TRANSFORM ----------
        raw_df = flatten_features(raw.features)
        events_df = transform_events(raw_df, event_types=settings.event_types)
        daily_df = build_daily_stats(events_df)

        # ---------- VALIDATE ----------
        report = validate_events(events_df, allow_empty=True)
        result.warnings = [f"{w.name}: {w.detail}" for w in report.warnings]

        if dry_run:
            log.info("dry run: skipping the load step")
            result.status = "dry-run"
            result.duration_seconds = time.perf_counter() - started
            return result

        # ---------- LOAD ----------
        assert engine is not None and tables is not None
        result.rows_events_loaded = upsert_dataframe(engine, events_df, tables["events"])
        result.rows_daily_loaded = upsert_dataframe(engine, daily_df, tables["daily"])
        finish_run(
            engine,
            tables["runs"],
            run_id,
            status="success",
            rows_extracted=result.rows_extracted,
            rows_loaded=result.rows_events_loaded,
            rows_aggregated=result.rows_daily_loaded,
        )
    except Exception as exc:  # noqa: BLE001 - we log, audit, then re-raise
        log.exception("pipeline run %s failed", run_id)
        if engine is not None and tables is not None:
            finish_run(
                engine,
                tables["runs"],
                run_id,
                status="failed",
                rows_extracted=result.rows_extracted,
                error_message=str(exc),
            )
        result.status = "failed"
        raise
    finally:
        result.duration_seconds = time.perf_counter() - started
        log.info("run %s finished in %.2fs", run_id, result.duration_seconds)

    return result
