"""ConversationBufferService tests — 7 cases ported verbatim from
`whatsapp-google-scheduling/tests/test_conversation_buffer_service.py`
2026-05-03 via `projects/whatsapp-seed-absorption/` Phase 3.

`FakeRedis` lives in `conftest.py` for reuse by `test_worker.py` (Phase 4).
"""

from noctusai_lib.domain.conversation.buffer import (
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
