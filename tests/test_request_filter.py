import pytest
from fastapi import HTTPException

from leobot_router.leobot_request_filter import ChatRequestFilter, RequestFilterUnavailable


class FakeRedis:
    def __init__(self, result=1):
        self.result = result
        self.calls = []

    def eval(self, *args):
        self.calls.append(args)
        return self.result


def test_filter_normalizes_and_atomically_consumes_rate_limit_slot():
    redis = FakeRedis()
    request_filter = ChatRequestFilter(redis, max_messages=2, window_seconds=30)

    result = request_filter.filter("  visitor  ", "  Hello\u0301  ")

    assert result.visitor_id == "visitor"
    assert result.message == "Hell\u00f3"
    assert len(redis.calls) == 1
    assert redis.calls[0][0] == ChatRequestFilter._RATE_LIMIT_SCRIPT
    assert redis.calls[0][1] == 1
    assert redis.calls[0][4:6] == (30000, 2)


@pytest.mark.parametrize(
    ("visitor_id", "message", "detail"),
    [
        ("", "hello", "visitor_id is empty"),
        ("visitor", "", "Question is empty"),
        ("visitor", "x" * 1001, "Question too long"),
        ("visitor\x00", "hello", "visitor_id contains invalid characters"),
        ("visitor", "hello\x00", "Question contains invalid characters"),
    ],
)
def test_filter_rejects_invalid_input_without_rate_limit_call(visitor_id, message, detail):
    redis = FakeRedis()
    request_filter = ChatRequestFilter(redis)

    with pytest.raises(HTTPException) as error:
        request_filter.filter(visitor_id, message)

    assert error.value.detail == detail
    assert redis.calls == []


def test_filter_rejects_when_rate_limit_is_exhausted():
    request_filter = ChatRequestFilter(FakeRedis(result=0))

    with pytest.raises(HTTPException) as error:
        request_filter.filter("visitor", "hello")

    assert error.value.status_code == 429


def test_filter_surfaces_rate_limit_store_errors():
    class BrokenRedis:
        def eval(self, *args):
            raise OSError("redis unavailable")

    request_filter = ChatRequestFilter(BrokenRedis())

    with pytest.raises(RequestFilterUnavailable):
        request_filter.filter("visitor", "hello")
