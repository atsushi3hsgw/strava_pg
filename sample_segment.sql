SELECT
    (effort->>'start_date_local')::timestamp AS start_time,
    (effort->>'elapsed_time')::int AS elapsed_time_sec,
    (effort->>'average_heartrate')::numeric AS avg_heartrate
FROM activities,
     jsonb_array_elements(data->'segment_efforts') AS effort
WHERE (effort->'segment'->>'id')::bigint = 10869382
ORDER BY start_time DESC;