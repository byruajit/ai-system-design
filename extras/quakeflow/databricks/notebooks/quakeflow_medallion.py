# Databricks notebook source
# MAGIC %md
# MAGIC # QuakeFlow - medallion refresh
# MAGIC
# MAGIC Same `quakeflow` package as the local Postgres pipeline; only the sink changes.
# MAGIC
# MAGIC | layer | table | content |
# MAGIC |---|---|---|
# MAGIC | bronze | `quake_events_bronze` | raw flattened API rows + ingest metadata |
# MAGIC | silver | `quake_events` | cleaned, typed, de-duplicated events |
# MAGIC | gold | `quake_daily_stats` | one row per day + region |

# COMMAND ----------

# Serverless compute requires the Spark session to be initialized by an actual
# call (a bare `spark` reference is not enough — it never touches the session)
# in its own first executed command, before anything else (dbutils calls
# included) — otherwise later `spark` usage trips an uninitialized-session error.
spark.sql("SELECT 1")

# COMMAND ----------

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("target_schema", "quakeflow_dev")
dbutils.widgets.text("lookback_days", "1")
dbutils.widgets.text("min_magnitude", "2.5")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("target_schema")
lookback_days = int(dbutils.widgets.get("lookback_days"))
min_magnitude = float(dbutils.widgets.get("min_magnitude"))

spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"USE {catalog}.{schema}")
print(f"Writing to {catalog}.{schema}")

# COMMAND ----------

from dataclasses import replace

from quakeflow.config import Settings
from quakeflow.extract import ExtractWindow, extract_events
from quakeflow.transform import build_daily_stats, flatten_features, transform_events
from quakeflow.validate import validate_events

settings = replace(
    Settings.from_env(),
    min_magnitude=min_magnitude,
    write_bronze=False,          # Delta is our bronze layer here, not the local filesystem
)
window = ExtractWindow.last_n_days(lookback_days)
raw = extract_events(window, settings)
print(f"Extracted {raw.count} events for {window}")

# COMMAND ----------

# MAGIC %md ## Bronze - land the raw rows exactly as they arrived

# COMMAND ----------

import pyspark.sql.functions as F

raw_pdf = flatten_features(raw.features)

if raw_pdf.empty:
    dbutils.notebook.exit("no events in window")

bronze_sdf = (
    spark.createDataFrame(raw_pdf.astype(object).where(raw_pdf.notna(), None))
    .withColumn("_ingested_at", F.current_timestamp())
    .withColumn("_run_id", F.lit(raw.run_id))
    .withColumn("_window_start", F.lit(window.start.isoformat()))
    .withColumn("_window_end", F.lit(window.end.isoformat()))
)

(
    bronze_sdf.write.format("delta")
    .mode("append")
    .option("mergeSchema", "true")
    .saveAsTable(f"{catalog}.{schema}.quake_events_bronze")
)
print(f"bronze += {bronze_sdf.count()} rows")

# COMMAND ----------

# MAGIC %md ## Silver - clean, enrich, validate, then MERGE (idempotent)

# COMMAND ----------

silver_pdf = transform_events(raw_pdf, event_types=settings.event_types)
report = validate_events(silver_pdf, allow_empty=True)
print(report.summary())

silver_sdf = spark.createDataFrame(silver_pdf)
silver_sdf.createOrReplaceTempView("silver_updates")

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {catalog}.{schema}.quake_events (
        event_id STRING, event_time TIMESTAMP, event_date DATE, magnitude DOUBLE,
        magnitude_band STRING, depth_km DOUBLE, depth_band STRING, latitude DOUBLE,
        longitude DOUBLE, place STRING, region STRING, energy_joules DOUBLE,
        significance INT, felt_reports INT, alert_level STRING, tsunami_flag BOOLEAN,
        status STRING, detail_url STRING, updated_at TIMESTAMP, ingested_at TIMESTAMP
    ) USING DELTA
    PARTITIONED BY (event_date)
    """
)

spark.sql(
    f"""
    MERGE INTO {catalog}.{schema}.quake_events AS target
    USING silver_updates AS source
    ON target.event_id = source.event_id
    WHEN MATCHED AND source.updated_at > target.updated_at THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
    """
)
print("silver merged")

# COMMAND ----------

# MAGIC %md ## Gold - the aggregate a dashboard queries

# COMMAND ----------

gold_pdf = build_daily_stats(silver_pdf)
gold_sdf = spark.createDataFrame(gold_pdf)
gold_sdf.createOrReplaceTempView("gold_updates")

spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {catalog}.{schema}.quake_daily_stats (
        event_date DATE, region STRING, event_count BIGINT, max_magnitude DOUBLE,
        avg_magnitude DOUBLE, avg_depth_km DOUBLE, total_energy_joules DOUBLE,
        tsunami_events BIGINT, computed_at TIMESTAMP
    ) USING DELTA
    """
)

spark.sql(
    f"""
    MERGE INTO {catalog}.{schema}.quake_daily_stats AS target
    USING gold_updates AS source
    ON target.event_date = source.event_date AND target.region = source.region
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
    """
)

display(
    spark.sql(
        f"SELECT * FROM {catalog}.{schema}.quake_daily_stats ORDER BY event_date DESC, event_count DESC LIMIT 20"
    )
)

# COMMAND ----------

dbutils.notebook.exit(
    f"ok: extracted={raw.count} silver={len(silver_pdf)} gold={len(gold_pdf)}"
)
