# QuakeFlow — an ETL pipeline that behaves like production

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **Extra mini-project in the [AI System Design series](../../README.md).** The episodes design
> AI systems for Northwind Bank; every one of them sits on top of a data pipeline that has to be
> retry-safe, fresh and observable. QuakeFlow is that layer, built for real on open public data,
> so you can run the patterns the episodes whiteboard. It is self-contained: its own
> `pyproject.toml`, tests and Docker setup, separate from the root `requirements.txt`.

| QuakeFlow pattern | Where the series uses it |
|---|---|
| `ON CONFLICT DO UPDATE` upserts keyed by a stable ID, so re-runs never duplicate | [Ep 3](../../ep03-permission-aware-rag/) idempotent re-ingest · [Ep 5](../../ep05-loan-doc-processing/) idempotency keys |
| Watermark + 6-hour overlap so late revisions are picked up | [Ep 3](../../ep03-permission-aware-rag/) freshness and the nightly reconciliation job |
| Blocking vs warning checks in `validate.py`, run before the load | [Ep 5](../../ep05-loan-doc-processing/) validation before write · [Ep 10](../../ep10-evals-observability/) gate that fails the build |
| Retry with exponential backoff and a timeout on every call | [Ep 9](../../ep09-reliability/) surviving a flaky dependency |
| `pipeline_runs` audit table: did it run, did it work, how much moved | [Ep 10](../../ep10-evals-observability/) observability · [Ep 11](../../ep11-security-governance/) audit trail |
| Raw bronze snapshot before any transform | Replay and reprocessing after a pipeline change ([Ep 5](../../ep05-loan-doc-processing/), follow-up 4) |

QuakeFlow pulls global earthquake events from the **USGS FDSN Event API**, cleans and enriches
them with pandas, runs a data-quality gate, and upserts them into **PostgreSQL** — then the same
package is deployed to **Databricks** as a bronze/silver/gold Delta job, and the whole thing is
tested, built and scheduled by **GitHub Actions**.

No API key. No sign-up. The source is open and free.

```
USGS API ──▶ extract ──▶ bronze JSON snapshot
                │
                ▼
           transform (pandas)  ──▶ validate (quality gate)
                                        │
                            ┌───────────┴───────────┐
                            ▼                       ▼
                   Postgres upsert            Databricks Delta
                 (silver + gold + audit)      (bronze/silver/gold)
```

## What makes this more than a toy

| Concern | How it is handled |
|---|---|
| Flaky networks | `urllib3` retry policy with exponential backoff, timeouts on every call |
| Large windows | Offset pagination with a hard page cap |
| Re-runs | `INSERT ... ON CONFLICT DO UPDATE` — running twice never duplicates a row |
| Late-arriving revisions | Watermark window with a 6-hour overlap; newest `updated` wins |
| Bad data | Blocking + non-blocking expectations in `validate.py`, run before the load |
| Observability | Every run is audited in `pipeline_runs` (status, counts, error, duration) |
| Recovery | Raw payloads are snapshotted to `data/bronze/` before anything is transformed |
| Config | 100% environment-driven, `.env` for local, GitHub secrets for CI |
| Confidence | 30+ unit tests plus an integration test against a real Postgres service container |

## Quick start (5 minutes)

```bash
cd extras/quakeflow                                    # from the root of the ai-system-design repo
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env

docker compose up -d postgres                          # Postgres on localhost:5433
quakeflow init-db                                      # create schema + tables
quakeflow run --days 3                                 # extract -> transform -> validate -> load
quakeflow stats                                        # peek at the gold table
```

Browse the data at <http://localhost:8080> (Adminer, server `postgres`, user/password `quake`),
or paste the queries in [`sql/analytics_queries.sql`](sql/analytics_queries.sql).

**No Docker?** Point it at SQLite instead. SQLite has no schemas, so switch the schema off:

```bash
export QF_DATABASE_URL=sqlite:///quake.db QF_DB_SCHEMA=none
quakeflow init-db && quakeflow run --days 2 && quakeflow stats
quakeflow run --days 2            # run it again: same row count, nothing duplicated
```

## CLI

```bash
quakeflow run                     # incremental: continues from the watermark
quakeflow run --days 7            # rolling 7-day window
quakeflow run --start 2024-06-01 --end 2024-06-08 --min-magnitude 4.5
quakeflow run --days 1 --dry-run  # extract + transform + validate, never writes
quakeflow init-db                 # DDL only
quakeflow stats --limit 20        # busiest day/region rows
```

## Layout

```
src/quakeflow/
  config.py        typed settings loaded from env / .env
  extract.py       retrying HTTP session, pagination, bronze snapshots
  transform.py     flatten -> clean -> enrich -> de-duplicate -> aggregate
  validate.py      data-quality expectations (blocking and warning)
  models.py        SQLAlchemy Core schema (Postgres + SQLite)
  load.py          dialect-aware upserts, watermark, run audit
  pipeline.py      orchestration and error handling
  cli.py           argparse entry point
tests/             unit tests (SQLite) + integration test (real Postgres)
.github/workflows/ ci, cd-release, scheduled-pipeline, databricks-deploy
databricks/        asset bundle, job definition, medallion + quality notebooks
sql/               analytics queries for the demo
```

## Tests

```bash
pytest -m "not integration"      # fast, SQLite only
make db-up
QF_TEST_DATABASE_URL=postgresql+psycopg2://quake:quake@localhost:5433/quakeflow pytest -m integration
```

## CI/CD

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | push / PR | ruff, ruff-format, mypy, pytest on 3.10–3.12, Postgres integration tests, Docker build |
| `cd-release.yml` | push to `main`, `v*` tags | builds and pushes the image to GHCR with semver tags |
| `scheduled-pipeline.yml` | manual (`workflow_dispatch`) | runs the pipeline against Postgres, publishes a run summary; the daily schedule lives in the Databricks job |
| `databricks-deploy.yml` | PR / main / tags | validates the asset bundle, deploys to dev, promotes to prod on a tag |

> **Inside this repo these workflows are reference copies.** GitHub Actions only runs workflows
> from the repository root's `.github/workflows/`, so nothing here triggers (no image pushes, no
> Databricks deploys). To use them, copy `extras/quakeflow/` into its own repository.

Secrets to add under **Settings → Secrets and variables → Actions**:
`QF_DATABASE_URL`, `DATABRICKS_HOST`, `DATABRICKS_TOKEN`.

## Databricks

```bash
cd databricks
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run quakeflow_daily -t dev
```

The notebook imports the exact same `quakeflow` functions, so the transform logic is identical
in both worlds — only the sink changes (Postgres upsert vs Delta `MERGE`).

## Docs

- [`docs/step-by-step.md`](docs/step-by-step.md) — build the project from an empty folder
- [`docs/series-roadmap.md`](docs/series-roadmap.md) — how the rest of the series is laid out

## Data source

USGS Earthquake Hazards Program, FDSN Event Web Service — public domain.
<https://earthquake.usgs.gov/fdsnws/event/1/>

## License

MIT — see [LICENSE](LICENSE).
