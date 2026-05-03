"""ConversationBufferService tests — 7 cases ported verbatim from
`whatsapp-google-scheduling/tests/test_conversation_buffer_service.py`
2026-05-03 via `projects/whatsapp-seed-absorption/` Phase 3.

`FakeRedis` lives in `conftest.py` for reuse by `test_worker.py` (Phase 4).
"""

from noctusai_lib.domain.chatbot.buffer import (
    ConversationBufferService,
    QueuedConversationMessage,
)


def test_buffers_message_to_memory_with_one_hour_ttl_and_stream_queue(fake_redis) -> None:
    service = ConversationBufferService(
        fake_redis, memory_ttl_seconds=3600, debounce_seconds=8, stream_maxlen=100
    )

    stream_id = service.buffer_inbound(
        QueuedConversationMessage(
            conversation_id="+5511999999999",
            text="Preciso de fotos para ONE0007",
            direction="inbound",
            provider_message_id="msg-1",
            user_id=123,
            timestamp=1000,
        )
    )

    assert stream_id == "1-0"
    assert fake_redis.expirations["conversation:memory:+5511999999999"] == 3600
    assert (
        service.memory_for("+5511999999999")[0]["text"]
        == "Preciso de fotos para ONE0007"
    )
    assert (
        fake_redis.streams["queue:conversation_messages"][0][1]["provider_message_id"]
        == "msg-1"
    )


def test_debounce_due_time_is_extended_by_later_messages(fake_redis) -> None:
    service = ConversationBufferService(fake_redis, debounce_seconds=8)

    service.buffer_inbound(
        QueuedConversationMessage("+5511999999999", "first", "inbound", timestamp=1000)
    )
    service.buffer_inbound(
        QueuedConversationMessage("+5511999999999", "second", "inbound", timestamp=1005)
    )

    assert service.due_conversations(now=1012) == []
    assert service.due_conversations(now=1013) == ["+5511999999999"]


def test_memory_is_trimmed_to_recent_messages(fake_redis) -> None:
    service = ConversationBufferService(fake_redis, max_memory_messages=2)

    for index in range(3):
        service.buffer_inbound(
            QueuedConversationMessage(
                "+5511999999999",
                f"message {index}",
                "inbound",
                timestamp=1000 + index,
            )
        )

    memory = service.memory_for("+5511999999999")

    assert [item["text"] for item in memory] == ["message 1", "message 2"]


def test_idle_due_time_fires_after_idle_timeout_window(fake_redis) -> None:
    service = ConversationBufferService(
        fake_redis, debounce_seconds=8, idle_timeout_seconds=1800
    )

    service.buffer_inbound(
        QueuedConversationMessage("+5511999999999", "oi", "inbound", timestamp=1000)
    )

    assert service.idle_conversations(now=2000) == []
    assert service.idle_conversations(now=2800) == ["+5511999999999"]


def test_buffer_inbound_with_trigger_reply_false_skips_debounce_but_keeps_idle(
    fake_redis,
) -> None:
    service = ConversationBufferService(
        fake_redis, debounce_seconds=8, idle_timeout_seconds=1800
    )

    service.buffer_inbound(
        QueuedConversationMessage(
            "+5511999999999",
            "[Imagem] foto da fachada",
            "inbound",
            timestamp=1000,
        ),
        trigger_reply=False,
    )

    assert service.due_conversations(now=2000) == []
    assert service.idle_conversations(now=2800) == ["+5511999999999"]


def test_outbound_appended_to_memory_bumps_idle_due_time(fake_redis) -> None:
    service = ConversationBufferService(
        fake_redis, debounce_seconds=8, idle_timeout_seconds=1800
    )

    service.buffer_inbound(
        QueuedConversationMessage("+5511999999999", "oi", "inbound", timestamp=1000)
    )
    service.append_to_memory(
        QueuedConversationMessage(
            "+5511999999999", "olá!", "outbound", timestamp=2000
        )
    )

    assert service.idle_conversations(now=3500) == []
    assert service.idle_conversations(now=3801) == ["+5511999999999"]


def test_clear_conversation_removes_memory_and_queue_entries(fake_redis) -> None:
    service = ConversationBufferService(
        fake_redis, debounce_seconds=8, idle_timeout_seconds=1800
    )

    service.buffer_inbound(
        QueuedConversationMessage("+5511999999999", "oi", "inbound", timestamp=1000)
    )

    service.clear_conversation("+5511999999999")

    assert service.memory_for("+5511999999999") == []
    assert service.due_conversations(now=10_000) == []
    assert service.idle_conversations(now=10_000) == []


def test_claim_due_conversations_skips_entries_bumped_past_now(fake_redis) -> None:
    """Race fix: if a new inbound bumped the score past `now` between
    the candidate read and the claim, the worker should NOT zrem
    (would dispatch on a still-debouncing conversation).

    Simulates the race by mutating the sorted-set score after
    zrangebyscore but before the score recheck."""
    service = ConversationBufferService(fake_redis, debounce_seconds=8)
    # Manually set a due conversation with score=10 (clearly due at now=20).
    fake_redis.zadd(service.due_set_key, {"conv-1": 10.0})

    # Patch zrangebyscore so that AFTER it returns ['conv-1'], a "new
    # inbound" bumps the score past `now` BEFORE claim re-checks it.
    original_zrangebyscore = fake_redis.zrangebyscore

    def race_inducing_zrangebyscore(*args, **kwargs):
        result = original_zrangebyscore(*args, **kwargs)
        # Simulate the race: a new inbound just arrived for conv-1
        # and bumped its score past `now`.
        fake_redis.zadd(service.due_set_key, {"conv-1": 100.0})
        return result

    fake_redis.zrangebyscore = race_inducing_zrangebyscore

    claimed = service.claim_due_conversations(now=20.0, limit=10)

    # conv-1 was a candidate but its score bumped past `now` — must NOT
    # be claimed (would dispatch prematurely). Stays in due set for next pass.
    assert claimed == []
    assert fake_redis.zscore(service.due_set_key, "conv-1") == 100.0


def test_claim_due_conversations_returns_and_removes_genuinely_due(fake_redis) -> None:
    """Happy path: when no race occurs, due conversations are pulled
    AND removed atomically-ish. The caller can dispatch on them
    knowing they're claimed."""
    service = ConversationBufferService(fake_redis, debounce_seconds=8)
    fake_redis.zadd(service.due_set_key, {"conv-1": 10.0, "conv-2": 15.0})

    claimed = service.claim_due_conversations(now=20.0, limit=10)

    assert sorted(claimed) == ["conv-1", "conv-2"]
    # Both removed from due set.
    assert fake_redis.zrangebyscore(service.due_set_key, "-inf", "+inf") == []


def test_claim_due_conversations_respects_limit(fake_redis) -> None:
    service = ConversationBufferService(fake_redis, debounce_seconds=8)
    fake_redis.zadd(service.due_set_key, {f"c{i}": float(i) for i in range(10)})

    claimed = service.claim_due_conversations(now=100.0, limit=3)

    assert len(claimed) == 3
    # The remaining 7 stay in the due set.
    remaining = fake_redis.zrangebyscore(service.due_set_key, "-inf", "+inf")
    assert len(remaining) == 7
