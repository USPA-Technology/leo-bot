import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import Redis
from redis.exceptions import ConnectionError

from leoai import chat_response_cache as caching, geo_place_events
from leoai.ai_intent_detection import IntentDetectionResult, IntentType


class MemoryStore:
    def __init__(self):
        self.values = {}
        self.deadlines = {}
        self.time = 0
        self.client = Mock(spec=Redis)
        self.client.eval.side_effect = self.eval
        self.client.incr.side_effect = self.incr

    def get(self, key):
        if self.deadlines.get(key, float("inf")) <= self.time:
            self.values.pop(key, None)
        return self.values.get(key)

    def set(self, key, value, ttl):
        self.values[key] = value
        self.deadlines[key] = self.time + int(ttl)

    def incr(self, key):
        value = int(self.get(key) or "0") + 1
        self.values[key] = str(value)
        return value

    def eval(
        self, script, key_count, revision_key, response_key, latest_key,
        visitor_revision_key, *args,
    ):
        assert key_count == 4
        revision = f"{self.get(revision_key) or '0'}:{self.get(visitor_revision_key) or '0'}"
        if script == caching.LOOKUP_SCRIPT:
            fingerprint, ttl, request_id = args
            response = self.get(response_key)
            if not (self.get(latest_key) or "").startswith(f"{fingerprint}:"):
                self.values.pop(response_key, None)
                response = None
            self.set(latest_key, f"{fingerprint}:{request_id}", ttl)
            return [revision, response]
        assert script == caching.STORE_SCRIPT
        requested_revision, fingerprint, response, ttl = args
        if revision != requested_revision or self.get(latest_key) != fingerprint:
            return 0
        self.set(response_key, response, ttl)
        return 1


def response(visitor="visitor", answer="answer"):
    return {
        "visitor_id": visitor, "question": "question", "answer": answer,
        "touchpoint_id": "tp", "error_code": 0,
        "places": [], "similar_places": [],
    }


def test_same_payload_hits_cache_for_five_minutes_then_expires():
    store = MemoryStore()
    cache = caching.ChatResponseCache(store.client)

    async def scenario():
        token, result = await cache.lookup("visitor", {"question": "miến"})
        assert result is None
        assert await cache.store(token, response())
        store.time = 299
        _, result = await cache.lookup("visitor", {"question": "miến"})
        assert result == response()
        store.time = 301
        _, result = await cache.lookup("visitor", {"question": "miến"})
        assert result is None

    asyncio.run(scenario())
    assert caching.CHAT_CACHE_TTL_SECONDS == 300


@pytest.mark.parametrize("field,value", [
    ("question", "phở"), ("context", "new context"),
    ("latitude", 10.8), ("longitude", 106.7), ("result_limit", 3),
    ("answer_in_language", "en"), ("answer_in_format", "text"),
    ("persona_id", "other"), ("touchpoint_id", "other-tp"),
    ("active_touchpoint_id", "cached-other"), ("profile_id", "other-profile"),
])
def test_request_and_context_changes_miss_cache(field, value):
    store = MemoryStore()
    cache = caching.ChatResponseCache(store.client)
    payload = {
        "question": "miến", "context": "chatbot", "latitude": 10.79,
        "longitude": 106.67, "result_limit": 5, "answer_in_language": "vi",
        "answer_in_format": "html", "persona_id": "web_user",
        "touchpoint_id": "tp", "active_touchpoint_id": "tp", "profile_id": None,
    }

    async def scenario():
        token, _ = await cache.lookup("visitor", payload)
        await cache.store(token, response())
        _, result = await cache.lookup("visitor", {**payload, field: value})
        assert result is None
        _, previous = await cache.lookup("visitor", payload)
        assert previous is None

    asyncio.run(scenario())


def test_cache_is_visitor_scoped_and_skips_stale_inflight_writes():
    store = MemoryStore()
    cache = caching.ChatResponseCache(store.client)

    async def scenario():
        token, _ = await cache.lookup("visitor", {"question": "A"})
        await cache.store(token, response())
        _, other = await cache.lookup("other", {"question": "A"})
        assert other is None
        await cache.lookup("visitor", {"question": "B"})
        await cache.lookup("visitor", {"question": "A"})
        assert not await cache.store(token, response())
        new_token, _ = await cache.lookup("visitor", {"question": "B"})
        await cache.invalidate_places()
        assert not await cache.store(new_token, response())
        _, result = await cache.lookup("visitor", {"question": "B"})
        assert result is None

    asyncio.run(scenario())


def test_error_responses_are_never_cached_and_corruption_is_rejected():
    store = MemoryStore()
    cache = caching.ChatResponseCache(store.client)

    async def scenario():
        token, _ = await cache.lookup("visitor", {"question": "A"})
        assert not await cache.store(token, {**response(), "error": True})
        assert not await cache.store(token, {**response(), "error_code": 500})
        assert store.get(token.response_key) is None
        store.values[token.response_key] = json.dumps({
            "fingerprint": token.fingerprint, "revision": token.revision,
            "response": response("another-visitor"),
        })
        with pytest.raises(ValueError, match="Invalid cached chat response"):
            await cache.lookup("visitor", {"question": "A"})

    asyncio.run(scenario())


@pytest.fixture
def cached_api(monkeypatch):
    from leobot_router import leobot_main_router as routes

    store = MemoryStore()
    cache = caching.ChatResponseCache(store.client)
    monkeypatch.setattr(routes, "chat_response_cache", cache)
    state = {"touchpoint_id": "tp", "profile_id": None}
    monkeypatch.setattr(routes, "REDIS_CLIENT", SimpleNamespace(
        hget=Mock(side_effect=lambda visitor, field: state[field]),
    ))
    limit = Mock(return_value=True)
    monkeypatch.setattr(routes, "is_safe_to_answer", limit)
    detector = AsyncMock(return_value=IntentDetectionResult(
        primary_intent=IntentType.LOCATION_CHAT, purpose="generate_answer",
        confidence=0.95, entities={"search_name": "miến", "search_terms": ["miến"]},
    ))
    monkeypatch.setattr(routes.intent_detector, "detect_async", detector)
    process = AsyncMock(return_value={
        "response": "Name matches", "enrichment_run_id": None,
        "places": [{"id": "miến", "name": "Miến ngon"}],
        "similar_places": [{"id": "pho", "name": "Phở", "distance_meters": 20}],
    })
    monkeypatch.setattr(routes, "rag_agent", SimpleNamespace(
        process_chat_message_with_metadata=process,
    ))
    app = FastAPI()
    app.include_router(routes.router)
    payload = {
        "visitor_id": "visitor", "question": "5 quán miến ngon",
        "latitude": 10.79, "longitude": 106.67, "answer_in_language": "vi",
    }
    return TestClient(app), payload, detector, process, limit, cache, store, state


def test_api_repeat_skips_models_search_and_history_but_still_rate_limits(cached_api):
    client, payload, detector, process, limit, _, _, _ = cached_api
    first = client.post("/_leoai/ask", json=payload)
    second = client.post("/ask", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["places"][0]["name"] == "Miến ngon"
    assert first.json()["similar_places"][0]["name"] == "Phở"
    detector.assert_awaited_once()
    process.assert_awaited_once()
    assert limit.call_count == 2
    limit.return_value = False
    rejected = client.post("/_leoai/ask", json=payload)
    assert rejected.json()["error_code"] == 429
    assert process.await_count == 1


def test_readiness_invalidates_cached_partial_answer_before_refresh(cached_api):
    client, payload, detector, process, _, cache, store, _ = cached_api
    process.return_value = {
        "response": "Discovery queued", "enrichment_run_id": "run-id",
        "places": [], "similar_places": [],
    }
    first = client.post("/_leoai/ask", json=payload)
    repeated = client.post("/_leoai/ask", json=payload)
    assert first.json() == repeated.json()
    assert process.await_count == 1
    store.incr(caching.CHAT_CACHE_REVISION_KEY)
    process.return_value = {
        "response": "Miến matches saved", "enrichment_run_id": None,
        "places": [{"name": "Miến ngon"}], "similar_places": [],
    }
    refreshed = client.post("/_leoai/ask", json=payload)
    assert refreshed.json()["answer"] == "Miến matches saved"
    assert "enrichment_run_id" not in refreshed.json()
    assert detector.await_count == process.await_count == 2


def test_api_cache_failures_are_logged_and_do_not_hide_fresh_response(
    cached_api, caplog,
):
    client, payload, detector, process, _, cache, store, _ = cached_api
    store.client.eval.side_effect = ConnectionError("Redis cache offline")
    fresh = client.post("/_leoai/ask", json=payload)
    assert fresh.status_code == 200
    assert fresh.json()["answer"] == "Name matches"
    assert "Chat response cache lookup failed" in caplog.text
    assert detector.await_count == process.await_count == 1


def test_api_cache_write_failure_is_logged_and_retry_is_processed(
    cached_api, caplog,
):
    client, payload, detector, process, _, _, store, _ = cached_api
    execute = store.eval

    def fail_writes(script, *args):
        if script == caching.STORE_SCRIPT:
            raise ConnectionError("Cache write failed")
        return execute(script, *args)

    store.client.eval.side_effect = fail_writes
    for _ in range(2):
        assert client.post("/_leoai/ask", json=payload).json()["answer"] == "Name matches"
    assert process.await_count == detector.await_count == 2
    assert "Chat response cache write failed" in caplog.text


def test_api_cache_isolated_between_visitors_and_after_context_changes(cached_api):
    client, payload, detector, process, _, _, _, state = cached_api
    client.post("/_leoai/ask", json=payload)
    other = client.post("/_leoai/ask", json={**payload, "visitor_id": "other"})
    assert other.json()["visitor_id"] == "other"
    assert process.await_count == 2
    state["profile_id"] = "new-profile"
    client.post("/_leoai/ask", json=payload)
    assert process.await_count == detector.await_count == 3
    assert process.call_args.kwargs["cdp_profile_id"] == "new-profile"


def test_invalid_request_is_rejected_before_cache_or_models(cached_api):
    client, payload, detector, process, limit, _, store, _ = cached_api
    invalid = client.post("/_leoai/ask", json={**payload, "question": ""})
    assert invalid.json()["error"] is True
    store.client.eval.assert_not_called()
    limit.assert_not_called()
    detector.assert_not_awaited()
    process.assert_not_awaited()


def test_agent_errors_are_returned_as_errors_and_not_cached(cached_api):
    client, payload, detector, process, _, _, _, _ = cached_api
    process.return_value = {
        "response": "Provider failed", "enrichment_run_id": None, "error": True,
    }
    for _ in range(2):
        result = client.post("/_leoai/ask", json=payload).json()
        assert result["error_code"] == 500
        assert result["error"] is True
    assert detector.await_count == process.await_count == 2


@pytest.mark.skipif(
    os.getenv("RUN_REDIS_EVENT_TESTS") != "1",
    reason="Enable explicitly for isolated Redis cache integration tests.",
)
def test_real_redis_cache_lua_replay_and_discovery_invalidation(monkeypatch):
    suffix = uuid4().hex
    revision_key = f"test:chat-cache:{suffix}:revision"
    monkeypatch.setattr(caching, "CHAT_CACHE_REVISION_KEY", revision_key)
    monkeypatch.setattr(geo_place_events, "CHAT_CACHE_REVISION_KEY", revision_key)
    visitor = f"test-visitor-{suffix}"
    run_id = f"test-run-{suffix}"
    cache = caching.ChatResponseCache()
    keys = [revision_key, *cache.visitor_keys(visitor),
            f"{cache.visitor_keys(visitor)[0]}:revision",
            geo_place_events.geo_place_event_key(run_id)]

    async def scenario():
        try:
            token, result = await cache.lookup(visitor, {"question": "miến"})
            assert result is None
            assert await cache.store(token, response(visitor))
            _, result = await cache.lookup(visitor, {"question": "miến"})
            assert result == response(visitor)
            ttl = await asyncio.to_thread(cache.client.ttl, token.response_key)
            assert 295 <= ttl <= 300
            await asyncio.to_thread(geo_place_events.publish_geo_places_ready, run_id, 3)
            _, result = await cache.lookup(visitor, {"question": "miến"})
            assert result is None
            assert not await cache.store(token, response(visitor, "outdated"))
            fresh_token, _ = await cache.lookup(visitor, {"question": "miến"})
            assert await cache.store(fresh_token, response(visitor, "fresh"))
            await cache.invalidate_visitor(visitor)
            assert not await cache.store(fresh_token, response(visitor, "stale"))
            _, result = await cache.lookup(visitor, {"question": "miến"})
            assert result is None
        finally:
            await asyncio.to_thread(cache.client.delete, *keys)
            cache.client.close()

    asyncio.run(scenario())
