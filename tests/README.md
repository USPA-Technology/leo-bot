
## Live weather AI task

Run the manual weather task from any working directory:

```bash
/path/to/leo-bot/env/bin/python /path/to/leo-bot/tests/test_leo_ai_functions.py 10.7769 106.7009
```

Use `--help` for usage. This task requires Playwright and the configured AI
provider at runtime; importing the module during pytest collection does not
start the task or load its browser dependencies.

# Dagster pipeline definitions and dependency graph:
env/bin/python -m pytest -q tests/test_dagster_pipelines.py

## Recommendation PoC

Run offline regression tests (no hosted AI or database requests):

```bash
env/bin/python -m pytest -q tests/test_recommendation.py
```

To additionally validate PostgreSQL/pgvector using `PGSQL_DB_URL` (or `PGSQL_DB_URL`):

```bash
RUN_RECOMMENDATION_DB_TESTS=1 env/bin/python -m pytest -q tests/test_recommendation.py
```

The database test uses fake embeddings and a unique schema inside a transaction,
then rolls it back; it does not change existing product/profile tables.

## Hybrid place lookup and early discovery readiness

Offline regressions:

```bash
env/bin/python -m pytest -q tests/test_hybrid_places.py tests/test_geo_place_events.py tests/test_nearby_places.py tests/test_geo_places_enrichment.py
node --test tests/leocdp.chatbot.test.cjs
```

Opt-in integration checks:

```bash
RUN_NEARBY_DB_TESTS=1 env/bin/python -m pytest -q tests/test_hybrid_places.py
RUN_REDIS_EVENT_TESTS=1 env/bin/python -m pytest -q tests/test_geo_place_events.py
```

The hybrid SQL test uses fake vectors in a rollback-only schema, checking
distance, tenant isolation, relevance rejection, and chunk deduplication.
It also verifies the three miến-named examples, excludes metadata-only matches,
and keeps vector recommendations outside the name-match list. API/browser tests
verify `places` and `similar_places` remain independent and that recommendations
do not suppress discovery.
Redis checks use unique test run IDs and remove only their own retained keys.
Readiness tests verify publishing after commit, late-subscriber replay, cleanup,
and notification delivery without waiting for a slow Dagster status call.

## Chat response caching

```bash
env/bin/python -m pytest -q tests/test_chat_response_cache.py
RUN_REDIS_EVENT_TESTS=1 env/bin/python -m pytest -q tests/test_chat_response_cache.py tests/test_geo_place_events.py
```

Tests cover the exact five-minute expiry, identical-response cache hits, both API
aliases, rate limits on hits, visitor/request/context isolation, failed responses,
Redis failure logging, stale in-flight writes, and discovery invalidation before
the browser refresh. Real Redis checks execute the atomic Lua scripts using
isolated revision keys and clean up only their own test keys. Other route tests
stub the response cache so they remain offline and independent.