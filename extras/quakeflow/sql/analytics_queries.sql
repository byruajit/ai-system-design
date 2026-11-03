-- Handy queries for the demo at the end of the video.
-- Run them in Adminer (http://localhost:8080) or psql.

-- 1. Did the pipeline actually run, and how did it go?
SELECT run_id, status, window_start, window_end, rows_extracted, rows_loaded, rows_aggregated,
       ROUND(EXTRACT(EPOCH FROM (finished_at - started_at))::numeric, 2) AS seconds
FROM quakeflow.pipeline_runs
ORDER BY started_at DESC
LIMIT 10;

-- 2. How much data landed in each layer?
SELECT 'silver: quake_events' AS table_name, COUNT(*) AS rows FROM quakeflow.quake_events
UNION ALL
SELECT 'gold: quake_daily_stats', COUNT(*) FROM quakeflow.quake_daily_stats;

-- 3. The ten strongest events we know about.
SELECT event_time, region, magnitude, magnitude_band, depth_km, depth_band, place
FROM quakeflow.quake_events
ORDER BY magnitude DESC
LIMIT 10;

-- 4. Where is the ground moving most? (gold table, the one a dashboard would hit)
SELECT region,
       SUM(event_count)                       AS events,
       MAX(max_magnitude)                     AS strongest,
       ROUND(AVG(avg_magnitude)::numeric, 2)  AS mean_magnitude
FROM quakeflow.quake_daily_stats
GROUP BY region
ORDER BY events DESC
LIMIT 15;

-- 5. Daily activity curve.
SELECT event_date, SUM(event_count) AS events, MAX(max_magnitude) AS strongest
FROM quakeflow.quake_daily_stats
GROUP BY event_date
ORDER BY event_date;

-- 6. Magnitude distribution, the classic Gutenberg-Richter shape.
SELECT magnitude_band, COUNT(*) AS events,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM quakeflow.quake_events
GROUP BY magnitude_band
ORDER BY events DESC;

-- 7. Deep events only - these are the subduction-zone ones.
SELECT region, COUNT(*) AS deep_events, ROUND(AVG(depth_km)::numeric, 1) AS avg_depth_km
FROM quakeflow.quake_events
WHERE depth_band = 'deep'
GROUP BY region
ORDER BY deep_events DESC;

-- 8. Proof that the load is idempotent: this must always return zero rows.
SELECT event_id, COUNT(*)
FROM quakeflow.quake_events
GROUP BY event_id
HAVING COUNT(*) > 1;
