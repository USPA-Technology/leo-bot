"""Visitor-scoped latest-request caching with atomic discovery invalidation."""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from redis import Redis

from main_config import REDIS_HOST, REDIS_PORT, REDIS_USER_SESSION_DB

CHAT_CACHE_TTL_SECONDS = 300
CHAT_CACHE_REVISION_KEY = "chat-response:v1:places-revision"

LOOKUP_SCRIPT = """
local revision = (redis.call('GET', KEYS[1]) or '0') .. ':' ..
    (redis.call('GET', KEYS[4]) or '0')
local latest = redis.call('GET', KEYS[3])
local response = redis.call('GET', KEYS[2])
if not latest or string.sub(latest, 1, string.len(ARGV[1])) ~= ARGV[1] then
    redis.call('DEL', KEYS[2])
    response = false
end
redis.call('SET', KEYS[3], ARGV[1] .. ':' .. ARGV[3], 'EX', ARGV[2])
return {revision, response}
"""

STORE_SCRIPT = """
local revision = (redis.call('GET', KEYS[1]) or '0') .. ':' ..
    (redis.call('GET', KEYS[4]) or '0')
if revision ~= ARGV[1] or redis.call('GET', KEYS[3]) ~= ARGV[2] then
    return 0
end
redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[4])
return 1
"""


@dataclass(frozen=True)
class ChatCacheRequest:
    response_key: str
    latest_key: str
    fingerprint: str
    revision: str
    latest_request: str


class ChatResponseCache:
    def __init__(self, client: Redis | None = None):
        self.client = client if client is not None else Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_USER_SESSION_DB,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    @staticmethod
    def visitor_keys(visitor_id: str) -> tuple[str, str]:
        digest = hashlib.sha256(visitor_id.encode("utf-8")).hexdigest()
        return f"chat-response:v1:{digest}", f"chat-response:v1:{digest}:latest"

    async def lookup(
        self, visitor_id: str, payload: dict[str, Any]
    ) -> tuple[ChatCacheRequest, dict[str, Any] | None]:
        encoded = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
            allow_nan=False,
        )
        fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        request_id = uuid4().hex
        response_key, latest_key = self.visitor_keys(visitor_id)
        revision, stored = await asyncio.to_thread(
            self.client.eval, LOOKUP_SCRIPT, 4,
            CHAT_CACHE_REVISION_KEY, response_key, latest_key,
            f"{response_key}:revision",
            fingerprint, CHAT_CACHE_TTL_SECONDS, request_id,
        )
        if isinstance(revision, bytes):
            revision = revision.decode("utf-8")
        request = ChatCacheRequest(
            response_key, latest_key, fingerprint, revision,
            f"{fingerprint}:{request_id}",
        )
        if stored is None:
            return request, None
        entry = json.loads(stored)
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("response"), dict)
            or entry["response"].get("visitor_id") != visitor_id
            or entry["response"].get("error_code") != 0
            or entry["response"].get("error")
            or not isinstance(entry["response"].get("answer"), str)
        ):
            raise ValueError("Invalid cached chat response")
        if entry.get("fingerprint") != fingerprint or entry.get("revision") != revision:
            return request, None
        return request, entry["response"]

    async def store(self, request: ChatCacheRequest, response: dict[str, Any]) -> bool:
        if response.get("error_code") != 0 or response.get("error"):
            return False
        encoded = json.dumps(
            {
                "fingerprint": request.fingerprint,
                "revision": request.revision,
                "response": response,
            },
            ensure_ascii=False, separators=(",", ":"), allow_nan=False,
        )
        return bool(await asyncio.to_thread(
            self.client.eval, STORE_SCRIPT, 4,
            CHAT_CACHE_REVISION_KEY, request.response_key, request.latest_key,
            f"{request.response_key}:revision",
            request.revision, request.latest_request, encoded, CHAT_CACHE_TTL_SECONDS,
        ))

    async def invalidate_visitor(self, visitor_id: str) -> None:
        response_key, latest_key = self.visitor_keys(visitor_id)

        def invalidate() -> None:
            with self.client.pipeline(transaction=True) as transaction:
                transaction.incr(f"{response_key}:revision")
                transaction.delete(response_key, latest_key)
                transaction.execute()

        await asyncio.to_thread(invalidate)

    async def invalidate_places(self) -> None:
        await asyncio.to_thread(self.client.incr, CHAT_CACHE_REVISION_KEY)
