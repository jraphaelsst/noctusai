"""Tests for `make_redis_client` + `make_fake_redis_client` factories.

Pattern parity check: matches the factory-shape tests for
`get_calendar_adapter` and `get_routing_adapter` per
`KB § PATTERNS/seed-fake-real-adapter.md`.
"""

from __future__ import annotations

from noctusai_lib.integrations.redis import (
    make_fake_redis_client,
    make_redis_client,
)


def test_fake_redis_basic_set_get() -> None:
    client = make_fake_redis_client()
    client.set("k", "v")
    assert client.get("k") == "v"


def test_fake_redis_decode_responses_default_true() -> None:
    client = make_fake_redis_client()
    client.set("foo", "bar")
    # decode_responses=True returns str, not bytes
    assert client.get("foo") == "bar"


def test_fake_redis_decode_responses_opt_out() -> None:
    client = make_fake_redis_client(decode_responses=False)
    client.set("foo", "bar")
    assert client.get("foo") == b"bar"


def test_fake_redis_zset_operations_match_buffer_usage() -> None:
    """The buffer/debounce paths use ZADD/ZRANGEBYSCORE/ZSCORE/ZREM —
    verify they all work on the fake (the surface chatbot.buffer relies on)."""
    client = make_fake_redis_client()
    client.zadd("due", {"conv-1": 100.0, "conv-2": 200.0})

    due = client.zrangebyscore("due", "-inf", 150.0)
    assert due == ["conv-1"]

    score = client.zscore("due", "conv-1")
    assert score == 100.0

    removed = client.zrem("due", "conv-1")
    assert removed == 1
    assert client.zscore("due", "conv-1") is None


def test_fake_redis_list_operations_match_memory_usage() -> None:
    """Memory persistence uses RPUSH/LTRIM/LRANGE/EXPIRE."""
    client = make_fake_redis_client()
    client.rpush("memory", "msg-1", "msg-2", "msg-3")
    assert client.lrange("memory", 0, -1) == ["msg-1", "msg-2", "msg-3"]
    client.ltrim("memory", -2, -1)
    assert client.lrange("memory", 0, -1) == ["msg-2", "msg-3"]


def test_fake_redis_stream_xadd_returns_id() -> None:
    """The buffer's stream key uses XADD with maxlen + approximate."""
    client = make_fake_redis_client()
    stream_id = client.xadd(
        "stream",
        {"k": "v"},
        maxlen=10,
        approximate=True,
    )
    assert isinstance(stream_id, str)
    assert "-" in stream_id  # standard XADD id format


def test_real_factory_is_callable() -> None:
    """Smoke test — `make_redis_client` doesn't error on import.

    Not connecting to a Redis server here; just verifying the factory
    is importable + callable shape. Real-server tests live in product
    integration suites that have a Redis service running.
    """
    assert callable(make_redis_client)
