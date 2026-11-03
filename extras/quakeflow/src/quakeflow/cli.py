"""Command line entry point: `quakeflow run`, `quakeflow init-db`, `quakeflow stats`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from sqlalchemy import desc, select

from .config import get_settings
from .load import ensure_schema, get_engine
from .logging_utils import get_logger, setup_logging
from .pipeline import run_pipeline

log = get_logger(__name__)


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quakeflow", description="Earthquake ETL pipeline")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING, ERROR")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the full ETL pipeline")
    run.add_argument("--days", type=int, default=None, help="look back N days from now")
    run.add_argument("--start", type=_parse_dt, default=None, help="ISO start timestamp (UTC)")
    run.add_argument("--end", type=_parse_dt, default=None, help="ISO end timestamp (UTC)")
    run.add_argument("--min-magnitude", type=float, default=None)
    run.add_argument("--dry-run", action="store_true", help="extract + transform, never load")
    run.add_argument("--no-bronze", action="store_true", help="skip the raw JSON snapshot")

    sub.add_parser("init-db", help="create the schema and tables, then exit")
    stats = sub.add_parser("stats", help="print the busiest regions currently in the warehouse")
    stats.add_argument("--limit", type=int, default=10)

    return parser


def _apply_overrides(settings, args):
    from dataclasses import replace

    changes = {}
    if getattr(args, "min_magnitude", None) is not None:
        changes["min_magnitude"] = args.min_magnitude
    if getattr(args, "no_bronze", False):
        changes["write_bronze"] = False
    if args.log_level:
        changes["log_level"] = args.log_level.upper()
    return replace(settings, **changes) if changes else settings


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = _apply_overrides(get_settings(), args)
    setup_logging(settings.log_level)

    if args.command == "init-db":
        engine = get_engine(settings)
        ensure_schema(engine, settings)
        print("Schema and tables are ready.")
        return 0

    if args.command == "stats":
        engine = get_engine(settings)
        tables = ensure_schema(engine, settings)
        daily = tables["daily"]
        query = (
            select(daily.c.event_date, daily.c.region, daily.c.event_count, daily.c.max_magnitude)
            .order_by(desc(daily.c.event_date), desc(daily.c.event_count))
            .limit(args.limit)
        )
        with engine.connect() as conn:
            rows = conn.execute(query).all()
        if not rows:
            print("No data yet - run `quakeflow run --days 3` first.")
            return 0
        print(f"{'date':<12}{'region':<32}{'events':>8}{'max mag':>10}")
        print("-" * 62)
        for event_date, region, count, max_mag in rows:
            print(f"{str(event_date):<12}{str(region)[:31]:<32}{count:>8}{max_mag:>10.2f}")
        return 0

    try:
        result = run_pipeline(
            settings=settings,
            days=args.days,
            start=args.start,
            end=args.end,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        log.error("pipeline failed: %s", exc)
        return 1

    print(json.dumps(result.as_dict(), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
