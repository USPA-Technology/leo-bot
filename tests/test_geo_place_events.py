import asyncio
import json
import os
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

from leoai import geo_place_events as events


def test_publish_stores_replay_and_publishes_atomically(monkeypatch):
    client = MagicMock()
    client.__enter__.return_value = client
    transaction = client.pipeline.return_value.__enter__.return_value
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(events, "Redis", factory)

    events.publish_geo_places_ready("run-id", 4)

    client.pipeline.assert_called_once_with(transaction=True)
    transaction.incr.assert_called_once_with(events.CHAT_CACHE_REVISION_KEY)
    key, payload = transaction.set.call_args.args
    assert key == events.geo_place_event_key("run-id")
    assert json.loads(payload) == {
        "run_id": "run-id", "status": "PLACES_READY", "saved_places": 4,
    }
    assert transaction.set.call_args.kwargs["ex"] == 3600
    transaction.publish.assert_called_once_with(key, payload)
    transaction.execute.assert_called_once()


@pytest.mark.parametrize("replay", [True, False])
def test_readiness_replays_or_receives_live_event_and_closes(monkeypatch, replay):
    event = {"run_id": "run-id", "status": "PLACES_READY", "saved_places": 4}
    payload = json.dumps(event)
    client = SimpleNamespace(get=AsyncMock(return_value=payload if replay else None))
    subscription = SimpleNamespace(
        get_message=AsyncMock(side_effect=[None, {"data": payload}])
    )
    closed = []

    @asynccontextmanager
    async def subscribe(run_id):
        assert run_id == "run-id"
        try:
            yield client, subscription
        finally:
            closed.append(True)

    monkeypatch.setattr(events, "subscribe_geo_place_events", subscribe)
    assert asyncio.run(events.wait_for_geo_places_ready("run-id")) == event
    assert closed == [True]
    if replay:
        subscription.get_message.assert_not_awaited()
    else:
        assert subscription.get_message.await_count == 2


@pytest.mark.parametrize(
    "event",
    [
        {"run_id": "other", "status": "PLACES_READY", "saved_places": 4},
        {"run_id": "run-id", "status": "SUCCESS", "saved_places": 4},
        {"run_id": "run-id", "status": "PLACES_READY", "saved_places": -1},
        {"run_id": "run-id", "status": "PLACES_READY", "saved_places": True},
    ],
)
def test_readiness_rejects_wrong_run_and_invalid_payload(event):
    with pytest.raises(ValueError, match="Invalid geo-place discovery event"):
        events.decode_geo_place_event(json.dumps(event), "run-id")


def test_cancelled_subscriber_closes_redis_subscription(monkeypatch):
    closed = []
    reading = asyncio.Event()

    async def read_message(timeout):
        reading.set()
        await asyncio.Event().wait()

    @asynccontextmanager
    async def subscribe(run_id):
        try:
            yield (
                SimpleNamespace(get=AsyncMock(return_value=None)),
                SimpleNamespace(get_message=read_message),
            )
        finally:
            closed.append(True)

    monkeypatch.setattr(events, "subscribe_geo_place_events", subscribe)

    async def scenario():
        task = asyncio.create_task(events.wait_for_geo_places_ready("run-id"))
        await reading.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert closed == [True]


@pytest.mark.parametrize("save_fails", [False, True])
def test_discovery_publishes_only_after_successful_commit(monkeypatch, save_fails):
    from dags_pipelines import geo_places_pipeline as pipeline

    steps = []
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    connection = SimpleNamespace(cursor=Mock(return_value=cursor))

    @contextmanager
    def connect():
        steps.append("transaction")
        yield connection
        if save_fails:
            raise RuntimeError("Commit failed")
        steps.append("commit")

    discovered = pipeline.BravePlace.from_search_result({
        "id": "pho-shop",
        "title": "Pho Shop",
        "coordinates": [10.79, 106.67],
        "categories": ["pho"],
    })
    monkeypatch.setattr(
        pipeline.GeoPlaceSearchService, "search",
        Mock(return_value=([discovered], 0)),
    )
    monkeypatch.setattr(
        pipeline.GeoPlaceRepository, "upsert",
        lambda *args, **kwargs: steps.append("save"),
    )
    publication = Mock(side_effect=lambda *args: steps.append("publish"))
    monkeypatch.setattr(pipeline, "publish_geo_places_ready", publication)
    execute = pipeline.process_places.op.compute_fn.decorated_fn
    kwargs = {
        "context": SimpleNamespace(run=SimpleNamespace(run_id="run-id"), log=Mock()),
        "config": pipeline.DiscoveryConfig(
            name="pho", latitude=10.79, longitude=106.67, radius=5_000, count=4,
            candidate_count=12,
        ),
        "brave": SimpleNamespace(build_client=Mock()),
        "pg": SimpleNamespace(connect=connect),
    }
    if save_fails:
        with pytest.raises(RuntimeError, match="Commit failed"):
            execute(**kwargs)
        publication.assert_not_called()
    else:
        execute(**kwargs)
        assert steps == ["transaction", "save", "commit", "publish"]
        publication.assert_called_once_with("run-id", 1)
        pipeline.GeoPlaceSearchService.search.assert_called_once_with(
            name="pho", latitude=10.79, longitude=106.67, radius=5_000, count=12,
        )


@pytest.mark.skipif(
    os.getenv("RUN_REDIS_EVENT_TESTS") != "1",
    reason="Enable explicitly for run-scoped Redis pub/sub integration tests.",
)
@pytest.mark.parametrize("replay", [False, True])
def test_real_redis_live_delivery_and_late_subscriber_replay(monkeypatch, replay):
    async def scenario():
        run_id = f"test-{uuid4()}"
        key = events.geo_place_event_key(run_id)
        revision_key = f"{key}:cache-revision"
        monkeypatch.setattr(events, "CHAT_CACHE_REVISION_KEY", revision_key)
        subscribed = asyncio.Event()
        original_subscription = events.subscribe_geo_place_events

        @asynccontextmanager
        async def subscribe(run_id):
            async with original_subscription(run_id) as connection:
                subscribed.set()
                yield connection

        monkeypatch.setattr(events, "subscribe_geo_place_events", subscribe)
        async with events.AsyncRedis(
            host=events.REDIS_HOST, port=events.REDIS_PORT,
            db=events.REDIS_USER_SESSION_DB,
        ) as client:
            try:
                if replay:
                    await asyncio.to_thread(events.publish_geo_places_ready, run_id, 4)
                task = asyncio.create_task(events.wait_for_geo_places_ready(run_id))
                if not replay:
                    await asyncio.wait_for(subscribed.wait(), timeout=2)
                    await asyncio.to_thread(events.publish_geo_places_ready, run_id, 4)
                event = await asyncio.wait_for(task, timeout=2)
                assert event == {
                    "run_id": run_id, "status": "PLACES_READY", "saved_places": 4,
                }
            finally:
                await client.delete(key, revision_key)

    asyncio.run(scenario())
