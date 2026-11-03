"""Transform layer: GeoJSON features -> a tidy silver table + a gold aggregate."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .logging_utils import get_logger

log = get_logger(__name__)

RAW_COLUMNS = [
    "event_id",
    "magnitude",
    "place",
    "event_time_ms",
    "updated_ms",
    "tsunami_flag",
    "significance",
    "event_type",
    "status",
    "felt_reports",
    "alert_level",
    "detail_url",
    "longitude",
    "latitude",
    "depth_km",
]

SILVER_COLUMNS = [
    "event_id",
    "event_time",
    "event_date",
    "magnitude",
    "magnitude_band",
    "depth_km",
    "depth_band",
    "latitude",
    "longitude",
    "place",
    "region",
    "energy_joules",
    "significance",
    "felt_reports",
    "alert_level",
    "tsunami_flag",
    "status",
    "detail_url",
    "updated_at",
    "ingested_at",
]

MAGNITUDE_BINS = [-np.inf, 2.0, 4.0, 5.0, 6.0, 7.0, np.inf]
MAGNITUDE_LABELS = ["micro", "minor", "light", "moderate", "strong", "major"]

DEPTH_BINS = [-np.inf, 70.0, 300.0, np.inf]
DEPTH_LABELS = ["shallow", "intermediate", "deep"]

# "14km NNE of Ridgecrest, CA" -> we only want the part after the last comma
_DISTANCE_PREFIX = re.compile(r"^\s*\d+\s*km\s+[NSEW]{1,3}\s+of\s+", flags=re.IGNORECASE)


def flatten_features(features: list[dict]) -> pd.DataFrame:
    """GeoJSON is nested; the warehouse wants flat rows."""
    rows = []
    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = list(geometry.get("coordinates") or [])
        coords += [None] * (3 - len(coords))
        rows.append(
            {
                "event_id": feature.get("id"),
                "magnitude": props.get("mag"),
                "place": props.get("place"),
                "event_time_ms": props.get("time"),
                "updated_ms": props.get("updated"),
                "tsunami_flag": props.get("tsunami"),
                "significance": props.get("sig"),
                "event_type": props.get("type"),
                "status": props.get("status"),
                "felt_reports": props.get("felt"),
                "alert_level": props.get("alert"),
                "detail_url": props.get("url"),
                "longitude": coords[0],
                "latitude": coords[1],
                "depth_km": coords[2],
            }
        )
    df = pd.DataFrame(rows, columns=RAW_COLUMNS)
    log.info("flattened %s features into %s raw rows", len(features), len(df))
    return df


def _clean_region(place: object) -> str:
    if not isinstance(place, str) or not place.strip():
        return "Unknown"
    tail = place.split(",")[-1].strip()
    if not tail:
        tail = place.strip()
    tail = _DISTANCE_PREFIX.sub("", tail).strip()
    if not tail:
        return "Unknown"
    # "CA", "MX", "B.C." are codes, not words - do not title-case them.
    if len(tail) <= 4 and tail.upper() == tail:
        return tail
    return tail.title()


def transform_events(
    raw_df: pd.DataFrame,
    event_types: tuple[str, ...] = ("earthquake",),
    now: datetime | None = None,
) -> pd.DataFrame:
    """Clean, enrich and de-duplicate the raw feed. Pure function: easy to unit test."""
    ingested_at = now or datetime.now(timezone.utc)
    df = raw_df.copy()

    if df.empty:
        return pd.DataFrame(columns=SILVER_COLUMNS)

    before = len(df)
    if event_types:
        df = df[df["event_type"].isin(event_types)]
    df = df.dropna(subset=["event_id", "event_time_ms", "magnitude"])
    log.info("dropped %s unusable/non-matching rows", before - len(df))

    if df.empty:
        return pd.DataFrame(columns=SILVER_COLUMNS)

    df["event_time"] = pd.to_datetime(df["event_time_ms"], unit="ms", utc=True)
    df["updated_at"] = pd.to_datetime(df["updated_ms"], unit="ms", utc=True)
    df["event_date"] = df["event_time"].dt.date

    numeric = ["magnitude", "depth_km", "latitude", "longitude"]
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")

    df["region"] = df["place"].map(_clean_region)
    df["magnitude_band"] = pd.cut(
        df["magnitude"], bins=MAGNITUDE_BINS, labels=MAGNITUDE_LABELS, right=False
    ).astype(object)
    df["depth_band"] = pd.cut(
        df["depth_km"], bins=DEPTH_BINS, labels=DEPTH_LABELS, right=False
    ).astype(object)

    # Gutenberg-Richter: log10(E) = 1.5 * M + 4.8  (energy in joules)
    df["energy_joules"] = np.power(10.0, 1.5 * df["magnitude"] + 4.8)

    df["tsunami_flag"] = df["tsunami_flag"].fillna(0).astype(int).astype(bool)
    df["felt_reports"] = pd.to_numeric(df["felt_reports"], errors="coerce").fillna(0).astype(int)
    df["significance"] = pd.to_numeric(df["significance"], errors="coerce").fillna(0).astype(int)
    df["alert_level"] = df["alert_level"].fillna("none").astype(str)
    df["status"] = df["status"].fillna("unknown").astype(str)
    df["ingested_at"] = ingested_at

    # The USGS revises events, so the newest "updated" row wins.
    df = df.sort_values("updated_at", ascending=False).drop_duplicates("event_id", keep="first")
    duplicates = len(df) - df["event_id"].nunique()
    if duplicates:  # pragma: no cover - defensive
        log.warning("%s duplicate event_ids survived de-duplication", duplicates)

    df = df.sort_values("event_time").reset_index(drop=True)
    result = df[SILVER_COLUMNS]
    log.info("silver table ready: %s rows, %s columns", len(result), len(result.columns))
    return result


def build_daily_stats(events_df: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    """Gold layer: one row per (day, region) - the table a dashboard would query."""
    computed_at = now or datetime.now(timezone.utc)
    columns = [
        "event_date",
        "region",
        "event_count",
        "max_magnitude",
        "avg_magnitude",
        "avg_depth_km",
        "total_energy_joules",
        "tsunami_events",
        "computed_at",
    ]
    if events_df.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        events_df.groupby(["event_date", "region"], dropna=False)
        .agg(
            event_count=("event_id", "count"),
            max_magnitude=("magnitude", "max"),
            avg_magnitude=("magnitude", "mean"),
            avg_depth_km=("depth_km", "mean"),
            total_energy_joules=("energy_joules", "sum"),
            tsunami_events=("tsunami_flag", "sum"),
        )
        .reset_index()
    )
    grouped["avg_magnitude"] = grouped["avg_magnitude"].round(2)
    grouped["avg_depth_km"] = grouped["avg_depth_km"].round(2)
    grouped["tsunami_events"] = grouped["tsunami_events"].astype(int)
    grouped["computed_at"] = computed_at
    grouped = grouped.sort_values(["event_date", "event_count"], ascending=[True, False])
    log.info("gold table ready: %s day/region rows", len(grouped))
    return grouped[columns].reset_index(drop=True)
