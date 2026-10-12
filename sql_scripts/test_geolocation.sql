-- Nearest places from the requested test location.
WITH user_location AS (
    SELECT ST_SetSRID(
        ST_MakePoint(106.6467328, 10.747904), 4326
    )::geography AS point
)
SELECT
    p.id,
    p.name,
    p.address,
    p.description,
    p.category,
    p.tags,
    ROUND(ST_Distance(p.geom::geography, u.point)::numeric, 1)
        AS distance_meters
FROM geo_places AS p
CROSS JOIN user_location AS u
WHERE p.tenant_id IN ('default', 'global')
  AND ST_DWithin(p.geom::geography, u.point, 50000)
ORDER BY p.geom::geography <-> u.point
LIMIT 10;