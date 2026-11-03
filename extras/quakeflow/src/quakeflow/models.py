"""Warehouse schema, defined once in SQLAlchemy Core so it works on Postgres and SQLite."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

EVENTS_TABLE = "quake_events"
DAILY_TABLE = "quake_daily_stats"
RUNS_TABLE = "pipeline_runs"


def build_metadata(schema: str | None = None) -> tuple[MetaData, dict[str, Table]]:
    metadata = MetaData(schema=schema)

    events = Table(
        EVENTS_TABLE,
        metadata,
        Column("event_id", String(64), primary_key=True),
        Column("event_time", DateTime(timezone=True), nullable=False, index=True),
        Column("event_date", Date, nullable=False, index=True),
        Column("magnitude", Float, nullable=False),
        Column("magnitude_band", String(16)),
        Column("depth_km", Float),
        Column("depth_band", String(16)),
        Column("latitude", Float),
        Column("longitude", Float),
        Column("place", Text),
        Column("region", String(120), index=True),
        Column("energy_joules", Float),
        Column("significance", Integer),
        Column("felt_reports", Integer),
        Column("alert_level", String(16)),
        Column("tsunami_flag", Boolean),
        Column("status", String(32)),
        Column("detail_url", Text),
        Column("updated_at", DateTime(timezone=True)),
        Column("ingested_at", DateTime(timezone=True), nullable=False),
    )

    daily = Table(
        DAILY_TABLE,
        metadata,
        Column("event_date", Date, primary_key=True),
        Column("region", String(120), primary_key=True),
        Column("event_count", Integer),
        Column("max_magnitude", Float),
        Column("avg_magnitude", Float),
        Column("avg_depth_km", Float),
        Column("total_energy_joules", Float),
        Column("tsunami_events", Integer),
        Column("computed_at", DateTime(timezone=True)),
    )

    runs = Table(
        RUNS_TABLE,
        metadata,
        Column("run_id", String(36), primary_key=True),
        Column("started_at", DateTime(timezone=True)),
        Column("finished_at", DateTime(timezone=True)),
        Column("status", String(16)),
        Column("window_start", DateTime(timezone=True)),
        Column("window_end", DateTime(timezone=True)),
        Column("rows_extracted", Integer),
        Column("rows_loaded", Integer),
        Column("rows_aggregated", Integer),
        Column("error_message", Text),
    )

    return metadata, {"events": events, "daily": daily, "runs": runs}
