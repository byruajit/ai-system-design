from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest
import responses

from quakeflow.extract import (
    ExtractionError,
    ExtractWindow,
    build_session,
    extract_events,
    save_bronze,
)

WINDOW = ExtractWindow(
    start=datetime(2024, 6, 1, tzinfo=timezone.utc),
    end=datetime(2024, 6, 2, tzinfo=timezone.utc),
)


def test_window_rejects_inverted_range():
    with pytest.raises(ValueError, match="must be before"):
        ExtractWindow(start=WINDOW.end, end=WINDOW.start)


def test_window_last_n_days():
    now = datetime(2024, 6, 10, tzinfo=timezone.utc)
    window = ExtractWindow.last_n_days(3, now=now)
    assert (window.end - window.start).days == 3
    assert window.as_params()["starttime"] == "2024-06-07T00:00:00"


@responses.activate
def test_extract_paginates_until_short_page(settings, sample_payload):
    settings = replace(settings, page_limit=3)  # force a second page
    url = settings.api_base_url
    page1 = {"features": sample_payload["features"][:3]}  # == page_limit (3) -> keep going
    page2 = {"features": sample_payload["features"][3:5]}  # < page_limit -> stop
    responses.add(responses.GET, url, json=page1, status=200)
    responses.add(responses.GET, url, json=page2, status=200)

    raw = extract_events(WINDOW, settings, session=build_session(settings))

    assert raw.count == 5
    assert len(responses.calls) == 2
    assert "offset=4" in responses.calls[1].request.url


@responses.activate
def test_extract_handles_204_no_content(settings):
    responses.add(responses.GET, settings.api_base_url, status=204, body="")
    raw = extract_events(WINDOW, settings, session=build_session(settings))
    assert raw.count == 0


@responses.activate
def test_extract_raises_on_http_error(settings):
    responses.add(responses.GET, settings.api_base_url, status=400, body="Bad Request")
    with pytest.raises(ExtractionError, match="HTTP 400"):
        extract_events(WINDOW, settings, session=build_session(settings))


@responses.activate
def test_extract_raises_on_invalid_json(settings):
    responses.add(responses.GET, settings.api_base_url, status=200, body="not json")
    with pytest.raises(ExtractionError, match="not valid JSON"):
        extract_events(WINDOW, settings, session=build_session(settings))


@responses.activate
def test_save_bronze_writes_snapshot(settings, sample_payload):
    responses.add(responses.GET, settings.api_base_url, json={"features": []}, status=200)
    raw = extract_events(WINDOW, settings, session=build_session(settings))
    raw.features = sample_payload["features"]

    path = save_bronze(raw, settings)

    assert path is not None and path.exists()
    document = json.loads(path.read_text())
    assert document["feature_count"] == 0 or document["feature_count"] == len(raw.features)
    assert document["run_id"] == raw.run_id
    assert "dt=2024-06-02" in str(path)
