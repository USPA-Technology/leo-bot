"""Validation and rate limiting for inbound chat messages."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any
import unicodedata

from fastapi import HTTPException

from main_config import (
    CHAT_MAX_MESSAGE_LENGTH,
    CHAT_MAX_VISITOR_ID_LENGTH,
    RATE_LIMIT_MAX_MESSAGES,
    RATE_LIMIT_WINDOW_SECONDS,
    REDIS_CLIENT,
)


class RequestFilterUnavailable(RuntimeError):
    """Raised when the request filter cannot reach its rate-limit store."""


@dataclass(frozen=True)
class FilteredChatRequest:
    """Normalized chat input accepted by the request filter."""

    visitor_id: str
    message: str


class ChatRequestFilter:
    """Validate chat input and atomically enforce a per-visitor rate limit."""

    _RATE_LIMIT_SCRIPT = """
    local window_start = ARGV[1] - ARGV[2]
    redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, window_start)
    if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then
        return 0
    end
    redis.call('ZADD', KEYS[1], ARGV[1], ARGV[4])
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return 1
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        max_messages: int = RATE_LIMIT_MAX_MESSAGES,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
        max_message_length: int = CHAT_MAX_MESSAGE_LENGTH,
        max_visitor_id_length: int = CHAT_MAX_VISITOR_ID_LENGTH,
    ) -> None:
        if (
            max_messages <= 0
            or window_seconds <= 0
            or max_message_length <= 0
            or max_visitor_id_length <= 0
        ):
            raise ValueError("Request filter limits must be positive")
        self._redis = redis_client
        self._max_messages = max_messages
        self._window_seconds = window_seconds
        self._max_message_length = max_message_length
        self._max_visitor_id_length = max_visitor_id_length

    def filter(
        self,
        visitor_id: str,
        message: str,
        *,
        consume_limit: bool = True,
    ) -> FilteredChatRequest:
        """Normalize and validate input, then consume one rate-limit slot."""
        normalized_visitor_id = self._normalize_visitor_id(visitor_id)
        normalized_message = self._normalize_message(message)
        if consume_limit and not self._consume_rate_limit(normalized_visitor_id):
            raise HTTPException(status_code=429, detail="Too many messages")
        return FilteredChatRequest(normalized_visitor_id, normalized_message)

    def _normalize_visitor_id(self, visitor_id: str) -> str:
        if not isinstance(visitor_id, str):
            raise HTTPException(status_code=400, detail="visitor_id must be text")
        value = unicodedata.normalize("NFC", visitor_id).strip()
        if not value:
            raise HTTPException(status_code=400, detail="visitor_id is empty")
        if len(value) > self._max_visitor_id_length:
            raise HTTPException(status_code=400, detail="visitor_id is too long")
        if any(character in "\x00\r\n" or unicodedata.category(character) == "Cf" for character in value):
            raise HTTPException(status_code=400, detail="visitor_id contains invalid characters")
        return value

    def _normalize_message(self, message: str) -> str:
        if not isinstance(message, str):
            raise HTTPException(status_code=400, detail="Question must be text")
        value = unicodedata.normalize("NFC", message).strip()
        if not value:
            raise HTTPException(status_code=400, detail="Question is empty")
        if len(value) > self._max_message_length:
            raise HTTPException(status_code=413, detail="Question too long")
        if any(character == "\x00" or unicodedata.category(character) == "Cc" and character not in "\t\n" for character in value):
            raise HTTPException(status_code=400, detail="Question contains invalid characters")
        return value

    def _consume_rate_limit(self, visitor_id: str) -> bool:
        now_ms = int(time.time() * 1000)
        key = f"chat_rate_limit:{visitor_id}"
        try:
            result = self._redis.eval(
                self._RATE_LIMIT_SCRIPT,
                1,
                key,
                now_ms,
                self._window_seconds * 1000,
                self._max_messages,
                f"{now_ms}:{uuid.uuid4().hex}",
            )
        except Exception as exc:
            raise RequestFilterUnavailable("Chat rate-limit store is unavailable") from exc
        return bool(result)

    def is_safe_to_answer(self, visitor_id: str) -> bool:
        """Compatibility helper for callers that only need rate-limit status."""
        try:
            normalized_visitor_id = self._normalize_visitor_id(visitor_id)
            return self._consume_rate_limit(normalized_visitor_id)
        except HTTPException:
            return False


chat_request_filter = ChatRequestFilter(REDIS_CLIENT)


def is_safe_to_answer(visitor_id: str) -> bool:
    """Backward-compatible rate-limit entry point for existing integrations."""
    return chat_request_filter.is_safe_to_answer(visitor_id)


def filter_webhook_message(visitor_id: str, message: str) -> FilteredChatRequest | None:
    """Filter a channel message and return ``None`` for rejected input."""
    try:
        return chat_request_filter.filter(visitor_id, message)
    except HTTPException:
        return None