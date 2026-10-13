-- Run outside a transaction on an existing deployment to avoid blocking writers.
CREATE INDEX CONCURRENTLY IF NOT EXISTS places_name_search_gin
ON geo_places USING GIN (to_tsvector('simple', coalesce(name, '')));

CREATE INDEX CONCURRENTLY IF NOT EXISTS places_text_search_gin
ON geo_places USING GIN (
    to_tsvector(
        'simple',
        coalesce(name, '') || ' ' || coalesce(description, '') || ' ' ||
        coalesce(category, '')
    )
);

CREATE INDEX CONCURRENTLY IF NOT EXISTS knowledge_sources_geo_place_lookup_ix
ON knowledge_sources (tenant_id, (metadata->>'geo_place_id'))
WHERE status = 'active'
  AND (metadata->>'source' = 'geo_places'
       OR metadata->>'provider' = 'brave_search');
