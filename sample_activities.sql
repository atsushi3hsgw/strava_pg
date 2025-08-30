SELECT
    data->>'id' AS id,
    data->>'start_date' AS start_date,
    data->>'name' AS name,
    (data->>'distance')::numeric AS distance_m,
    (data->>'moving_time')::int AS moving_time_s,
    (data->>'elapsed_time')::int AS elapsed_time_s,
    (data->>'average_heartrate')::numeric AS avg_hr,
    (data->>'max_heartrate')::numeric AS max_hr
FROM activities
ORDER BY start_date DESC;