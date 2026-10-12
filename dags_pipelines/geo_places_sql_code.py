"""SQL statements used by the geo-places pipeline."""

UPSERT_PLACES = """
INSERT INTO geo_places (
    geo_place_id, name, address, category, tags, pluscode, latitude, longitude,
    geom, phone, website, rating, rating_count, description, image_url, image_source
)
VALUES %s
ON CONFLICT (tenant_id, geo_place_id) DO UPDATE SET
    name = EXCLUDED.name,
    address = COALESCE(EXCLUDED.address, geo_places.address),
    category = EXCLUDED.category,
    pluscode = COALESCE(EXCLUDED.pluscode, geo_places.pluscode),
    latitude = COALESCE(EXCLUDED.latitude, geo_places.latitude),
    longitude = COALESCE(EXCLUDED.longitude, geo_places.longitude),
    geom = COALESCE(EXCLUDED.geom, geo_places.geom),
    phone = COALESCE(EXCLUDED.phone, geo_places.phone),
    website = COALESCE(EXCLUDED.website, geo_places.website),
    rating = EXCLUDED.rating,
    rating_count = EXCLUDED.rating_count,
    description = COALESCE(EXCLUDED.description, geo_places.description),
    image_url = CASE
        WHEN EXCLUDED.image_url IS NOT NULL THEN EXCLUDED.image_url
        ELSE geo_places.image_url
    END,
    image_source = CASE
        WHEN EXCLUDED.image_url IS NOT NULL THEN 'brave'
        ELSE geo_places.image_source
    END,
    data_checked_at = CASE
        WHEN (geo_places.name, geo_places.address, geo_places.geom)
             IS DISTINCT FROM
             (EXCLUDED.name, COALESCE(EXCLUDED.address, geo_places.address), EXCLUDED.geom)
        THEN NULL
        ELSE geo_places.data_checked_at
    END,
    schedule_checked_at = CASE
        WHEN (geo_places.name, geo_places.address, geo_places.website)
             IS DISTINCT FROM
             (EXCLUDED.name, COALESCE(EXCLUDED.address, geo_places.address),
              COALESCE(EXCLUDED.website, geo_places.website))
        THEN NULL
        ELSE geo_places.schedule_checked_at
    END,
    updated_at = NOW()
"""

UPSERT_TEMPLATE = (
    "(%s,%s,%s,%s,%s,%s,%s,%s,"
    "CASE WHEN %s IS NULL OR %s IS NULL THEN NULL::geometry "
    "ELSE ST_SetSRID(ST_MakePoint(%s,%s),4326) END,"
    "%s,%s,%s,%s,%s,%s,%s)"
)

DELETE_SEARCH_SOURCES = """
DELETE FROM knowledge_sources
WHERE user_id=%s AND tenant_id=%s
  AND metadata->>'provider'='brave_search'
  AND metadata->>'geo_place_id'=%s
"""

INSERT_KNOWLEDGE_SOURCE = """
INSERT INTO knowledge_sources (
    id, user_id, tenant_id, source_type, name, uri, status, metadata
)
VALUES (%s,%s,%s,%s,%s,%s,'active',%s)
ON CONFLICT (id) DO UPDATE SET
    name=EXCLUDED.name,
    uri=EXCLUDED.uri,
    status=EXCLUDED.status,
    metadata=EXCLUDED.metadata,
    updated_at=NOW()
"""

INSERT_KNOWLEDGE_CHUNKS = """
INSERT INTO knowledge_chunks (
    id, tenant_id, source_id, content, embedding, chunk_sequence, metadata
)
VALUES (%s,%s,%s,%s,%s::vector,%s,%s)
"""

SELECT_SEARCH_PLACES = """
SELECT id, name, address, category,
       latitude, longitude
FROM geo_places AS gp
WHERE gp.tenant_id = 'global'
  AND (
      gp.data_checked_at IS NULL
      OR gp.data_checked_at < NOW() - make_interval(days => %s)
  )
ORDER BY data_checked_at NULLS FIRST
"""

SELECT_TARGETED_SEARCH_PLACES = """
SELECT gp.id, gp.name, gp.address, gp.category, gp.latitude, gp.longitude
FROM geo_places AS gp
WHERE gp.tenant_id = 'global'
  AND gp.geom IS NOT NULL
  AND ST_DWithin(
      gp.geom::geography,
      ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
      %s
  )
  AND (
      %s = 'places'
      OR lower(coalesce(gp.name, '')) LIKE '%%' || lower(%s) || '%%'
      OR lower(coalesce(gp.description, '')) LIKE '%%' || lower(%s) || '%%'
      OR lower(coalesce(gp.category, '')) LIKE '%%' || lower(%s) || '%%'
      OR EXISTS (
          SELECT 1
          FROM unnest(coalesce(gp.tags, ARRAY[]::text[])) AS tag
          WHERE lower(tag) LIKE '%%' || lower(%s) || '%%'
      )
  )
  AND (
      gp.data_checked_at IS NULL
      OR gp.data_checked_at < NOW() - make_interval(days => %s)
  )
ORDER BY gp.data_checked_at NULLS FIRST,
         ST_Distance(
             gp.geom::geography,
             ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
         ),
         gp.id
LIMIT %s
"""

UPDATE_SEARCH_CHECK = """
UPDATE geo_places
SET data_checked_at=NOW(), updated_at=NOW()
WHERE tenant_id='global' AND id=%s
"""

UPDATE_PLACE_COORDINATES = """
UPDATE geo_places
SET latitude=%s,
    longitude=%s,
    pluscode=%s,
    geom=ST_SetSRID(ST_MakePoint(%s,%s),4326),
    updated_at=NOW()
WHERE tenant_id='global' AND id=%s
"""

SELECT_MASS_SCHEDULE_PLACES = """
SELECT id, name, address, website FROM geo_places
WHERE tenant_id = 'global'
  AND lower(coalesce(category, '')) ~ '(church|cathedral|chapel|parish|nhà thờ)'
  AND (
      schedule_checked_at IS NULL
      OR schedule_checked_at < NOW() - make_interval(days => %s)
  )
ORDER BY schedule_checked_at NULLS FIRST, rating_count DESC NULLS LAST
"""

SELECT_TARGETED_MASS_SCHEDULE_PLACES = """
SELECT gp.id, gp.name, gp.address, gp.website
FROM geo_places AS gp
WHERE gp.tenant_id = 'global'
  AND lower(coalesce(gp.category, '')) ~ '(church|cathedral|chapel|parish|nhà thờ)'
  AND gp.geom IS NOT NULL
  AND ST_DWithin(
      gp.geom::geography,
      ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
      %s
  )
  AND (
      %s = 'places'
      OR lower(coalesce(gp.name, '')) LIKE '%%' || lower(%s) || '%%'
      OR lower(coalesce(gp.category, '')) LIKE '%%' || lower(%s) || '%%'
      OR EXISTS (
          SELECT 1
          FROM unnest(coalesce(gp.tags, ARRAY[]::text[])) AS tag
          WHERE lower(tag) LIKE '%%' || lower(%s) || '%%'
      )
  )
  AND (
      gp.schedule_checked_at IS NULL
      OR gp.schedule_checked_at < NOW() - make_interval(days => %s)
  )
ORDER BY gp.schedule_checked_at NULLS FIRST,
         ST_Distance(
             gp.geom::geography,
             ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
         ),
         gp.rating_count DESC NULLS LAST,
         gp.id
LIMIT %s
"""

UPDATE_MASS_SCHEDULE_FOUND = """
UPDATE geo_places SET
    schedule_operation=%s,
    schedule_source=%s,
    schedule_checked_at=NOW(),
    updated_at=NOW()
WHERE tenant_id='global' AND id=%s
"""

UPDATE_MASS_SCHEDULE_CHECK = """
UPDATE geo_places
SET schedule_checked_at=NOW()
WHERE tenant_id='global' AND id=%s
"""

UPDATE_GEO_PLACE_ENRICHMENT = """
UPDATE geo_places
SET description=%s, tags=%s, updated_at=NOW()
WHERE tenant_id='global' AND id=%s
"""

DELETE_KNOWLEDGE_CHUNKS = """
DELETE FROM knowledge_chunks
WHERE tenant_id=%s AND source_id=%s
"""

SELECT_KNOWLEDGE_PLACES = """
SELECT gp.id, gp.geo_place_id, gp.name, gp.address, gp.category,
       gp.phone, gp.website, gp.description, gp.schedule_operation
FROM geo_places AS gp
WHERE gp.tenant_id = 'global'
  AND NOT EXISTS (
    SELECT 1
    FROM knowledge_sources AS ks
    WHERE ks.tenant_id = 'global'
      AND ks.metadata->>'geo_place_id' = gp.id::text
      AND ks.metadata->>'source' = 'geo_places'
)
ORDER BY gp.created_at, gp.id
"""

SELECT_TARGETED_KNOWLEDGE_PLACES = """
SELECT gp.id, gp.geo_place_id, gp.name, gp.address, gp.category,
       gp.phone, gp.website, gp.description, gp.schedule_operation
FROM geo_places AS gp
WHERE gp.tenant_id = 'global'
  AND gp.geom IS NOT NULL
  AND ST_DWithin(
      gp.geom::geography,
      ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
      %s
  )
  AND (
      %s = 'places'
      OR lower(coalesce(gp.name, '')) LIKE '%%' || lower(%s) || '%%'
      OR lower(coalesce(gp.description, '')) LIKE '%%' || lower(%s) || '%%'
      OR lower(coalesce(gp.category, '')) LIKE '%%' || lower(%s) || '%%'
      OR EXISTS (
          SELECT 1
          FROM unnest(coalesce(gp.tags, ARRAY[]::text[])) AS tag
          WHERE lower(tag) LIKE '%%' || lower(%s) || '%%'
      )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM knowledge_sources AS ks
      WHERE ks.tenant_id = 'global'
        AND ks.metadata->>'geo_place_id' = gp.id::text
        AND ks.metadata->>'source' = 'geo_places'
  )
ORDER BY gp.created_at, gp.id
LIMIT %s
"""
