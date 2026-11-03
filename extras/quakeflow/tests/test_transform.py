from __future__ import annotations

import pandas as pd
import pytest

from quakeflow.transform import (
    SILVER_COLUMNS,
    build_daily_stats,
    flatten_features,
    transform_events,
)


def test_flatten_features_produces_expected_shape(sample_features):
    raw = flatten_features(sample_features)
    assert len(raw) == 6
    assert raw.loc[0, "event_id"] == "us7000abc1"
    assert raw.loc[0, "latitude"] == pytest.approx(35.6)
    assert raw.loc[0, "depth_km"] == pytest.approx(8.2)


def test_flatten_handles_missing_geometry():
    raw = flatten_features([{"id": "x1", "properties": {"mag": 3.0, "time": 1}, "geometry": None}])
    assert raw.loc[0, "longitude"] is None
    assert raw.loc[0, "depth_km"] is None


def test_transform_filters_non_earthquakes_and_nulls(sample_features):
    events = transform_events(flatten_features(sample_features))
    ids = set(events["event_id"])
    assert "nc73mine1" not in ids, "quarry blast should be filtered out"
    assert "us7000abc4" not in ids, "row with null magnitude should be dropped"
    assert list(events.columns) == SILVER_COLUMNS


def test_transform_deduplicates_keeping_latest_update(sample_features):
    events = transform_events(flatten_features(sample_features))
    honshu = events[events["event_id"] == "us7000abc2"]
    assert len(honshu) == 1
    assert honshu.iloc[0]["magnitude"] == pytest.approx(3.4)
    assert honshu.iloc[0]["status"] == "reviewed"


def test_transform_enrichment(sample_features):
    events = transform_events(flatten_features(sample_features)).set_index("event_id")
    assert events.loc["us7000abc1", "region"] == "CA"
    assert events.loc["us7000abc5", "region"] == "Chile"
    assert events.loc["us7000abc1", "magnitude_band"] == "moderate"
    assert events.loc["us7000abc2", "magnitude_band"] == "minor"
    assert events.loc["us7000abc5", "magnitude_band"] == "strong"
    assert events.loc["us7000abc1", "depth_band"] == "shallow"
    assert events.loc["us7000abc5", "depth_band"] == "deep"
    assert events.loc["us7000abc5", "tsunami_flag"] is True or bool(
        events.loc["us7000abc5", "tsunami_flag"]
    )
    assert events.loc["us7000abc2", "felt_reports"] == 4
    assert events.loc["us7000abc2", "alert_level"] == "none"
    assert events.loc["us7000abc5", "energy_joules"] > events.loc["us7000abc1", "energy_joules"]


def test_transform_on_empty_input_returns_empty_silver_frame():
    events = transform_events(pd.DataFrame(columns=["event_id"]))
    assert events.empty
    assert list(events.columns) == SILVER_COLUMNS


def test_build_daily_stats(sample_features):
    events = transform_events(flatten_features(sample_features))
    daily = build_daily_stats(events)
    assert not daily.empty
    assert {"event_date", "region", "event_count", "max_magnitude"}.issubset(daily.columns)
    assert daily["event_count"].sum() == len(events)
    chile = daily[daily["region"] == "Chile"].iloc[0]
    assert chile["max_magnitude"] == pytest.approx(6.8)
    assert chile["tsunami_events"] == 1
