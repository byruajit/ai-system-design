# QuakeFlow — step-by-step implementation guide

This is the build order I use on camera. Every section ends with a **checkpoint** you can run,
so if something breaks you know exactly which step broke it.

Total build time from an empty folder: ~2.5 hours (video 1 covers steps 0–8).

---

## Step 0 — Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.10+ | `python --version` |
| Docker Desktop | any recent | `docker --version` |
| Git | any | `git --version` |
| VS Code | any | with the Python + Docker extensions |

No API key is needed. The USGS FDSN Event API is public domain and unauthenticated.

Open the API once in a browser so you understand the payload before writing code:

```
https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=2024-06-01&endtime=2024-06-02&minmagnitude=5
```

Note the shape: `features[]`, each with `properties` (mag, place, time, updated, tsunami, sig,
type, status, felt, alert, url) and `geometry.coordinates = [longitude, latitude, depth_km]`.
Two things to point out on camera: **time is epoch milliseconds**, and **depth is the third
coordinate**, which almost everyone misses.

---

## Step 1 — Scaffold the repository

```bash
mkdir quakeflow && cd quakeflow
git init
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate

mkdir -p src/quakeflow tests/fixtures sql docs data/bronze
mkdir -p .github/workflows databricks/resources databricks/notebooks
touch src/quakeflow/__init__.py data/bronze/.gitkeep
```

Why `src/` layout: it makes the package installable, forces the tests to import the *installed*
package instead of loose files, and stops the "works on my machine because of the CWD" class of bug.

Create `pyproject.toml`, `.gitignore`, `.env.example` (copy them from this repo), then:

```bash
pip install -e ".[dev]"
```

**Checkpoint:** `python -c "import quakeflow; print(quakeflow.__version__)"` → `0.1.0`

---

## Step 2 — Configuration (`src/quakeflow/config.py`)

Rules that keep this project sane:

1. No literal host, password, magnitude or path anywhere except `config.py`.
2. Everything reads from environment variables; `.env` is loaded for local convenience only.
3. `Settings` is a frozen dataclass, so tests can build a variant with `dataclasses.replace()`
   and nothing can mutate config mid-run.
4. `safe_database_url()` masks the password — logs get printed in CI and pasted into issues.

```bash
cp .env.example .env
```

**Checkpoint:**

```bash
python -c "from quakeflow.config import get_settings; s=get_settings(); print(s.safe_database_url(), s.min_magnitude)"
```

---

## Step 3 — Logging (`src/quakeflow/logging_utils.py`)

`print()` is fine in a script and a liability in a pipeline. One `setup_logging()` called from the
CLI, `get_logger(__name__)` everywhere else, and the module name in every line so you can tell
which layer produced it.

---

## Step 4 — Extract (`src/quakeflow/extract.py`)

Four ideas, in this order:

1. **`ExtractWindow`** — a value object for the time slice, with validation in `__post_init__`.
   A window that ends before it starts should fail immediately, not silently return zero rows.
2. **`build_session()`** — a `requests.Session` with `urllib3.Retry`: 4 attempts, exponential
   backoff, retry on 429/500/502/503/504. Plus a timeout on every call. A pipeline without a
   timeout is a pipeline that hangs at 3am.
3. **`extract_events()`** — offset pagination. Ask for `limit` rows; if you get fewer back, you
   are done; otherwise bump the offset. `max_pages` is the circuit breaker.
   Handle **HTTP 204** — USGS returns "no content" rather than an empty feature list.
4. **`save_bronze()`** — write the untouched payload to `data/bronze/dt=YYYY-MM-DD/...json`
   with lineage metadata (run id, window, source URLs). If tomorrow's transform has a bug, you
   replay from bronze instead of re-hitting the API.

**Checkpoint:**

```bash
python - <<'PY'
from quakeflow.config import get_settings
from quakeflow.extract import ExtractWindow, extract_events
s = get_settings()
raw = extract_events(ExtractWindow.last_n_days(1), s)
print(raw.count, raw.features[0]["properties"]["place"])
PY
```

---

## Step 5 — Transform (`src/quakeflow/transform.py`)

Keep every function **pure**: DataFrame in, DataFrame out, no I/O. That is what makes the test
suite fast and the Databricks notebook able to reuse the exact same code.

`flatten_features()` — nested GeoJSON to flat rows. Pad the coordinates list so a malformed
geometry cannot throw an `IndexError`.

`transform_events()` does, in order:

| Operation | Why |
|---|---|
| filter on `event_type` | the feed also carries quarry blasts, explosions, ice quakes |
| drop null id / time / magnitude | those rows cannot be keyed or ranked |
| epoch ms → UTC timestamps | `pd.to_datetime(..., unit="ms", utc=True)` |
| region parsing | `"35km SSW of Ridgecrest, CA"` → `"CA"`; short uppercase codes stay uppercase |
| magnitude band | `pd.cut` into micro / minor / light / moderate / strong / major |
| depth band | shallow < 70km, intermediate < 300km, deep beyond |
| energy in joules | Gutenberg–Richter: `log10(E) = 1.5·M + 4.8` |
| null handling | `felt`, `alert`, `sig` are frequently null in the raw feed |
| de-duplication | USGS **revises** events; sort by `updated` desc, keep the first per id |

`build_daily_stats()` — the gold layer: one row per (day, region) with count, max/avg magnitude,
avg depth, total energy and tsunami count.

**Checkpoint:** `pytest tests/test_transform.py -v` (7 tests, all green).

---

## Step 6 — Validate (`src/quakeflow/validate.py`)

The gate between "we have a DataFrame" and "we write to the warehouse". Two severities:

- **Blocking** → raises `DataQualityError`, the run fails: missing columns, null or duplicate
  keys, magnitude outside [-2, 10.5], impossible coordinates, future-dated events.
- **Warning** → logged, run continues: absurd depth, more than 20% unknown regions.

The report prints as a readable PASS/WARN/FAIL block — that block is the single most
"production" looking thing in the whole video, and it takes 60 lines of code.

**Checkpoint:** `pytest tests/test_validate.py -v`

---

## Step 7 — Model + Load (`models.py`, `load.py`)

`models.py` declares the schema in SQLAlchemy Core so the same definition runs on Postgres
(production) and SQLite (tests). Three tables:

- `quake_events` — silver, PK `event_id`
- `quake_daily_stats` — gold, PK `(event_date, region)`
- `pipeline_runs` — the audit trail: status, window, row counts, error, duration

`load.py` highlights:

- `_scalar()` converts numpy scalars, `NaN` and `NaT` into things a DB driver actually accepts.
  Skip this and you get `can't adapt type 'numpy.float64'` — the classic pandas→Postgres error.
- `upsert_dataframe()` builds `INSERT ... ON CONFLICT (pk) DO UPDATE SET ...`, chunked at 200
  rows to stay under parameter limits. **Idempotency is the whole point**: re-running the
  pipeline over the same window must never duplicate or crash.
- `latest_event_time()` is the watermark used for incremental runs.

**Checkpoint:**

```bash
docker compose up -d postgres
quakeflow init-db
pytest tests/test_load.py -v
```

---

## Step 8 — Orchestrate + CLI (`pipeline.py`, `cli.py`)

`run_pipeline()` wires the layers together and, crucially, wraps them in the audit:

```
start_run(status="running")
  extract → bronze → flatten → transform → validate → upsert silver → upsert gold
finish_run(status="success" | "failed", counts, error)
```

Window precedence: `--start/--end` → `--days` → watermark (minus 6h overlap) → `QF_LOOKBACK_DAYS`.
The overlap exists because USGS keeps revising magnitudes for hours after an event.

`cli.py` gives you `run`, `init-db` and `stats`, plus `--dry-run` (extract and transform,
never write) which is what you demo when you do not want to touch the warehouse.

**Checkpoint — the money shot:**

```bash
quakeflow run --days 3
quakeflow stats
psql postgresql://quake:quake@localhost:5433/quakeflow -f sql/analytics_queries.sql
```

Run `quakeflow run --days 3` a second time and show the row count does not move. That single
demo is worth more than any slide about idempotency.

---

## Step 9 — Tests (video 2)

```
tests/conftest.py                    fixtures: sample payload + a SQLite-backed Settings
tests/fixtures/sample_feed.json      6 handcrafted features covering every edge case
tests/test_extract.py                pagination, 204, HTTP error, bad JSON, bronze snapshot
tests/test_transform.py              filtering, de-duplication, enrichment, empty input
tests/test_validate.py               blocking vs warning expectations
tests/test_load.py                   idempotent upsert, updates, audit lifecycle
tests/test_pipeline.py               end-to-end on SQLite, rerun safety, failure auditing
tests/test_integration_postgres.py   the same flow against a real Postgres (marked)
```

The fixture is deliberately nasty: a duplicate event with a newer `updated`, a quarry blast, a
null magnitude, a null `alert`, a tsunami flag and a 320km-deep event. Six rows in, three rows out.

`responses` intercepts the HTTP layer, so the suite never touches the network.

```bash
pytest -m "not integration"          # fast lane
pytest -m integration                # needs QF_TEST_DATABASE_URL
```

---

## Step 10 — Docker (video 3)

Multi-stage `Dockerfile`: build wheels in stage one, copy `/install` into a slim runtime, run as
a non-root user, `ENTRYPOINT ["quakeflow"]` so the container behaves like the CLI.

```bash
docker compose up -d postgres
docker compose --profile etl run --rm etl run --days 1
```

Note the port mapping `5433:5432` — it keeps a locally installed Postgres from clashing.

---

## Step 11 — GitHub Actions (videos 4 and 5)

### `ci.yml` — four jobs

1. **lint** — `ruff check`, `ruff format --check`, `mypy`.
2. **unit-tests** — matrix over Python 3.10/3.11/3.12, coverage uploaded as an artifact.
3. **integration-tests** — a `postgres:16` **service container**; `QF_TEST_DATABASE_URL` points at
   it, and the integration test proves the upsert works on the real dialect.
4. **docker-build** — builds the image with buildx + GHA layer cache and smoke-tests it.

`concurrency.cancel-in-progress` stops five pushes from queuing five duplicate runs.

### `cd-release.yml`

On `main` and on `v*.*.*` tags: log in to GHCR with the built-in `GITHUB_TOKEN`, derive tags with
`docker/metadata-action` (semver, branch, short sha, `latest`), push.

```bash
git tag v0.1.0 && git push origin v0.1.0
docker pull ghcr.io/<you>/quakeflow:0.1.0
```

### `scheduled-pipeline.yml`

Daily cron plus `workflow_dispatch` with inputs (days, min magnitude, dry-run). Writes the JSON
run summary into the GitHub step summary and uploads bronze snapshots as artifacts.

Secrets → **Settings → Secrets and variables → Actions**: `QF_DATABASE_URL` pointing at a
reachable Postgres (Neon, Supabase or RDS all work; localhost obviously does not).

---

## Step 12 — Databricks (video 6)

```
databricks/
  databricks.yml                       bundle definition, dev + prod targets
  resources/quakeflow_job.yml          job: ingest task → quality-gate task, schedule, cluster
  notebooks/quakeflow_medallion.py     bronze append → silver MERGE → gold MERGE (Delta)
  notebooks/quakeflow_quality_checks.py post-load assertions that fail the job
```

The notebook imports `quakeflow.extract` / `transform` / `validate` from the wheel, so the
business logic is shared with the Postgres pipeline; only the sink differs
(`ON CONFLICT DO UPDATE` on Postgres, `MERGE INTO` on Delta).

```bash
databricks configure --host https://<workspace>.cloud.databricks.com --token
python -m build --wheel --outdir databricks/dist
cd databricks
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run quakeflow_daily -t dev
```

`databricks-deploy.yml` does the same three commands in CI: validate on every PR, deploy to dev
on `main`, deploy to prod on a version tag behind a GitHub Environment approval.

Free-tier note: Databricks Community Edition does not support Asset Bundles or Unity Catalog.
Use a trial workspace, or simply import the notebook manually and write to `hive_metastore` —
the notebook works either way with the catalog widget set to `hive_metastore`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `could not translate host name "postgres"` | running the CLI on the host, not in compose | use `localhost:5433` |
| `can't adapt type 'numpy.int64'` | passing raw numpy scalars to the driver | that is what `_scalar()` is for |
| `relation "quakeflow.quake_events" does not exist` | schema never created | `quakeflow init-db` |
| Pipeline returns 0 rows | window too narrow or magnitude too high | `--days 7 --min-magnitude 2.5` |
| HTTP 400 from USGS | window larger than the service allows | shorten the window, raise `minmagnitude` |
| Integration tests skipped | `QF_TEST_DATABASE_URL` not set | export it, or let CI run them |
| GHCR push denied | missing package permission | add `permissions: packages: write` to the job |
| `databricks bundle deploy` 403 | token lacks workspace access | regenerate a PAT with the right scope |

---

## Extension exercises for students

1. Add a `--backfill 2024-01-01:2024-06-30` mode that loops month by month.
2. Add a `dim_region` table and turn `quake_events` into a proper star schema.
3. Emit Prometheus metrics or a Slack webhook message from `finish_run()`.
4. Swap the Postgres sink for DuckDB and compare load times.
5. Replace the hand-rolled expectations with Great Expectations or `pandera`.
6. Add a dbt project on top of the silver table and let it own the gold layer.
