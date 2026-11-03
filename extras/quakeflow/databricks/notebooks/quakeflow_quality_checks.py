# Databricks notebook source
# MAGIC %md
# MAGIC # QuakeFlow - post-load quality gate
# MAGIC Fails the job if the warehouse tables violate our expectations.

# COMMAND ----------

# Serverless compute requires the Spark session to be initialized by an actual
# call (a bare `spark` reference is not enough — it never touches the session)
# in its own first executed command, before anything else (dbutils calls
# included) — otherwise later `spark` usage trips an uninitialized-session error.
spark.sql("SELECT 1")

# COMMAND ----------

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("target_schema", "quakeflow_dev")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("target_schema")
table = f"{catalog}.{schema}.quake_events"

# COMMAND ----------

checks = {
    "silver table is not empty": f"SELECT COUNT(*) FROM {table}",
    "no duplicate event ids": f"""
        SELECT COUNT(*) FROM (
            SELECT event_id FROM {table} GROUP BY event_id HAVING COUNT(*) > 1
        )
    """,
    "no impossible magnitudes": f"SELECT COUNT(*) FROM {table} WHERE magnitude < -2 OR magnitude > 10.5",
    "no future events": f"SELECT COUNT(*) FROM {table} WHERE event_time > current_timestamp() + INTERVAL 2 HOURS",
    "no null keys": f"SELECT COUNT(*) FROM {table} WHERE event_id IS NULL OR event_time IS NULL",
}

expectations = {
    "silver table is not empty": lambda n: n > 0,
    "no duplicate event ids": lambda n: n == 0,
    "no impossible magnitudes": lambda n: n == 0,
    "no future events": lambda n: n == 0,
    "no null keys": lambda n: n == 0,
}

failures = []
for name, query in checks.items():
    value = spark.sql(query).collect()[0][0]
    passed = expectations[name](value)
    print(f"[{'PASS' if passed else 'FAIL'}] {name} -> {value}")
    if not passed:
        failures.append(f"{name} (got {value})")

if failures:
    raise AssertionError("Data quality gate failed: " + "; ".join(failures))

dbutils.notebook.exit("all quality checks passed")
