"""Extract layer: pull raw GeoJSON earthquake events from the USGS FDSN API."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Settings
from .logging_utils import get_logger

log = get_logger(__name__)

ISO_FMT = "%Y-%m-%dT%H:%M:%S"


class ExtractionError(RuntimeError):
    """Raised when the source API cannot be read after retries."""


@dataclass(frozen=True)
class ExtractWindow:
    """The [start, end) slice of time we are asking the API for."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(f"window start {self.start} must be before end {self.end}")

    @classmethod
    def last_n_days(cls, days: int, now: datetime | None = None) -> ExtractWindow:
        end = now or datetime.now(timezone.utc)
        return cls(start=end - timedelta(days=days), end=end)

    def as_params(self) -> dict[str, str]:
        return {
            "starttime": self.start.strftime(ISO_FMT),
            "endtime": self.end.strftime(ISO_FMT),
        }

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.start:%Y-%m-%d %H:%M}Z -> {self.end:%Y-%m-%d %H:%M}Z"


@dataclass
class RawExtract:
    """Whatever came back from the API, plus the lineage metadata around it."""

    features: list[dict]
    window: ExtractWindow
    source_urls: list[str] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def count(self) -> int:
        return len(self.features)


def build_session(settings: Settings) -> requests.Session:
    """A session that retries on flaky networks and 5xx responses."""
    retry = Retry(
        total=settings.max_retries,
        backoff_factor=settings.backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=8)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "quakeflow-etl/0.1 (+https://github.com/)"})
    return session


def extract_events(
    window: ExtractWindow,
    settings: Settings,
    session: requests.Session | None = None,
    run_id: str | None = None,
) -> RawExtract:
    """Page through the API until we have every event inside the window."""
    session = session or build_session(settings)
    features: list[dict] = []
    urls: list[str] = []
    offset = 1  # USGS offsets are 1-based

    for page in range(1, settings.max_pages + 1):
        params: dict[str, str | int | float] = {
            "format": "geojson",
            "minmagnitude": settings.min_magnitude,
            "orderby": "time-asc",
            "limit": settings.page_limit,
            "offset": offset,
            **window.as_params(),
        }
        try:
            response = session.get(
                settings.api_base_url, params=params, timeout=settings.request_timeout
            )
        except requests.RequestException as exc:
            raise ExtractionError(f"request to {settings.api_base_url} failed: {exc}") from exc

        urls.append(response.url)

        if response.status_code == 204:  # USGS says "nothing matched" with an empty 204
            log.info("page %s returned 204 no-content, stopping", page)
            break
        if response.status_code >= 400:
            raise ExtractionError(
                f"API returned HTTP {response.status_code} for {response.url}: "
                f"{response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExtractionError(f"response was not valid JSON: {exc}") from exc

        batch = payload.get("features") or []
        features.extend(batch)
        log.info("page %s -> %s events (running total %s)", page, len(batch), len(features))

        if len(batch) < settings.page_limit:
            break
        offset += settings.page_limit
    else:
        log.warning("hit max_pages=%s, the window may be truncated", settings.max_pages)

    return RawExtract(
        features=features,
        window=window,
        source_urls=urls,
        run_id=run_id or str(uuid.uuid4()),
    )


def save_bronze(raw: RawExtract, settings: Settings) -> Path | None:
    """Persist the untouched payload so a bad transform never costs us the source data."""
    if not settings.write_bronze:
        return None
    partition = settings.bronze_dir / f"dt={raw.window.end:%Y-%m-%d}"
    partition.mkdir(parents=True, exist_ok=True)
    path = partition / f"quakes_{raw.fetched_at:%Y%m%dT%H%M%S}_{raw.run_id[:8]}.json"
    document = {
        "run_id": raw.run_id,
        "fetched_at": raw.fetched_at.isoformat(),
        "window_start": raw.window.start.isoformat(),
        "window_end": raw.window.end.isoformat(),
        "source_urls": raw.source_urls,
        "feature_count": raw.count,
        "features": raw.features,
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    log.info("bronze snapshot written to %s (%s events)", path, raw.count)
    return path
