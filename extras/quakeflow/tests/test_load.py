from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest
from sqlalchemy import func, select

from quakeflow.load import ensure_schema, get_engine, upsert_dataframe
from quakeflow.transform import build_daily_stats, flatten_features, transform_events


@pytest.fixture
def engine_and_tables(settings):
    engine = get_engine(settings)
    tables = ensure_schema(engine, settings)
    return engine, tables


def _count(engine, table) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar_one()


def test_ensure_schema_is_idempotent(settings):
    engine = get_engine(settings)
    ensure_schema(engine, settings)
    tables = ensure_schema(engine, settings)
    assert set(tables) == {"events", "daily", "runs"}


def test_upsert_is_idempotent(engine_and_tables, sample_features):
    engine, tables = engine_and_tables
    events = transform_events(flatten_features(sample_features))

    first = upsert_dataframe(engine, events, tables["events"])
    second = upsert_dataframe(engine, events, tables["events"])

    assert first == second == len(events)
    assert _count(engine, tables["events"]) == len(events), "re-running must not duplicate rows"


def test_upsert_updates_changed_values(engine_and_tables, sample_features):
    engine, tables = engine_and_tables
    events = transform_events(flatten_features(sample_features))
    upsert_dataframe(engine, events, tables["events"])

    revised = events.copy()
    revised.loc[revised["event_id"] == "us7000abc1", "magnitude"] = 5.9
    upsert_dataframe(engine, revised, tables["events"])

    table = tables["events"]
    with engine.connect() as conn:
        value = conn.execute(
            select(table.c.magnitude).where(table.c.event_id == "us7000abc1")
        ).scalar_one()
    assert value == pytest.approx(5.9)
    assert _count(engine, table) == len(events)


def test_upsert_empty_frame_is_a_noop(engine_and_tables):
    engine, tables = engine_and_tables
    assert upsert_dataframe(engine, pd.DataFrame(), tables["events"]) == 0


def test_daily_stats_round_trip(engine_and_tables, sample_features):
    engine, tables = engine_and_tables
    events = transform_events(flatten_features(sample_features))
    daily = build_daily_stats(events)

    upsert_dataframe(engine, daily, tables["daily"])
    upsert_dataframe(engine, daily, tables["daily"])

    assert _count(engine, tables["daily"]) == len(daily)


def test_run_audit_lifecycle(engine_and_tables):
    from quakeflow.load import finish_run, start_run

    engine, tables = engine_and_tables
    runs = tables["runs"]
    start_run(
        engine,
        runs,
        "run-1",
        datetime(2024, 6, 1, tzinfo=timezone.utc),
        datetime(2024, 6, 2, tzinfo=timezone.utc),
    )
    finish_run(engine, runs, "run-1", status="success", rows_extracted=10, rows_loaded=8)

    with engine.connect() as conn:
        row = conn.execute(select(runs.c.status, runs.c.rows_loaded)).one()
    assert row.status == "success"
    assert row.rows_loaded == 8
