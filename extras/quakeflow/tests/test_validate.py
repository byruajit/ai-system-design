from __future__ import annotations

import pandas as pd
import pytest

from quakeflow.transform import flatten_features, transform_events
from quakeflow.validate import DataQualityError, validate_events


def test_clean_frame_passes(sample_features):
    events = transform_events(flatten_features(sample_features))
    report = validate_events(events)
    assert report.ok
    assert all(check.passed or not check.blocking for check in report.checks)


def test_missing_column_raises():
    with pytest.raises(DataQualityError, match="missing columns"):
        validate_events(pd.DataFrame({"event_id": ["a"]}))


def test_empty_frame_blocks_unless_allowed(sample_features):
    empty = transform_events(pd.DataFrame(columns=["event_id"]))
    with pytest.raises(DataQualityError, match="volume.not_empty"):
        validate_events(empty)
    assert validate_events(empty, allow_empty=True).ok


def test_out_of_range_magnitude_is_blocking(sample_features):
    events = transform_events(flatten_features(sample_features))
    events.loc[0, "magnitude"] = 42.0
    with pytest.raises(DataQualityError, match="range.magnitude"):
        validate_events(events)


def test_duplicate_ids_are_blocking(sample_features):
    events = transform_events(flatten_features(sample_features))
    events = pd.concat([events, events.head(1)], ignore_index=True)
    with pytest.raises(DataQualityError, match="event_id_unique"):
        validate_events(events)


def test_bad_depth_is_only_a_warning(sample_features):
    events = transform_events(flatten_features(sample_features))
    events.loc[0, "depth_km"] = 5000.0
    report = validate_events(events)
    assert report.ok
    assert any(w.name == "range.depth_km" for w in report.warnings)
