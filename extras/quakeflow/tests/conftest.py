from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from quakeflow.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_payload() -> dict:
    return json.loads((FIXTURES / "sample_feed.json").read_text())


@pytest.fixture
def sample_features(sample_payload) -> list[dict]:
    return sample_payload["features"]


@pytest.fixture
def settings(tmp_path) -> Settings:
    base = Settings(
        api_base_url="https://example.test/fdsnws/event/1/query",
        request_timeout=5,
        max_retries=0,
        backoff_factor=0.0,
        page_limit=100,
        max_pages=5,
        min_magnitude=2.5,
        lookback_days=1,
        event_types=("earthquake",),
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        db_schema=None,
        bronze_dir=tmp_path / "bronze",
        write_bronze=True,
        log_level="WARNING",
    )
    return replace(base)
