# Dagster pipelines

This package exposes one Dagster code location by merging the `defs` objects
from its pipeline modules:

| Python module | Dagster definition | Purpose |
| --- | --- | --- |
| `arango_to_postgres_leo_cdp.py` | `leo_cdp_to_leo_bot_etl` job | Load segment profiles and linked transactions from ArangoDB into PostgreSQL |
| `causal_sales_dag.py` | `causal_sales_dag` job | Illustrative causal sales model with logged inputs and estimates |
| `causal_geo_marketing_dag.py` | `geo_marketing_sales_dag` job | Independent catchment, O2O conversion, store-capacity and campaign-economics simulation |
| `geo_places_pipeline.py` | `geo_places_pipeline` asset job | Search and enrich geo places, then persist their knowledge |
| `hello_world_dag.py` | `hello_world` job | Small example of a config-driven Dagster op |

## ArangoDB to PostgreSQL ETL

The job runs these ops; profile and transaction processing branch after profile
extraction, then join at the metrics refresh:

```text
extract_profiles
├── extract_transactions ── transform_and_embed_txns ── load_txns_to_pg ──┐
└── transform_and_embed_profiles ── load_profiles_to_pg ──────────────────┤
                                └── collect_tenants_from_profiles ────────┴── refresh_metrics_task
```

`extract_profiles` selects active profiles whose `inSegments` contains the
requested `segment_id`. It paginates by `_key` in batches of 5,000. An empty
segment ID returns no profiles; it does not fail the run. Transactions are
selected from `cdp_profile2conversion` where `_from` points to one of those
profiles.

The transform ops build text summaries and request embeddings through
`leoai.ai_core.get_embedding_model()`. Each op submits texts in batches of 64
(configurable per op). Profile records preserve the source document in
`metadata`; transaction records preserve it in `context_data`.

The load ops upsert to:

- `customer_profile`, on `cdp_profile_id`
- `transactional_context`, on `(tenant_id, user_id, txn_id)`

After both loads finish, `refresh_metrics_task` calls
`refresh_customer_metrics(tenant_id)` for each tenant found in the profiles.
Every ETL op has one retry, delayed by five minutes. This job has no schedule;
launch it manually with a non-empty segment ID.

Example Dagster run config:

```yaml
ops:
  extract_profiles:
    config:
      segment_id: "your-segment-id"
      batch_size: 5000
  transform_and_embed_profiles:
    config:
      batch_size: 64
  transform_and_embed_txns:
    config:
      batch_size: 64
```

The embedding adapter uses `EMBEDDING_PROVIDER`, falling back to `AI_PROVIDER`
and then `google`. `EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS` override the
provider defaults; dimensions default to 768. The key is `EMBEDDING_API_KEY`
when set, otherwise it uses the key for the selected provider
(`GEMINI_API_KEY`, `OPENAI_API_KEY`, or `OPENROUTER_API_KEY`).

## Geo places enrichment

For a Vietnamese, student-oriented walkthrough, see
[`geo_places_pipeline.md`](./geo_places_pipeline.md).

The assets upsert to `geo_places` and create matching `knowledge_sources` and
`knowledge_chunks` records. Existing place UUIDs remain unchanged. Initialize
the development database from
[`../sql_scripts/leo360_schema.sql`](../sql_scripts/leo360_schema.sql) before
materializing these assets; the pipeline does not run schema migrations.
Asset dependencies are:

```text
process_places
├── process_brave_search ───┐
└── process_mass_schedule ──┴── process_knowledge
```

The general-purpose assets do the following:

1. **`process_places`** searches with `BravePlaceSearchClient` and upserts by
   `geo_place_id`. The database primary key is `geo_places.id`, used as the
   internal `geo_place_id` when related knowledge records are stored. The search
   name, center latitude/longitude, and radius are
   required inputs supplied through the Dagster run config. Brave's radius is
   a location bias, not a strict distance cutoff. Its category is the requested
   place type; general `places` searches preserve the category supplied by Brave.
   Every `geo_place_id` uses a source prefix such as `brave_api:`, `sample:`,
   `google_api:`, or `leo_crawler:`; the database rejects unprefixed IDs.
   A discovery result without coordinates is still stored with a NULL `geom`;
   `process_brave_search` performs a follow-up place search to recover
   coordinates before continuing enrichment.
   Chat-triggered runs request a bounded candidate pool (`candidate_count`,
   normally 10-15) in one provider call so duplicates and filtered results do not
   consume the entire requested result count. Manual runs keep their existing
   `count` behavior unless `candidate_count` is supplied.
   After the upsert transaction commits, this asset publishes `PLACES_READY`
   through Redis on `geo-places:discovery:<run_id>`. The same event is retained
   for one hour for late SSE subscribers. The browser rechecks saved places
   immediately; it does not wait for web lookup, schedules, or vector generation.
   A Redis failure is logged and the SSE route falls back to Dagster run status.
2. **`process_brave_search`** searches Brave's grounded web context for one
   place at a time. Each place is committed to PostgreSQL before the next place
   is searched, so a later failure does not roll back earlier results. Each
   `grounding.generic` result is stored as a `knowledge_sources` row, and each
   result snippet is embedded and stored as a `knowledge_chunks` row only when
   the result contains the place-name tokens. Church-specific results must also
   contain church/parish/Mass context.
   Unrelated tourism results are skipped. Places are revisited after 90 days by
   default.
3. **`process_mass_schedule`** is intentionally church-specific. It fetches
   parish pages using the shared public-web fetcher, which validates public IPs
   and redirects. It follows only safe same-origin subpages and asks `AIClient`
   to extract schedules with page-text evidence. Non-church categories are
   skipped. It processes and commits one church at a time.
4. **`process_knowledge`** uses `AIClient` to create a factual place description
   and tags, then writes the enriched place and its vectorized knowledge directly
   to PostgreSQL. It upserts one `knowledge_sources` record and its
   768-dimensional `knowledge_chunks` per place. It processes and commits one
   place at a time. Pipeline-owned sources use user `geo_places_pipeline` and
   tenant `global`.

The required search config and optional result count look like:

```yaml
ops:
  process_places:
    config:
      name: "church"
      latitude: 10.7536097
      longitude: 106.6284595
      radius: 6000
      count: 3
```

Other config defaults:

| Config | Defaults |
| --- | --- |
| `BraveSearchConfig` | Vietnamese search; 90-day refresh; 10 results per place; sequential processing |
| `MassScheduleConfig` | 60-day refresh; sequential processing; 0.6 minimum confidence; up to 3 subpages |
| `KnowledgeEnrichmentConfig` | Sequential processing; 200-token chunks; 40-token overlap |

The `geo_places_full_refresh_weekly` schedule runs at `0 2 * * 0` (02:00 every
Sunday, in the Dagster deployment's timezone). Enable the
schedule in Dagster if it should run automatically.

## Geo-marketing simulation

[`causal_geo_marketing_dag.py`](./causal_geo_marketing_dag.py) owns the
`geo_marketing_sales_dag` job and its own config, ops and `defs`. It does not
import the simple sales model. It simulates a single store's local audience,
frequency-limited ad delivery, online orders, O2O visits, store capacity and
campaign economics. It uses assumed inputs, not live GPS, ads or POS data;
reported incremental metrics are simulated differences, not measured causal lift.
For configuration, equations and examples, see
[`causal_geo_marketing_dag.md`](./causal_geo_marketing_dag.md).

Both simulations are registered independently in the package code location.
Geo op definitions use distinct names to avoid collisions; job-local aliases
preserve the existing geo run-config keys and output names.

## Simple causal sales example

`causal_sales_dag` is a small, deterministic example showing how an assumed
causal DAG maps to Dagster op dependencies. All sales quantities are estimates
in thousands; the model is illustrative and does not establish causal effects
from observational data.
For a Vietnamese student-oriented walkthrough, see
[`causal_sales_dag.md`](./causal_sales_dag.md).

```text
marketing_spend ──> ad_impressions ──> website_visits ──> purchases
seasonality_index ───────────────────> website_visits
seasonality_index ─────────────────────────────────────> purchases
product_quality_index ─────────────────────────────────> purchases
```

The structural equations are:

- `ad_impressions = 100 * marketing_spend` (impressions in thousands per
  thousand USD spent)
- `website_visits = ad_impressions * (0.02 + 0.03 * seasonality_index)`
- `purchases = website_visits * (0.02 + 0.03 * product_quality_index + 0.01 * seasonality_index)`

The three root ops are exogenous inputs supplied through Dagster run config.
Each op writes its input, equation, and computed estimate as an info-level
event, visible in the Dagster UI run's Logs tab. Change `marketing_spend` to
explore how this model's downstream estimates respond; the other equations and
assumptions remain fixed.

```yaml
ops:
  marketing_spend:
    config:
      thousands_usd: 10
  seasonality_index:
    config:
      index: 0.5
  product_quality_index:
    config:
      index: 0.7
```

## On-demand geo places enrichment

When nearby chat has no matching local places or fewer results than requested,
the RAG agent submits the existing `geo_places_pipeline` asset job and returns
a search-queued notice after Dagster accepts the run. For partial results, the
response keeps the places already found. It does not wait for completion; the
browser uses SSE readiness to recheck the database as soon as discovery commits.

```text
process_places
├── process_brave_search ───┐
└── process_mass_schedule ──┴── process_knowledge
```

The trigger explicitly selects and runs all four existing assets. Every run
config carries the requested category, center, radius, and at most five
additional places (only the number missing from the request when fewer) through
the downstream database selectors. Discovery requests extra candidates to allow
for existing places, duplicates, and filtering. `process_places` stores
the requested category (for example `Ramen`) instead of forcing `Church`.
`process_brave_search` and `process_knowledge` handle the requested place type;
`process_mass_schedule` runs as part of the job but skips non-church categories.
`process_knowledge` creates place-owned `knowledge_sources` records and embedded
`knowledge_chunks` for matching places that lack a place knowledge source.
Provider and database failures are visible in Dagster.

The regular scheduled/manual run also supports categories other than churches;
the chat trigger builds scoped config for all four assets:

```yaml
ops:
  process_places:
    config:
      name: "ramen"
      latitude: 10.7536097
      longitude: 106.6284595
      radius: 50000
      count: 5
  process_brave_search:
    config:
      search_name: "ramen"
      latitude: 10.7536097
      longitude: 106.6284595
      radius: 50000
      max_places: 5
      refresh_days: 0
  process_mass_schedule:
    config:
      search_name: "ramen"
      latitude: 10.7536097
      longitude: 106.6284595
      radius: 50000
      max_places: 5
  process_knowledge:
    config:
      search_name: "ramen"
      latitude: 10.7536097
      longitude: 106.6284595
      radius: 50000
      max_places: 5
```

The radius is in meters. The shared chat trigger caps discovery and processing
at five places. Restart/reload the Dagster code location after deploying changes.

The chatbot uses `DAGSTER_HOST` (default `localhost`), `DAGSTER_WEB_PORT`
(default `3000`), `DAGSTER_REPOSITORY_LOCATION` (default `dags_pipelines`), and
`DAGSTER_REPOSITORY` (default `__repository__`) to submit runs. The Dagster
process requires the database, Brave, and AI settings listed below.

Manual validation and execution:

```bash
env/bin/python -m test_poc.test_trigger_geo_places_tasks --dry-run
env/bin/python -m test_poc.test_trigger_geo_places_tasks
```

The proof-of-concept CLI runs this same four-asset pipeline for up to five
places (its example search term is church) and polls for completion; chat
requests do not poll.

## Greeting job

`hello_world` logs a greeting and the current time. Its `GreetingConfig.name`
defaults to `World`; override it with:

```yaml
ops:
  hello:
    config:
      name: "Dagster"
```

## Environment and database requirements

Set variables in the Dagster process environment. The pipeline does not
hard-code credentials: Dagster resources use `EnvVar` for their secrets, while
the shared embedding adapter reads its provider settings from the environment.

| Variable | Used by | Required/default |
| --- | --- | --- |
| `PGSQL_DB_URL` | Both database pipelines | Required PostgreSQL DSN |
| `ARANGO_URL` | ArangoDB ETL | Required ArangoDB endpoint |
| `ARANGO_USERNAME` | ArangoDB ETL | Required ArangoDB username |
| `ARANGO_PASSWORD` | ArangoDB ETL | Required ArangoDB password |
| `ARANGO_DATABASE` | ArangoDB ETL | Optional; `leo_cdp` |
| `ARANGO_PROFILE_COLLECTION` | ArangoDB ETL | Optional; `cdp_profile` |
| `ARANGO_TRANSACTION_COLLECTION` | ArangoDB ETL | Optional; `cdp_profile2conversion` |
| `BRAVE_API_KEY` | Place discovery and grounded web search | Required |
| `AI_PROVIDER`, `AI_CHAT_MODEL` | `AIClient` description and schedule generation | Provider defaults apply |
| `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `OPENROUTER_API_KEY` | `AIClient` generation and embedding | Required for the selected provider |
The embedding settings and provider credentials described above are also
required by the ETL's configured embedding provider. The geo places pipeline
requires PostgreSQL/PostGIS access and read/write permissions on `geo_places`,
`knowledge_sources`, and `knowledge_chunks`; its development assets do not
alter the schema.
The ArangoDB ETL expects `customer_profile`, `transactional_context`, and the
`refresh_customer_metrics(text)` function to exist.

## Run and test

From the repository root:

```bash
python -m pip install -r requirements.txt
./start_dagster.sh
```

`start_dagster.sh` starts `dockers/pgsql/start_pgsql_pgvector.sh` first. The
PostgreSQL helper creates `TARGET_DB` when it is missing; `TARGET_DB` defaults
to `leo360` and can be overridden through the environment. Pass
`--reset-db` to reset the PostgreSQL data before Dagster starts.

The script uses `env/bin/dagster` when available, otherwise `dagster` from
`PATH`. By default it starts the local Dagster development deployment. To run
the webserver and daemon as separate supervised processes, use cluster mode:

```bash
./start_dagster.sh --cluster
```

Cluster mode shares `DAGSTER_HOME` between both processes, defaults to
`0.0.0.0:3000`, writes separate webserver and daemon logs under `logs/`, and
commits each pipeline place independently. Override `DAGSTER_HOME`,
`DAGSTER_WEB_HOST`, `DAGSTER_WEB_PORT`, `DAGSTER_LOG_DIR`, or
`DAGSTER_PID_DIR` through the environment. Additional Dagster webserver options
can be passed after `--cluster`.

Use the Dagster UI at `http://localhost:3000` to launch the ETL or greeting job,
materialize geo place assets with the required search config, and enable the
weekly schedule. To check the code location and tests:

```bash
dagster definitions validate -m dags_pipelines
env/bin/python -m pytest -q tests/test_dagster_pipelines.py
```
