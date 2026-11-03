"""Runtime configuration, loaded from environment variables / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv(override=False)

DEFAULT_API = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def _env(key: str, default: str) -> str:
    value = os.getenv(key)
    return default if value is None or value.strip() == "" else value.strip()


def _database_url() -> str:
    """Prefer a full URL, otherwise assemble one from the individual parts."""
    explicit = os.getenv("QF_DATABASE_URL")
    if explicit:
        return explicit
    user = _env("QF_DB_USER", "postgres")
    password = quote_plus(_env("QF_DB_PASSWORD", "postgres"))
    host = _env("QF_DB_HOST", "localhost")
    port = _env("QF_DB_PORT", "5432")
    name = _env("QF_DB_NAME", "quakeflow")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


@dataclass(frozen=True)
class Settings:
    """Everything the pipeline needs to know about the outside world."""

    api_base_url: str
    request_timeout: int
    max_retries: int
    backoff_factor: float
    page_limit: int
    max_pages: int
    min_magnitude: float
    lookback_days: int
    event_types: tuple[str, ...]
    database_url: str
    db_schema: str | None
    bronze_dir: Path
    write_bronze: bool
    log_level: str

    @classmethod
    def from_env(cls) -> Settings:
        schema = _env("QF_DB_SCHEMA", "quakeflow")
        return cls(
            api_base_url=_env("QF_API_BASE_URL", DEFAULT_API),
            request_timeout=int(_env("QF_REQUEST_TIMEOUT", "30")),
            max_retries=int(_env("QF_MAX_RETRIES", "4")),
            backoff_factor=float(_env("QF_BACKOFF_FACTOR", "0.8")),
            page_limit=int(_env("QF_PAGE_LIMIT", "2000")),
            max_pages=int(_env("QF_MAX_PAGES", "25")),
            min_magnitude=float(_env("QF_MIN_MAGNITUDE", "2.5")),
            lookback_days=int(_env("QF_LOOKBACK_DAYS", "7")),
            event_types=tuple(
                t.strip() for t in _env("QF_EVENT_TYPES", "earthquake").split(",") if t.strip()
            ),
            database_url=_database_url(),
            db_schema=None if schema.lower() in {"none", "null", "-"} else schema,
            bronze_dir=Path(_env("QF_BRONZE_DIR", "data/bronze")),
            write_bronze=_env("QF_WRITE_BRONZE", "true").lower() in {"1", "true", "yes"},
            log_level=_env("QF_LOG_LEVEL", "INFO").upper(),
        )

    def safe_database_url(self) -> str:
        """Database URL with the password masked, safe to print in logs."""
        url = self.database_url
        if "://" not in url or "@" not in url:
            return url
        scheme, rest = url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
