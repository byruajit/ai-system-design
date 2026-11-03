# QuakeFlow — course series roadmap

One project, six videos, each one shippable on its own. Every video ends with something that
runs, and starts by re-running what the last one built.

| # | Title | Runtime | You finish with |
|---|---|---|---|
| 1 | Build a Real ETL Pipeline in Python (USGS → PostgreSQL) | 45–55 min | Working idempotent pipeline + CLI |
| 2 | Testing Data Pipelines: pytest, mocked APIs, in-memory DBs | 35–40 min | 30+ tests, coverage, a nasty fixture |
| 3 | Containerising the Pipeline: Docker & Compose | 25–30 min | Multi-stage image, one-command stack |
| 4 | CI with GitHub Actions: lint, types, tests, Postgres services | 35–40 min | Green badge on every PR |
| 5 | CD & Scheduling: GHCR releases and a pipeline that runs itself | 30–35 min | Daily cron run + versioned images |
| 6 | Lakehouse: the same code on Databricks with Delta & Asset Bundles | 40–45 min | Bronze/silver/gold job deployed from CI |

---

## Video 1 — Build a Real ETL Pipeline
**Files:** `pyproject.toml`, `config.py`, `logging_utils.py`, `extract.py`, `transform.py`,
`validate.py`, `models.py`, `load.py`, `pipeline.py`, `cli.py`, `docker-compose.yml` (Postgres only)
**Teaching beats:** epoch-ms timestamps, lon/lat/depth ordering, HTTP 204, retry policy,
bronze snapshots, pure transform functions, blocking vs warning checks, `ON CONFLICT DO UPDATE`,
watermark + overlap, run auditing.
**Homework:** add a `--min-significance` filter and a `felt_reports` band.

## Video 2 — Testing Data Pipelines
**Files:** `tests/*`, `tests/fixtures/sample_feed.json`
**Beats:** why pure functions are testable; `responses` for HTTP; SQLite as a stand-in warehouse;
building a fixture that encodes every edge case (duplicate revision, quarry blast, null magnitude,
null alert, deep event, tsunami); testing idempotency by asserting a count doesn't move; markers
for integration tests; coverage as a conversation, not a target.
**Homework:** write a failing test for a bug you introduce in `_clean_region`.

## Video 3 — Containerising the Pipeline
**Files:** `Dockerfile`, full `docker-compose.yml`, `Makefile`
**Beats:** multi-stage builds and why the runtime image shouldn't contain pytest; non-root users;
`ENTRYPOINT` vs `CMD`; compose profiles; healthchecks and `depends_on: condition: service_healthy`;
host port 5433 to avoid collisions; volumes for bronze data.
**Homework:** shrink the image, measure before and after.

## Video 4 — CI with GitHub Actions
**Files:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`
**Beats:** jobs vs steps; caching pip; a matrix over Python versions; ruff and mypy as gates;
**service containers** — running the integration suite against a real Postgres inside CI;
`concurrency` to cancel superseded runs; artifacts; branch protection so the badge means something.
**Homework:** make CI fail on purpose, then read the annotation and fix it.

## Video 5 — CD & Scheduling
**Files:** `.github/workflows/cd-release.yml`, `.github/workflows/scheduled-pipeline.yml`
**Beats:** GHCR and the built-in `GITHUB_TOKEN`; `docker/metadata-action` for semver + sha tags;
buildx layer caching; cron syntax and why UTC bites you; `workflow_dispatch` inputs;
secrets vs variables; step summaries; a free hosted Postgres so the schedule has somewhere to write.
**Homework:** tag `v0.2.0` and pull your own image.

## Video 6 — Lakehouse on Databricks
**Files:** `databricks/databricks.yml`, `databricks/resources/quakeflow_job.yml`,
`databricks/notebooks/*`, `.github/workflows/databricks-deploy.yml`
**Beats:** medallion architecture as an actual folder of code; `MERGE INTO` as the Delta
equivalent of `ON CONFLICT`; packaging the project as a wheel and installing it on the cluster so
the transform logic is shared, not copy-pasted; Asset Bundles with dev and prod targets; a
quality-gate task that fails the job; deploying from CI with an approval gate on prod.
**Homework:** add a `quake_monthly_stats` gold table and a task that builds it.

---

## Series-level promises (repeat these on camera)

1. Every layer is testable in isolation because nothing does I/O and computation in the same function.
2. Every write is idempotent, so every run is safe to retry.
3. Every run is observable — you can answer "did it run, did it work, how much moved" in SQL.
4. The same transform code runs on your laptop, in CI, and on a Spark cluster.
