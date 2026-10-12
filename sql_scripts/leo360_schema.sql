-- ============================================================================
-- LEO BOT  |  FULL SCHEMA (fresh install)  |  multi-tenant hardened
-- Requires PostgreSQL 18+ (uuidv7()) and pgvector, PostGIS, pg_trgm.
--
-- TENANT RULES USED IN THIS FILE
--   R1. Every table carries tenant_id NOT NULL.
--   R2. Every business key is unique PER TENANT, never globally
--       (message_hash, cdp_profile_id, touchpoint_id, email, login ...).
--   R3. Every foreign key is COMPOSITE (tenant_id, x), so a row can never
--       point at another tenant's row.
--   R4. Shared public reference data (churches, weather) lives under the
--       reserved tenant 'global'. Query it with: tenant_id IN (:tenant, 'global').
--   R5. Optional: enable Row-Level Security with enable_tenant_rls() (last section).
--
-- Search for these tags to see what changed from the original schema:
--   [TENANT FIX]  tenant-isolation bug fixed
--   [FIX]         non-tenant bug that would break or silently misbehave
--   [NEW]         persona-vector tables
-- ============================================================================


-- ============================================================================
-- 0. EXTENSIONS
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector: embeddings
CREATE EXTENSION IF NOT EXISTS postgis;    -- geospatial
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- fuzzy name search


-- ============================================================================
-- 1. ENUM TYPES
-- ============================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'chat_status') THEN
        CREATE TYPE chat_status AS ENUM ('active', 'closed', 'escalated', 'archived');
    END IF;

    -- Type of knowledge source (book, report, dataset, ...)
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'knowledge_source_type') THEN
        CREATE TYPE knowledge_source_type AS ENUM (
            'book_summary', 'report_analytics', 'uploaded_document', 'web_page',
            'research_paper', 'knowledge_base_article', 'dataset', 'code_repository',
            'api_documentation', 'system_log', 'conversation_log', 'meeting_transcript',
            'social_media_post', 'video_transcript', 'audio_transcript', 'other'
        );
    END IF;

    -- State of a document in the ingestion pipeline
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'processing_status') THEN
        CREATE TYPE processing_status AS ENUM ('pending', 'processing', 'active', 'failed', 'archived');
    END IF;
END
$$;


-- ============================================================================
-- 2. HELPER FUNCTIONS (timestamps)
-- ============================================================================
-- Generic: for tables whose column is called updated_at.
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

-- [FIX] chat_messages has last_updated (not updated_at). The original trigger
-- used update_timestamp(), which raises an error on every UPDATE of that table.
CREATE OR REPLACE FUNCTION set_last_updated()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.last_updated := NOW();
    RETURN NEW;
END;
$$;


-- ============================================================================
-- 3. CUSTOMER / IDENTITY (created first: other tables reference it)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- customer_profile
-- [TENANT FIX] PK was cdp_profile_id alone. Two tenants reusing the same id
-- collided. PK is now (tenant_id, cdp_profile_id).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customer_profile (
    tenant_id         VARCHAR(50) NOT NULL,
    cdp_profile_id    VARCHAR(50) NOT NULL,
    full_name         TEXT,
    email             TEXT,
    phone             TEXT,
    country           TEXT,
    age               INT,
    gender            TEXT,
    metadata          JSONB,
    profile_embedding VECTOR(768),
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, cdp_profile_id)
);

-- [FIX] pgvector has no default operator class for ivfflat; the original
-- statement (no opclass) fails. Cosine added.
CREATE INDEX IF NOT EXISTS idx_customer_profile_embedding
    ON customer_profile USING ivfflat (profile_embedding vector_cosine_ops) WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- customer_metrics (RFM / CLV snapshot per profile)
-- [TENANT FIX] PK (tenant_id, cdp_profile_id); composite FK to customer_profile.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customer_metrics (
    tenant_id        VARCHAR(50) NOT NULL,
    cdp_profile_id   VARCHAR(50) NOT NULL,
    last_purchase    TIMESTAMPTZ,
    freq_90d         INT DEFAULT 0,
    avg_order_value  NUMERIC(18, 4) DEFAULT 0,
    monetary_90d     NUMERIC(18, 4) DEFAULT 0,
    clv_est          NUMERIC(18, 4) DEFAULT 0,
    experience_score NUMERIC(6, 2) DEFAULT 0,
    segment          VARCHAR(50),
    segment_reason   JSONB,
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, cdp_profile_id),
    FOREIGN KEY (tenant_id, cdp_profile_id)
        REFERENCES customer_profile (tenant_id, cdp_profile_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_metrics_last_purchase ON customer_metrics (tenant_id, last_purchase);
CREATE INDEX IF NOT EXISTS idx_metrics_freq_90d      ON customer_metrics (tenant_id, freq_90d);

-- ---------------------------------------------------------------------------
-- tenant_metrics_config (per-tenant CLV parameters)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenant_metrics_config (
    tenant_id               VARCHAR(50) PRIMARY KEY,
    expected_lifetime_years NUMERIC(5, 2) DEFAULT 3.0,
    cac                     NUMERIC(18, 4) DEFAULT 5.0,
    clv_happy_threshold     NUMERIC(18, 4) DEFAULT 500.0,
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- transactional_context
-- PK already tenant-scoped. [TENANT FIX] added composite FK to customer_profile
-- so a transaction cannot reference another tenant's profile.
-- NOTE: if events can arrive BEFORE the profile exists, insert a stub
-- customer_profile row first (or drop this FK).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactional_context (
    tenant_id         VARCHAR(50) NOT NULL,
    user_id           VARCHAR(50) NOT NULL,
    txn_id            VARCHAR(50) NOT NULL,
    cdp_profile_id    VARCHAR(50),
    source_system     VARCHAR(255),
    txn_type          VARCHAR(100) NOT NULL,
    txn_status        VARCHAR(50) DEFAULT 'completed',
    txn_timestamp     TIMESTAMPTZ DEFAULT NOW(),
    amount            NUMERIC(18, 4) DEFAULT 0,
    currency          VARCHAR(10) DEFAULT 'USD',
    context_data      JSONB NOT NULL,
    embedding         VECTOR(768),
    category_label    VARCHAR(255),
    intent_label      VARCHAR(255),
    intent_confidence NUMERIC(5, 4) CHECK (intent_confidence >= 0 AND intent_confidence <= 1) DEFAULT 0,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_by        TEXT DEFAULT 'system',
    PRIMARY KEY (tenant_id, user_id, txn_id),
    -- ON DELETE SET NULL (col): only the profile column is nulled, never tenant_id (PG15+)
    FOREIGN KEY (tenant_id, cdp_profile_id)
        REFERENCES customer_profile (tenant_id, cdp_profile_id) ON DELETE SET NULL (cdp_profile_id)
);

CREATE INDEX IF NOT EXISTS idx_txn_user_time
    ON transactional_context (tenant_id, user_id, txn_timestamp DESC);
-- [TENANT FIX] profile-based lookups (used by refresh_customer_metrics) were not tenant-indexed
CREATE INDEX IF NOT EXISTS idx_txn_profile_time
    ON transactional_context (tenant_id, cdp_profile_id, txn_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_txn_type_status
    ON transactional_context (tenant_id, txn_type, txn_status);
CREATE INDEX IF NOT EXISTS idx_txn_context_gin
    ON transactional_context USING GIN (context_data jsonb_path_ops);
-- [FIX] opclass added (see customer_profile)
CREATE INDEX IF NOT EXISTS idx_txn_embedding_ivfflat
    ON transactional_context USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- refresh_customer_metrics(tenant)
-- [TENANT FIX] ON CONFLICT now targets (tenant_id, cdp_profile_id).
-- Logic otherwise unchanged from the original.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION refresh_customer_metrics(p_tenant_id VARCHAR(50))
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    cfg RECORD;
    rec RECORD;
BEGIN
    SELECT * INTO cfg FROM tenant_metrics_config WHERE tenant_id = p_tenant_id;

    IF NOT FOUND THEN
        cfg.expected_lifetime_years := 3.0;
        cfg.cac := 5.0;
        cfg.clv_happy_threshold := 500.0;
    END IF;

    FOR rec IN
        SELECT DISTINCT cdp_profile_id FROM customer_profile WHERE tenant_id = p_tenant_id
    LOOP
        WITH agg AS (
            SELECT
                MAX(txn_timestamp) AS last_purchase,
                COUNT(*) FILTER (WHERE txn_timestamp >= NOW() - INTERVAL '90 days')::INT AS freq_90d,
                AVG(amount) FILTER (WHERE amount > 0) AS avg_order_value,
                COALESCE(
                    SUM(amount) FILTER (WHERE txn_timestamp >= NOW() - INTERVAL '90 days' AND amount > 0),
                    0
                ) AS monetary_90d
            FROM transactional_context
            WHERE tenant_id = p_tenant_id
              AND cdp_profile_id = rec.cdp_profile_id
              AND txn_status = 'completed'
        )
        INSERT INTO customer_metrics AS cm (
            cdp_profile_id, tenant_id, last_purchase, freq_90d, avg_order_value,
            monetary_90d, clv_est, experience_score, segment, segment_reason, updated_at
        )
        SELECT
            rec.cdp_profile_id,
            p_tenant_id,
            a.last_purchase,
            COALESCE(a.freq_90d, 0),
            COALESCE(a.avg_order_value, 0),
            COALESCE(a.monetary_90d, 0),
            -- clv_est
            ROUND(
                (COALESCE(a.avg_order_value, 0) * (COALESCE(a.freq_90d, 0) * 365.0 / 90.0)
                 * cfg.expected_lifetime_years) - cfg.cac, 2
            )::NUMERIC,
            -- experience_score
            ROUND((
                CASE
                    WHEN a.last_purchase IS NULL THEN -60
                    WHEN a.last_purchase >= NOW() - INTERVAL '30 days' THEN 40
                    WHEN a.last_purchase >= NOW() - INTERVAL '90 days' THEN 10
                    ELSE -10
                END
                + LEAST(30, GREATEST(-30,
                    COALESCE(a.monetary_90d, 0)
                    / NULLIF(GREATEST(COALESCE(a.avg_order_value, 0), 1), 0)))
                + LEAST(30, COALESCE(a.freq_90d, 0) * 2)
            ), 2)::NUMERIC,
            -- segment
            CASE
                WHEN (
                    (COALESCE(a.avg_order_value, 0) * (COALESCE(a.freq_90d, 0) * 365.0 / 90.0)
                     * cfg.expected_lifetime_years) - cfg.cac
                ) >= cfg.clv_happy_threshold
                AND (
                    CASE
                        WHEN a.last_purchase IS NULL THEN -60
                        WHEN a.last_purchase >= NOW() - INTERVAL '30 days' THEN 40
                        WHEN a.last_purchase >= NOW() - INTERVAL '90 days' THEN 10
                        ELSE -10
                    END
                    + LEAST(30, GREATEST(-30,
                        COALESCE(a.monetary_90d, 0)
                        / NULLIF(GREATEST(COALESCE(a.avg_order_value, 0), 1), 0)))
                    + LEAST(30, COALESCE(a.freq_90d, 0) * 2)
                ) >= 30 THEN 'happy'
                WHEN a.last_purchase IS NULL AND COALESCE(a.freq_90d, 0) = 0 THEN 'prospective'
                WHEN COALESCE(a.freq_90d, 0) = 0 THEN 'inactive'
                WHEN (
                    (COALESCE(a.avg_order_value, 0) * (COALESCE(a.freq_90d, 0) * 365.0 / 90.0)
                     * cfg.expected_lifetime_years) - cfg.cac
                ) BETWEEN 100 AND (cfg.clv_happy_threshold - 1) THEN 'first_time'
                ELSE 'target'
            END,
            -- segment_reason
            JSONB_BUILD_OBJECT(
                'clv_calc', ROUND(
                    (COALESCE(a.avg_order_value, 0) * (COALESCE(a.freq_90d, 0) * 365.0 / 90.0)
                     * cfg.expected_lifetime_years) - cfg.cac, 2),
                'freq_90d', COALESCE(a.freq_90d, 0),
                'monetary_90d', COALESCE(a.monetary_90d, 0),
                'last_purchase', a.last_purchase
            ),
            NOW()
        FROM agg AS a
        ON CONFLICT (tenant_id, cdp_profile_id) DO UPDATE      -- [TENANT FIX]
        SET last_purchase    = EXCLUDED.last_purchase,
            freq_90d         = EXCLUDED.freq_90d,
            avg_order_value  = EXCLUDED.avg_order_value,
            monetary_90d     = EXCLUDED.monetary_90d,
            clv_est          = EXCLUDED.clv_est,
            experience_score = EXCLUDED.experience_score,
            segment          = EXCLUDED.segment,
            segment_reason   = EXCLUDED.segment_reason,
            updated_at       = NOW();
    END LOOP;
END;
$$;


-- ============================================================================
-- 4. CHAT
-- ============================================================================

-- ---------------------------------------------------------------------------
-- page_index: tenant-scoped table-of-contents vectors used by ContentIndex.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS page_index (
    id          SERIAL PRIMARY KEY,
    tenant_id   VARCHAR(50) NOT NULL DEFAULT 'default',
    page_number INT,
    toc         JSONB,
    embedding   VECTOR(768)
);

CREATE INDEX IF NOT EXISTS idx_page_index_tenant_page
    ON page_index (tenant_id, page_number);
CREATE INDEX IF NOT EXISTS idx_page_index_embedding
    ON page_index USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- chat_messages
-- [TENANT FIX] PK was message_hash alone (global). Now (tenant_id, message_hash).
--   CAVEAT: if message_hash is computed from message text only, two users in
--   the same tenant sending "hi" will collide. Include user_id + timestamp in
--   the hash input (or change the PK to (tenant_id, user_id, message_hash)).
-- [TENANT FIX] Removed UNIQUE (user_id, message_hash): redundant and not tenant-scoped.
-- [TENANT FIX] composite FK to customer_profile.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_messages (
    tenant_id              VARCHAR(50) NOT NULL,
    message_hash           TEXT NOT NULL,
    user_id                VARCHAR(50) NOT NULL,
    cdp_profile_id         VARCHAR(50),
    persona_id             VARCHAR(50),
    touchpoint_id          VARCHAR(50),
    channel                VARCHAR(50) NOT NULL DEFAULT 'webchat',
    status                 chat_status DEFAULT 'active',
    role                   TEXT CHECK (role IN ('user', 'bot')),
    message                TEXT NOT NULL,
    keywords               TEXT[],
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    last_intent_label      VARCHAR(255),
    last_intent_confidence NUMERIC(5, 4) CHECK (last_intent_confidence BETWEEN 0 AND 1),
    last_updated           TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, message_hash),
    FOREIGN KEY (tenant_id, cdp_profile_id)
        REFERENCES customer_profile (tenant_id, cdp_profile_id) ON DELETE SET NULL (cdp_profile_id)
);

-- [TENANT FIX] tenant_id leads every index so tenant filters use the index
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created_at
    ON chat_messages (tenant_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_cdp_profile
    ON chat_messages (tenant_id, cdp_profile_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_tenant_role
    ON chat_messages (tenant_id, role);
CREATE INDEX IF NOT EXISTS idx_chat_messages_tsv
    ON chat_messages USING GIN (to_tsvector('english', message));

-- ---------------------------------------------------------------------------
-- chat_message_embeddings
-- [TENANT FIX] The original FK ignored tenant_id, so an embedding row could
-- carry tenant A while pointing at tenant B's message. Composite FK fixes it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_message_embeddings (
    tenant_id    VARCHAR(50) NOT NULL,
    message_hash TEXT NOT NULL,
    embedding    VECTOR(768),
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, message_hash),
    FOREIGN KEY (tenant_id, message_hash)
        REFERENCES chat_messages (tenant_id, message_hash) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS chat_message_embeddings_embedding_idx
    ON chat_message_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 200);


-- ============================================================================
-- 5. CONVERSATION CONTEXT & TOUCHPOINTS
-- ============================================================================

-- ---------------------------------------------------------------------------
-- conversational_context
-- [TENANT FIX] PK was (user_id, touchpoint_id): the same user/touchpoint id in
-- two tenants overwrote each other. PK is now (tenant_id, user_id, touchpoint_id).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversational_context (
    tenant_id         VARCHAR(50) NOT NULL,
    user_id           VARCHAR(50) NOT NULL,
    touchpoint_id     VARCHAR(50) NOT NULL,
    cdp_profile_id    VARCHAR(50),
    context_data      JSONB NOT NULL,
    embedding         VECTOR(768),
    intent_label      VARCHAR(255),
    intent_confidence NUMERIC(5, 4) CHECK (intent_confidence >= 0 AND intent_confidence <= 1) DEFAULT 0,
    updated_by        TEXT DEFAULT 'system',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, user_id, touchpoint_id),
    FOREIGN KEY (tenant_id, cdp_profile_id)
        REFERENCES customer_profile (tenant_id, cdp_profile_id) ON DELETE SET NULL (cdp_profile_id)
);

CREATE INDEX IF NOT EXISTS idx_context_jsonb
    ON conversational_context USING GIN (context_data jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_context_cdp_profile
    ON conversational_context (tenant_id, cdp_profile_id);
-- (the old idx_context_user (user_id) is dropped: the PK now covers tenant+user lookups)

-- Unchanged: vector index, filtered to rows that have an embedding.
-- Tip: build ivfflat AFTER loading data; lists=1000 suits ~1M rows.
CREATE INDEX IF NOT EXISTS idx_context_embedding
    ON conversational_context USING ivfflat (embedding vector_cosine_ops) WITH (lists = 1000)
    WHERE embedding IS NOT NULL;
-- [TENANT FIX] intent lookups were not tenant-scoped
CREATE INDEX IF NOT EXISTS idx_context_intent_confident
    ON conversational_context (tenant_id, intent_label) WHERE intent_confidence > 0.5;

-- ---------------------------------------------------------------------------
-- touchpoints (user geolocation touchpoints)
-- [TENANT FIX] PK was touchpoint_id alone -> now (tenant_id, touchpoint_id).
-- [TENANT FIX] tenant_id DEFAULT 'default' removed: a missing tenant now fails
--              loudly instead of silently landing in a 'default' tenant.
-- [FIX]        user_id was VARCHAR(255); other tables use VARCHAR(50).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS touchpoints (
    tenant_id     VARCHAR(50) NOT NULL,
    touchpoint_id VARCHAR(64) NOT NULL,
    user_id       VARCHAR(50) NOT NULL,
    latitude      DECIMAL(9, 6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude     DECIMAL(9, 6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    geom          GEOMETRY(Point, 4326) NOT NULL,
    name          TEXT,
    description   TEXT,
    type          VARCHAR(50),
    keywords      TEXT[],
    embedding     VECTOR(768),
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, touchpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_touchpoints_geom ON touchpoints USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_touchpoints_geog ON touchpoints USING GIST ((geom::geography));
CREATE INDEX IF NOT EXISTS idx_touchpoints_user ON touchpoints (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_touchpoints_embedding
    ON touchpoints USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;


-- ============================================================================
-- 6. KNOWLEDGE BASE (RAG)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- knowledge_sources: one row per document / source
-- [TENANT FIX] UNIQUE (tenant_id, id) lets child tables use a composite FK.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_sources (
    id          UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id   VARCHAR(50) NOT NULL,
    user_id     VARCHAR(50) NOT NULL,
    source_type knowledge_source_type DEFAULT 'other',
    name        TEXT NOT NULL,            -- e.g. 'Q3 Financial Report.pdf'
    code_name   VARCHAR(50) DEFAULT '',
    uri         TEXT,                     -- original file location (e.g. s3://bucket/file.md)
    status      processing_status NOT NULL DEFAULT 'pending',
    metadata    JSONB,                    -- author, source URL, ...
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_sources_user_tenant ON knowledge_sources (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_status      ON knowledge_sources (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_fts
    ON knowledge_sources USING GIN (
        to_tsvector('simple'::regconfig,
            coalesce(name, '') || ' ' || coalesce(code_name, '') || ' ' || coalesce(metadata::text, ''))
    );

-- ---------------------------------------------------------------------------
-- knowledge_chunks: text chunks + embeddings
-- [TENANT FIX] This table had NO tenant_id, so vector search could not be
-- filtered by tenant without a join (and could leak across tenants). Added
-- tenant_id plus a composite FK to the parent source.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id             UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id      VARCHAR(50) NOT NULL,                 -- [TENANT FIX]
    source_id      UUID NOT NULL,
    content        TEXT NOT NULL,
    embedding      VECTOR(768) NOT NULL,
    chunk_sequence INT,                                  -- order within the document
    metadata       JSONB,                                -- page number, section headers, ...
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (tenant_id, source_id)
        REFERENCES knowledge_sources (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source
    ON knowledge_chunks (tenant_id, source_id);
-- Similarity search. Always add "WHERE tenant_id = :t" in queries. ivfflat cannot
-- pre-filter, so for big multi-tenant corpora consider HNSW or per-tenant partitions.
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding
    ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_metadata
    ON knowledge_chunks USING GIN (metadata jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_fts
    ON knowledge_chunks USING GIN (to_tsvector('simple', content));


-- ============================================================================
-- 7. SHARED REFERENCE DATA  (tenant_id = 'global' means "visible to every tenant")
-- ============================================================================

-- ---------------------------------------------------------------------------
-- geo_places (Catholic churches in Vietnam)
-- [TENANT FIX] Had no tenant_id. Added, default 'global' (shared catalogue).
--   A tenant may store its own private places under its own tenant_id.
-- [TENANT FIX] Upsert key is now UNIQUE (tenant_id, geo_place_id).
-- [FIX] Removed duplicate indexes and the duplicate updated_at trigger.
-- Query pattern: WHERE tenant_id IN (:tenant, 'global')
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo_places (
    id                  UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id           VARCHAR(50) NOT NULL DEFAULT 'global',   -- [TENANT FIX]
    -- identity (upsert key is (tenant_id, geo_place_id); name is NOT unique)
    geo_place_id        TEXT NOT NULL,
    name                TEXT NOT NULL,
    category            TEXT NOT NULL DEFAULT 'Church',
    tags                TEXT[] NOT NULL DEFAULT '{}',
    -- location
    address             TEXT,
    region_id           TEXT,            -- e.g. VN-HO-CHI-MINH
    pluscode            TEXT,            -- not unique: places can share a cell
    latitude            NUMERIC(9, 6),
    longitude           NUMERIC(9, 6),
    geom                GEOMETRY(Point, 4326),
    geo_maps_uri        TEXT,
    -- contact
    phone               TEXT,
    website             TEXT,
    -- ratings
    rating              NUMERIC(2, 1),
    rating_count        INTEGER,
    description         TEXT,
    -- image
    image_url           TEXT,
    image_source        TEXT,            -- 'brave' | 'wikimedia' | 'google'
    image_attribution   TEXT,
    geo_photo_name      TEXT,            -- durable ref; photoUri expires
    geo_photo_author    TEXT,
    data_checked_at     TIMESTAMPTZ,
    -- Mass schedule, e.g.
    -- {"found":true,"via":"website","confidence":0.9,"source_url":"...","notes":null,
    --  "schedule":[{"days":["mon","tue"],"times":["05:00","17:30"],"note":null}]}
    schedule_operation  JSONB,
    schedule_source     TEXT,
    schedule_checked_at TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT places_tenant_geo_place_id_uq UNIQUE (tenant_id, geo_place_id),   -- [TENANT FIX]
    CONSTRAINT places_geo_place_id_prefix_chk CHECK (geo_place_id ~ '^[a-z][a-z0-9_]*:.+$'),
    CONSTRAINT places_rating_chk       CHECK (rating IS NULL OR rating BETWEEN 0 AND 5),
    CONSTRAINT places_rating_count_chk CHECK (rating_count IS NULL OR rating_count >= 0),
    CONSTRAINT places_image_source_chk CHECK (image_source IS NULL OR image_source IN ('brave', 'wikimedia', 'google')),
    CONSTRAINT places_schedule_operation_chk
        CHECK (schedule_operation IS NULL OR jsonb_typeof(schedule_operation) = 'object'),
    -- (named "vn" originally but only checks valid WGS84 ranges; name kept for compatibility)
    CONSTRAINT places_geom_vn_chk CHECK (ST_Y(geom) BETWEEN -90 AND 90 AND ST_X(geom) BETWEEN -180 AND 180)
);

CREATE INDEX IF NOT EXISTS places_tenant_ix        ON geo_places (tenant_id);
CREATE INDEX IF NOT EXISTS places_geom_gix         ON geo_places USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_places_geog         ON geo_places USING GIST ((geom::geography));
CREATE INDEX IF NOT EXISTS places_region_ix        ON geo_places (tenant_id, region_id);
CREATE INDEX IF NOT EXISTS places_pluscode_ix      ON geo_places (pluscode);
CREATE INDEX IF NOT EXISTS places_tags_gin         ON geo_places USING GIN (tags);
CREATE INDEX IF NOT EXISTS places_name_trgm_gin    ON geo_places USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS places_schedule_operation_gin
    ON geo_places USING GIN (schedule_operation jsonb_path_ops);
-- enrichment work queues ("what is left to do")
CREATE INDEX IF NOT EXISTS places_data_search_todo_ix ON geo_places (data_checked_at NULLS FIRST);
CREATE INDEX IF NOT EXISTS places_schedule_todo_ix    ON geo_places (schedule_checked_at NULLS FIRST);
CREATE INDEX IF NOT EXISTS places_no_image_ix         ON geo_places (id) WHERE image_url IS NULL;

COMMENT ON TABLE  geo_places IS 'Catholic churches in Vietnam, enriched from Brave Search and parish websites. tenant_id=global means shared catalogue.';
COMMENT ON COLUMN geo_places.tenant_id IS 'Owner tenant, or global = shared reference data visible to all tenants';
COMMENT ON COLUMN geo_places.geo_place_id IS 'Upsert key within a tenant (Google Places API New id)';
COMMENT ON COLUMN geo_places.schedule_operation IS 'Mass times as JSON: schedule[].days (mon..sun), times (HH:MM 24h), note';

-- ---------------------------------------------------------------------------
-- weather_data (cached weather by location)
-- [TENANT FIX] Added tenant_id, default 'global' (shared cache).
-- [FIX] ivfflat opclass added.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather_data (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id         VARCHAR(50) NOT NULL DEFAULT 'global',   -- [TENANT FIX]
    original_data     JSONB NOT NULL,        -- full source JSON (audit / re-extraction)
    location_name     TEXT NOT NULL,
    city              TEXT NOT NULL,
    country           TEXT,
    time_zone         TEXT,
    latitude          DECIMAL(9, 6) NOT NULL,
    longitude         DECIMAL(9, 6) NOT NULL,
    geog              GEOGRAPHY(Point, 4326) NOT NULL,       -- fast GPS lookups
    weather_embedding VECTOR(768)                            -- semantic weather queries
);

CREATE INDEX IF NOT EXISTS idx_weather_location_name ON weather_data (tenant_id, location_name);
CREATE INDEX IF NOT EXISTS idx_weather_city          ON weather_data (tenant_id, city);
CREATE INDEX IF NOT EXISTS idx_weather_geog          ON weather_data USING GIST (geog);
CREATE INDEX IF NOT EXISTS idx_weather_embedding
    ON weather_data USING ivfflat (weather_embedding vector_cosine_ops) WITH (lists = 100);


-- ============================================================================
-- 8. SYSTEM USERS (back-office staff)
-- [TENANT FIX] user_email and user_login were UNIQUE across ALL tenants, so two
-- tenants could not have an admin with the same email/login. Now unique per tenant.
-- (Login must therefore receive the tenant.) Redundant single-column indexes removed.
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_users (
    id                    SERIAL PRIMARY KEY,
    tenant_id             VARCHAR(50) NOT NULL,
    activation_key        VARCHAR(64),
    avatar_url            TEXT,
    creation_time         BIGINT NOT NULL,
    custom_data           JSONB,
    display_name          TEXT NOT NULL,
    is_online             BOOLEAN DEFAULT FALSE,
    modification_time     BIGINT,
    registered_time       BIGINT DEFAULT 0,
    role                  INTEGER NOT NULL,
    status                INTEGER NOT NULL,
    user_email            TEXT NOT NULL,
    user_login            TEXT NOT NULL,
    user_pass             TEXT NOT NULL,
    access_profile_fields TEXT[],
    action_logs           TEXT[],
    in_groups             TEXT[],
    business_unit         TEXT,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_system_users_tenant_email UNIQUE (tenant_id, user_email),   -- [TENANT FIX]
    CONSTRAINT uq_system_users_tenant_login UNIQUE (tenant_id, user_login),   -- [TENANT FIX]
    CONSTRAINT check_display_name_not_empty CHECK (display_name <> ''),
    CONSTRAINT check_user_email_not_empty   CHECK (user_email <> ''),
    CONSTRAINT check_user_login_not_empty   CHECK (user_login <> ''),
    CONSTRAINT check_user_pass_not_empty    CHECK (user_pass <> '')
);

CREATE INDEX IF NOT EXISTS idx_system_users_custom_data
    ON system_users USING GIN (custom_data jsonb_path_ops);


-- ============================================================================
-- 9. [NEW] PERSONA-AS-VECTOR
--    All FKs are composite (tenant_id, x). Participant key = (tenant_id, user_id).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 9.1 persona_schemas: data dictionary for the vector (versioned).
--     Coordinate order, meaning, units and normalization live here so a bare
--     array of numbers is never ambiguous.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persona_schemas (
    id              UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id       VARCHAR(50) NOT NULL,
    domain          VARCHAR(50) NOT NULL,                 -- e.g. 'parish_life', 'pilgrimage'
    version         INT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'retired')),
    -- ordered array: [{"idx":0,"code":"V","name":"...","definition":"...","unit":"...",
    --   "normalization":"...","direction":"higher_is_closer","requires_consent_scope":"..."}]
    dimensions      JSONB NOT NULL CHECK (jsonb_typeof(dimensions) = 'array'),
    -- {"metric":"weighted_euclidean","weights":[...],"d_max":1.0}
    distance_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, domain, version),
    UNIQUE (tenant_id, id)
);

-- ---------------------------------------------------------------------------
-- 9.2 persona_consents: append-only opt-in ledger.
--     Separate scopes: joining the journey, each data source, each interaction type.
--     Current state = latest row per scope (view below).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persona_consents (
    id             UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id      VARCHAR(50) NOT NULL,
    user_id        VARCHAR(50) NOT NULL,
    cdp_profile_id VARCHAR(50),
    scope_type     TEXT NOT NULL CHECK (scope_type IN ('journey', 'data_source', 'interaction')),
    scope_key      TEXT NOT NULL,                  -- e.g. 'chat_text', 'location', 'mass_reminder'
    purpose        TEXT NOT NULL,
    channel        VARCHAR(50),
    status         TEXT NOT NULL CHECK (status IN ('granted', 'declined', 'withdrawn', 'expired')),
    notice_version TEXT NOT NULL,
    effective_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMPTZ,
    evidence_ref   TEXT,                           -- action id / policy version, NOT raw sensitive text
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_persona_consents_lookup
    ON persona_consents (tenant_id, user_id, scope_type, scope_key, purpose, effective_at DESC);

-- security_invoker: the view honours the caller's RLS instead of the owner's
CREATE OR REPLACE VIEW persona_consents_current WITH (security_invoker = true) AS
SELECT DISTINCT ON (tenant_id, user_id, scope_type, scope_key, purpose) *
FROM persona_consents
ORDER BY tenant_id, user_id, scope_type, scope_key, purpose, effective_at DESC;

-- Call at EXECUTION time (right before sending), not only when a proposal is made.
CREATE OR REPLACE FUNCTION persona_has_consent(
    p_tenant VARCHAR, p_user VARCHAR, p_scope_type TEXT, p_scope_key TEXT, p_purpose TEXT
) RETURNS BOOLEAN
LANGUAGE sql STABLE AS $$
    SELECT COALESCE((
        SELECT status = 'granted' AND (expires_at IS NULL OR expires_at > NOW())
        FROM persona_consents_current
        WHERE tenant_id = p_tenant AND user_id = p_user
          AND scope_type = p_scope_type AND scope_key = p_scope_key AND purpose = p_purpose
    ), FALSE);
$$;

-- ---------------------------------------------------------------------------
-- 9.3 persona_goals: participant-confirmed goal + setpoint P* (versioned).
--     A change = a NEW version row, never an in-place edit.
--     Setpoint is a range per coordinate (point target: min = max).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persona_goals (
    id                       UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id                VARCHAR(50) NOT NULL,
    goal_key                 UUID NOT NULL,            -- stable across versions
    version                  INT NOT NULL DEFAULT 1,
    user_id                  VARCHAR(50) NOT NULL,
    cdp_profile_id           VARCHAR(50),
    schema_id                UUID NOT NULL,
    title                    TEXT NOT NULL,
    participant_words        TEXT,                     -- the person's own phrasing
    evidence_criteria        JSONB NOT NULL DEFAULT '{}'::jsonb,
    boundaries               JSONB NOT NULL DEFAULT '{}'::jsonb,
    setpoint_min             REAL[],
    setpoint_max             REAL[],
    dim_mask                 REAL[],                   -- weights/mask, 0 = not targeted
    status                   TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'confirmed', 'paused', 'completed', 'closed', 'superseded')),
    change_reason            TEXT,
    participant_confirmed_at TIMESTAMPTZ,
    review_at                TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, goal_key, version),
    FOREIGN KEY (tenant_id, schema_id) REFERENCES persona_schemas (tenant_id, id),
    -- a goal cannot be active unless the participant confirmed it
    CHECK (status NOT IN ('confirmed', 'completed') OR participant_confirmed_at IS NOT NULL),
    CHECK (array_length(setpoint_min, 1) IS NOT DISTINCT FROM array_length(setpoint_max, 1))
);

CREATE INDEX IF NOT EXISTS idx_persona_goals_user ON persona_goals (tenant_id, user_id, status);

-- ---------------------------------------------------------------------------
-- 9.4 persona_evidence: provenance. Never keep only the latest vector.
--     Separates event / assessment / self-report / inference; records
--     MISSINGNESS instead of writing zeros ("silence is not zero").
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persona_evidence (
    id                  UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id           VARCHAR(50) NOT NULL,
    user_id             VARCHAR(50) NOT NULL,
    goal_id             UUID,
    kind                TEXT NOT NULL CHECK (kind IN (
        'event', 'assessment', 'self_report', 'human_review',
        'model_inference', 'correction', 'missing')),
    source              TEXT NOT NULL,                 -- 'chat', 'transaction', 'form', 'coach' ...
    source_message_hash TEXT,
    source_txn_id       VARCHAR(50),
    dimension_code      TEXT,                          -- matches persona_schemas.dimensions[].code
    observed_value      REAL,
    rubric_version      TEXT,
    assessor            TEXT,
    consent_id          UUID,
    missing_reason      TEXT CHECK (missing_reason IS NULL OR missing_reason IN (
        'no_activity', 'logging_failure', 'offline', 'no_permission', 'declined', 'unknown')),
    event_time          TIMESTAMPTZ NOT NULL,                   -- when it happened
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),     -- when we learned of it
    valid_until         TIMESTAMPTZ,
    retracted_at        TIMESTAMPTZ,                            -- correction/withdrawal; keep the row
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    FOREIGN KEY (tenant_id, goal_id)    REFERENCES persona_goals (tenant_id, id),
    FOREIGN KEY (tenant_id, consent_id) REFERENCES persona_consents (tenant_id, id),
    -- only the message column is nulled when a message is deleted, never tenant_id
    FOREIGN KEY (tenant_id, source_message_hash)
        REFERENCES chat_messages (tenant_id, message_hash) ON DELETE SET NULL (source_message_hash),
    UNIQUE (tenant_id, user_id, source, source_message_hash, dimension_code)
);

CREATE INDEX IF NOT EXISTS idx_persona_evidence_user_time
    ON persona_evidence (tenant_id, user_id, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_persona_evidence_goal ON persona_evidence (tenant_id, goal_id);

-- ---------------------------------------------------------------------------
-- 9.5 persona_states: time-versioned estimate P_t with uncertainty.
--     mean = interpretable coordinates (explain / decide);
--     persona_embedding = retrieval only (never used to judge the person).
--     evidence_ids is an array and cannot be an FK: validate in application code.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persona_states (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id         VARCHAR(50) NOT NULL,
    user_id           VARCHAR(50) NOT NULL,
    cdp_profile_id    VARCHAR(50),
    goal_id           UUID,
    schema_id         UUID NOT NULL,
    model_version     TEXT NOT NULL,
    mean              REAL[] NOT NULL,           -- schema order
    variance          REAL[],                    -- per-dimension uncertainty
    covariance        JSONB,                     -- optional full matrix
    evidence_coverage REAL[],                    -- 0..1 per dimension; unknown != "close to goal"
    evidence_ids      UUID[] NOT NULL DEFAULT '{}',
    persona_embedding VECTOR(768),
    as_of             TIMESTAMPTZ NOT NULL,
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, goal_id)   REFERENCES persona_goals (tenant_id, id),
    FOREIGN KEY (tenant_id, schema_id) REFERENCES persona_schemas (tenant_id, id),
    CHECK (variance IS NULL OR array_length(variance, 1) = array_length(mean, 1)),
    CHECK (evidence_coverage IS NULL OR array_length(evidence_coverage, 1) = array_length(mean, 1))
);

CREATE INDEX IF NOT EXISTS idx_persona_states_user_time
    ON persona_states (tenant_id, user_id, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_persona_states_embedding
    ON persona_states USING hnsw (persona_embedding vector_cosine_ops)
    WHERE persona_embedding IS NOT NULL;

CREATE OR REPLACE VIEW persona_states_current WITH (security_invoker = true) AS
SELECT DISTINCT ON (tenant_id, user_id, goal_id) *
FROM persona_states
ORDER BY tenant_id, user_id, goal_id, as_of DESC;

-- ---------------------------------------------------------------------------
-- 9.6 persona_gap_snapshots: derived TG / PAS / TV / PD (recomputable)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persona_gap_snapshots (
    id               UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id        VARCHAR(50) NOT NULL,
    state_id         UUID NOT NULL,
    goal_id          UUID NOT NULL,
    distance_version TEXT NOT NULL,
    dims_in_scope    TEXT[] NOT NULL,
    tg               REAL NOT NULL,              -- transformation gap
    pas              REAL,                       -- alignment = 1 - TG/Dmax
    tv               REAL,                       -- velocity (same goal + distance only)
    pd               REAL,                       -- drift vs previous state
    per_dim_gap      REAL[],                     -- decompose before acting
    is_reanalysis    BOOLEAN NOT NULL DEFAULT FALSE,   -- recomputed against a newer setpoint
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, state_id) REFERENCES persona_states (tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, goal_id)  REFERENCES persona_goals (tenant_id, id),
    UNIQUE (tenant_id, state_id, goal_id, distance_version, dims_in_scope, is_reanalysis)
);

-- ---------------------------------------------------------------------------
-- 9.7 persona_contexts: situation, NOT identity. Must expire.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persona_contexts (
    id            UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id     VARCHAR(50) NOT NULL,
    user_id       VARCHAR(50) NOT NULL,
    touchpoint_id VARCHAR(50),
    context_type  TEXT NOT NULL,                 -- 'availability','device','mobility','stage','budget' ...
    value         JSONB NOT NULL,
    source        TEXT NOT NULL DEFAULT 'self_report',
    consent_id    UUID,
    valid_from    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_until   TIMESTAMPTZ NOT NULL,          -- no open-ended context
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, consent_id) REFERENCES persona_consents (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_persona_contexts_active
    ON persona_contexts (tenant_id, user_id, context_type, valid_until DESC);

-- ---------------------------------------------------------------------------
-- 9.8 recommendation_items: candidate catalogue for the Next Best Action.
--     "no_action", "ask_question" and "human_handoff" are real candidates.
--     ref_table/ref_id points at existing content (cannot be a real FK because
--     it is polymorphic): the referenced row must belong to the same tenant or
--     to 'global'; enforce in application code.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendation_items (
    id                UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id         VARCHAR(50) NOT NULL,
    action_kind       TEXT NOT NULL CHECK (action_kind IN (
        'explain', 'resource', 'place', 'practice', 'schedule_adjust',
        'ask_question', 'human_handoff', 'no_action')),
    ref_table         TEXT CHECK (ref_table IS NULL OR ref_table IN (
        'knowledge_sources', 'knowledge_chunks', 'geo_places')),
    ref_id            UUID,
    title             TEXT NOT NULL,
    target_dims       TEXT[] NOT NULL DEFAULT '{}',
    required_consents JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{"scope_type":..,"scope_key":..,"purpose":..}]
    preconditions     JSONB NOT NULL DEFAULT '{}'::jsonb,   -- domain, context, minimum evidence
    cooldown          INTERVAL,
    embedding         VECTOR(768),
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_reco_items_tenant_kind
    ON recommendation_items (tenant_id, action_kind) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_reco_items_embedding
    ON recommendation_items USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 9.9 recommendation_decisions: why the bot acted (or chose not to).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendation_decisions (
    id               UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id        VARCHAR(50) NOT NULL,
    user_id          VARCHAR(50) NOT NULL,
    touchpoint_id    VARCHAR(50),
    state_id         UUID,
    goal_id          UUID,
    context_ids      UUID[] NOT NULL DEFAULT '{}',
    policy_version   TEXT NOT NULL,
    candidates       JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{item_id, score, excluded_by}]
    chosen_item_id   UUID,
    chosen_kind      TEXT,                                 -- denormalized; 'no_action' allowed
    propensity       NUMERIC(6, 5),                        -- P(this item) for uplift / off-policy eval
    is_exploration   BOOLEAN NOT NULL DEFAULT FALSE,
    experiment_arm   TEXT,
    guardrail_result TEXT NOT NULL DEFAULT 'allowed'
        CHECK (guardrail_result IN ('allowed', 'blocked', 'needs_review', 'ask_first')),
    guardrail_detail JSONB NOT NULL DEFAULT '{}'::jsonb,   -- WHICH condition failed
    proposed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_at      TIMESTAMPTZ,
    execution_check  JSONB,                                -- consent/state/goal re-check at send time
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, state_id)       REFERENCES persona_states (tenant_id, id),
    FOREIGN KEY (tenant_id, goal_id)        REFERENCES persona_goals (tenant_id, id),
    FOREIGN KEY (tenant_id, chosen_item_id) REFERENCES recommendation_items (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_reco_decisions_user_time
    ON recommendation_decisions (tenant_id, user_id, proposed_at DESC);

-- ---------------------------------------------------------------------------
-- 9.10 recommendation_outcomes: feedback, including harm reports and corrections.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendation_outcomes (
    id                 UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id          VARCHAR(50) NOT NULL,
    decision_id        UUID NOT NULL,
    event_type         TEXT NOT NULL CHECK (event_type IN (
        'delivered', 'opened', 'clicked', 'accepted', 'completed',
        'dismissed', 'snoozed', 'opted_out', 'harm_report', 'correction')),
    occurred_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    participant_rating SMALLINT CHECK (participant_rating BETWEEN 1 AND 5),
    detail             JSONB NOT NULL DEFAULT '{}'::jsonb,
    FOREIGN KEY (tenant_id, decision_id)
        REFERENCES recommendation_decisions (tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reco_outcomes_decision
    ON recommendation_outcomes (tenant_id, decision_id, occurred_at);


-- ============================================================================
-- 10. updated_at / last_updated TRIGGERS
-- ============================================================================
DROP TRIGGER IF EXISTS trg_chat_messages_timestamp ON chat_messages;
CREATE TRIGGER trg_chat_messages_timestamp          -- [FIX] uses set_last_updated()
    BEFORE UPDATE ON chat_messages
    FOR EACH ROW EXECUTE FUNCTION set_last_updated();

DROP TRIGGER IF EXISTS trg_places_timestamp ON geo_places;
CREATE TRIGGER trg_places_timestamp
    BEFORE UPDATE ON geo_places
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

DROP TRIGGER IF EXISTS trg_system_users_timestamp ON system_users;
CREATE TRIGGER trg_system_users_timestamp
    BEFORE UPDATE ON system_users
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

DROP TRIGGER IF EXISTS trg_conversational_context_timestamp ON conversational_context;
CREATE TRIGGER trg_conversational_context_timestamp
    BEFORE UPDATE ON conversational_context
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

DROP TRIGGER IF EXISTS trg_persona_goals_timestamp ON persona_goals;
CREATE TRIGGER trg_persona_goals_timestamp
    BEFORE UPDATE ON persona_goals
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

DROP TRIGGER IF EXISTS trg_reco_items_timestamp ON recommendation_items;
CREATE TRIGGER trg_reco_items_timestamp
    BEFORE UPDATE ON recommendation_items
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();


-- ============================================================================
-- 11. OPTIONAL: ROW-LEVEL SECURITY (database-enforced tenant isolation)
-- ============================================================================
-- Composite keys stop cross-tenant REFERENCES; RLS stops cross-tenant READS caused
-- by a forgotten "WHERE tenant_id = ..." in application code.
--
-- Usage: the app runs, per transaction:   SET LOCAL app.tenant_id = 'acme';
-- RLS does not apply to superusers / BYPASSRLS roles: connect as a normal app role.
-- Nothing below is enabled until you uncomment the calls at the bottom.
-- ============================================================================
CREATE OR REPLACE FUNCTION enable_tenant_rls(p_table REGCLASS, p_allow_global BOOLEAN DEFAULT FALSE)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', p_table);
    EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', p_table);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %s', p_table);
    -- read: own tenant (plus shared 'global' rows when allowed); write: own tenant only
    EXECUTE format(
        'CREATE POLICY tenant_isolation ON %s '
        'USING (tenant_id = current_setting(''app.tenant_id'', true) %s) '
        'WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))',
        p_table,
        CASE WHEN p_allow_global THEN 'OR tenant_id = ''global''' ELSE '' END
    );
END;
$$;

-- Per-tenant tables:
-- SELECT enable_tenant_rls(t::regclass) FROM unnest(ARRAY[
--   'customer_profile','customer_metrics','tenant_metrics_config','transactional_context',
--   'chat_messages','chat_message_embeddings','conversational_context','touchpoints',
--   'knowledge_sources','knowledge_chunks','system_users',
--   'persona_schemas','persona_consents','persona_goals','persona_evidence','persona_states',
--   'persona_gap_snapshots','persona_contexts','recommendation_items',
--   'recommendation_decisions','recommendation_outcomes'
-- ]::text[]) AS t;
--
-- Shared reference tables (readable by every tenant):
-- SELECT enable_tenant_rls('geo_places', TRUE);
-- SELECT enable_tenant_rls('weather_data', TRUE);