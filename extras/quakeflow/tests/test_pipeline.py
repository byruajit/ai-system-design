from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import responses
from sqlalchemy import func, select

from quakeflow.extract import ExtractionError, ExtractWindow, build_session
from quakeflow.load import ensure_schema, get_engine
from quakeflow.pipeline import resolve_window, run_pipeline

WINDOW = ExtractWindow(
    start=datetime(2024, 6, 1, tzinfo=timezone.utc),
    end=datetime(2024, 6, 3, tzinfo=timezone.utc),
)


@responses.activate
def test_end_to_end_pipeline_writes_all_layers(settings, sample_payload):
    responses.add(responses.GET, settings.api_base_url, json=sample_payload, status=200)

    result = run_pipeline(settings=settings, window=WINDOW, session=build_session(settings))

    assert result.status == "success"
    assert result.rows_extracted == 6
    assert result.rows_events_loaded == 3  # blast + null-magnitude + duplicate removed
    assert result.rows_daily_loaded >= 1
    assert result.bronze_path is not None

    engine = get_engine(settings)
    tables = ensure_schema(engine, settings)
    with engine.connect() as conn:
        events = conn.execute(select(func.count()).select_from(tables["events"])).scalar_one()
        runs = conn.execute(select(tables["runs"].c.status)).scalars().all()
    assert events == 3
    assert runs == ["success"]


@responses.activate
def test_pipeline_is_rerunnable_without_duplicating(settings, sample_payload):
    responses.add(responses.GET, settings.api_base_url, json=sample_payload, status=200)
    run_pipeline(settings=settings, window=WINDOW, session=build_session(settings))
    run_pipeline(settings=settings, window=WINDOW, session=build_session(settings))

    engine = get_engine(settings)
    tables = ensure_schema(engine, settings)
    with engine.connect() as conn:
        events = conn.execute(select(func.count()).select_from(tables["events"])).scalar_one()
    assert events == 3


@responses.activate
def test_dry_run_never_touches_the_warehouse(settings, sample_payload):
    responses.add(responses.GET, settings.api_base_url, json=sample_payload, status=200)
    result = run_pipeline(
        settings=settings, window=WINDOW, dry_run=True, session=build_session(settings)
    )
    assert result.status == "dry-run"
    assert result.rows_events_loaded == 0


@responses.activate
def test_failure_is_recorded_in_the_audit_table(settings):
    responses.add(responses.GET, settings.api_base_url, status=500, body="boom")

    with pytest.raises(ExtractionError):
        run_pipeline(settings=settings, window=WINDOW, session=build_session(settings))

    engine = get_engine(settings)
    tables = ensure_schema(engine, settings)
    with engine.connect() as conn:
        row = conn.execute(select(tables["runs"].c.status, tables["runs"].c.error_message)).one()
    assert row.status == "failed"
    assert row.error_message


def test_resolve_window_precedence(settings):
    explicit = resolve_window(settings, start=WINDOW.start, end=WINDOW.end)
    assert explicit.start == WINDOW.start

    by_days = resolve_window(settings, days=2, end=WINDOW.end)
    assert by_days.start == WINDOW.end - timedelta(days=2)

    default = resolve_window(settings, end=WINDOW.end)
    assert default.start == WINDOW.end - timedelta(days=settings.lookback_days)


@responses.activate
def test_watermark_drives_the_next_incremental_window(settings, sample_payload):
    responses.add(responses.GET, settings.api_base_url, json=sample_payload, status=200)
    run_pipeline(settings=settings, window=WINDOW, session=build_session(settings))

    engine = get_engine(settings)
    tables = ensure_schema(engine, settings)
    window = resolve_window(settings, engine=engine, events_table=tables["events"])

    assert window.start < datetime(2024, 6, 2, tzinfo=timezone.utc)
    assert window.start > datetime(2024, 5, 31, tzinfo=timezone.utc)
