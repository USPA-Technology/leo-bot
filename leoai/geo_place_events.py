"""Run-scoped discovery notifications shared by Dagster and the chat SSE route."""

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.client import PubSub

from main_config import REDIS_HOST, REDIS_PORT, REDIS_USER_SESSION_DB
from leoai.chat_response_cache import CHAT_CACHE_REVISION_KEY

EVENT_TTL_SECONDS = 3600


def geo_place_event_key(run_id: str) -> str:
    return f"geo-places:discovery:{run_id}"


def publish_geo_places_ready(run_id: str, saved_places: int) -> None:
    """Persist replay state and publish only after the discovery transaction commits."""
    event = json.dumps(
        {
            "run_id": run_id,
            "status": "PLACES_READY",
            "saved_places": saved_places,
        },
        separators=(",", ":"),
    )
    key = geo_place_event_key(run_id)
    with Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_USER_SESSION_DB,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    ) as client:
        with client.pipeline(transaction=True) as transaction:
            transaction.incr(CHAT_CACHE_REVISION_KEY)
            transaction.set(key, event, ex=EVENT_TTL_SECONDS)
            transaction.publish(key, event)
            transaction.execute()


@asynccontextmanager
async def subscribe_geo_place_events(
    run_id: str,
) -> AsyncGenerator[tuple[AsyncRedis, PubSub], None]:
    async with AsyncRedis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_USER_SESSION_DB,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    ) as client:
        async with client.pubsub(ignore_subscribe_messages=True) as subscription:
            await subscription.subscribe(geo_place_event_key(run_id))
            yield client, subscription


def decode_geo_place_event(data: str | bytes, run_id: str) -> dict[str, Any]:
    event = json.loads(data)
    if (
        not isinstance(event, dict)
        or event.get("run_id") != run_id
        or event.get("status") != "PLACES_READY"
        or isinstance(event.get("saved_places"), bool)
        or not isinstance(event.get("saved_places"), int)
        or event["saved_places"] < 0
    ):
        raise ValueError("Invalid geo-place discovery event")
    return event


async def wait_for_geo_places_ready(run_id: str) -> dict[str, Any]:
    async with subscribe_geo_place_events(run_id) as (client, subscription):
        # Subscribe before replaying state so a commit cannot fall into a gap.
        stored_event = await client.get(geo_place_event_key(run_id))
        if stored_event is not None:
            return decode_geo_place_event(stored_event, run_id)
        while True:
            message = await subscription.get_message(timeout=1)
            if message is not None:
                return decode_geo_place_event(message["data"], run_id)
