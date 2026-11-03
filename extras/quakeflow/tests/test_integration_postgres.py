"""Integration tests: these only run when a real Postgres is available.

Locally:
    make db-up
    QF_TEST_DATABASE_URL=postgresql+psycopg2://quake:quake@localhost:5433/quakeflow \
        pytest -m integration
In CI:    the `integration` job spins up a Postgres service container and sets the env var.
"""

from __future__ import annotations

import os
from dataclasses import replace

import pytest
import responses
from sqlalchemy import func, select, text
from tests.test_pipeline import WINDOW

from quakeflow.extract import build_session
from quakeflow.load import ensure_schema, get_engine
from quakeflow.pipeline import run_pipeline

PG_URL = os.getenv("QF_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not PG_URL, reason="QF_TEST_DATABASE_URL is not set"),
]


@pytest.fixture
def pg_settings(settings):
    pg = replace(settings, database_url=PG_URL, db_schema="quakeflow_test")
    engine = get_engine(pg)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS quakeflow_test CASCADE"))
    return pg


@responses.activate
def test_pipeline_against_real_postgres(pg_settings, sample_payload):
    responses.add(responses.GET, pg_settings.api_base_url, json=sample_payload, status=200)

    first = run_pipeline(settings=pg_settings, window=WINDOW, session=build_session(pg_settings))
    second = run_pipeline(settings=pg_settings, window=WINDOW, session=build_session(pg_settings))

    assert first.status == second.status == "success"

    engine = get_engine(pg_settings)
    tables = ensure_schema(engine, pg_settings)
    with engine.connect() as conn:
        events = conn.execute(select(func.count()).select_from(tables["events"])).scalar_one()
        runs = conn.execute(select(func.count()).select_from(tables["runs"])).scalar_one()
        max_mag = conn.execute(select(func.max(tables["events"].c.magnitude))).scalar_one()

    assert events == 3, "ON CONFLICT DO UPDATE must keep the table de-duplicated"
    assert runs == 2, "every run must be audited"
    assert max_mag == pytest.approx(6.8)
