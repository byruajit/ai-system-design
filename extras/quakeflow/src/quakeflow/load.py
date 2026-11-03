"""Load layer: idempotent upserts into the warehouse + a run-audit table."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, Table, create_engine, func, select, text

from .config import Settings
from .logging_utils import get_logger
from .models import build_metadata

log = get_logger(__name__)

CHUNK_SIZE = 200


class LoadError(RuntimeError):
    """Raised when the warehouse rejects our data."""


def get_engine(settings: Settings) -> Engine:
    engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    log.info("engine created for %s", settings.safe_database_url())
    return engine


def ensure_schema(engine: Engine, settings: Settings) -> dict[str, Table]:
    """Create the schema and all tables if they are not there yet."""
    metadata, tables = build_metadata(settings.db_schema)
    if settings.db_schema and engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"'))
    metadata.create_all(engine)
    log.info("schema ready (%s tables)", len(tables))
    return tables


def _scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: _scalar(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def _chunks(rows: Sequence[dict], size: int) -> Iterable[Sequence[dict]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _dialect_insert(dialect: str, table: Table) -> Any:
    """Postgres and SQLite both speak ON CONFLICT, but through different constructs."""
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        return pg_insert(table)
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        return sqlite_insert(table)
    raise LoadError(f"upsert is not implemented for dialect '{dialect}'")


def upsert_dataframe(
    engine: Engine,
    df: pd.DataFrame,
    table: Table,
    update_columns: Sequence[str] | None = None,
) -> int:
    """INSERT ... ON CONFLICT DO UPDATE, so re-running the pipeline is always safe."""
    if df.empty:
        log.info("nothing to upsert into %s", table.name)
        return 0

    key_columns = [c.name for c in table.primary_key.columns]
    if update_columns is None:
        update_columns = [c.name for c in table.columns if c.name not in key_columns]

    dialect = engine.dialect.name
    rows = _records(df[[c.name for c in table.columns if c.name in df.columns]])
    written = 0
    try:
        with engine.begin() as conn:
            for chunk in _chunks(rows, CHUNK_SIZE):
                stmt = _dialect_insert(dialect, table).values(list(chunk))
                stmt = stmt.on_conflict_do_update(
                    index_elements=key_columns,
                    set_={col: getattr(stmt.excluded, col) for col in update_columns},
                )
                conn.execute(stmt)
                written += len(chunk)
    except Exception as exc:  # noqa: BLE001 - we re-raise with context
        raise LoadError(f"upsert into {table.name} failed: {exc}") from exc

    log.info("upserted %s rows into %s", written, table.name)
    return written


def latest_event_time(engine: Engine, table: Table) -> datetime | None:
    """Watermark for incremental runs."""
    try:
        with engine.connect() as conn:
            value = conn.execute(select(func.max(table.c.event_time))).scalar()
    except Exception as exc:  # noqa: BLE001 - table may simply not exist yet
        log.warning("could not read watermark: %s", exc)
        return None
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def start_run(engine: Engine, table: Table, run_id: str, window_start, window_end) -> None:
    upsert_dataframe(
        engine,
        pd.DataFrame(
            [
                {
                    "run_id": run_id,
                    "started_at": datetime.now(timezone.utc),
                    "finished_at": None,
                    "status": "running",
                    "window_start": window_start,
                    "window_end": window_end,
                    "rows_extracted": 0,
                    "rows_loaded": 0,
                    "rows_aggregated": 0,
                    "error_message": None,
                }
            ]
        ),
        table,
    )


def finish_run(
    engine: Engine,
    table: Table,
    run_id: str,
    status: str,
    rows_extracted: int = 0,
    rows_loaded: int = 0,
    rows_aggregated: int = 0,
    error_message: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            table.update()
            .where(table.c.run_id == run_id)
            .values(
                finished_at=datetime.now(timezone.utc),
                status=status,
                rows_extracted=rows_extracted,
                rows_loaded=rows_loaded,
                rows_aggregated=rows_aggregated,
                error_message=(error_message or "")[:2000] or None,
            )
        )
    log.info("run %s finished with status=%s", run_id, status)
