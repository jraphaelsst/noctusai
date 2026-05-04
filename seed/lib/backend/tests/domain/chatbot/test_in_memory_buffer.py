"""End-to-end test: ConversationBufferService driven by the in-memory
buffer client (no Redis server required).

This test proves the gold-standard Fake+Real adapter shape works for
the chatbot buffer module: the in-memory client satisfies
`RedisBufferClient` Protocol AND the buffer service produces the
expected behavior when wired to it.
"""

from __future__ import annotations

from noctusai_lib.domain.chatbot import (
    ConversationBufferService,
    QueuedConversationMessage,
    RedisBufferClient,
    make_in_memory_buffer_client,
)


def test_in_memory_client_satisfies_redis_buffer_client_protocol() -> None:
    client = make_in_memory_buffer_client()
    assert isinstance(client, RedisBufferClient)


def test_buffer_inbound_persists_to_memory() -> None:
    client = make_in_memory_buffer_client()
    service = ConversationBufferService(redis_client=client)

    service.buffer_inbound(
        QueuedConversationMessage(
            conversation_id="conv-1",
            text="quero agendar",
            direction="inbound",
            timestamp=1000.0,
        )
    )

    memory = service.memory_for("conv-1")
    assert len(memory) == 1
    assert memory[0]["text"] == "quero agendar"
    assert memory[0]["direction"] == "inbound"


def test_claim_due_conversations_returns_due_after_debounce() -> None:
    client = make_in_memory_buffer_client()
    service = ConversationBufferService(
        redis_client=client, debounce_seconds=8
    )

    service.buffer_inbound(
        QueuedConversationMessage(
            conversation_id="conv-1",
            text="hi",
            direction="inbound",
            timestamp=1000.0,
        )
    )

    # Before debounce window expires — nothing due yet
    assert service.claim_due_conversations(now=1005.0) == []

    # After debounce window — conv-1 is due and gets claimed
    claimed = service.claim_due_conversations(now=1010.0)
    assert claimed == ["conv-1"]

    # Already claimed — second call returns nothing
    assert service.claim_due_conversations(now=1010.0) == []


def test_clear_conversation_drops_memory_and_due() -> None:
    client = make_in_memory_buffer_client()
    service = ConversationBufferService(redis_client=client)

    service.buffer_inbound(
        QueuedConversationMessage(
            conversation_id="conv-1",
            text="hi",
            direction="inbound",
            timestamp=1000.0,
        )
    )
    service.clear_conversation("conv-1")

    assert service.memory_for("conv-1") == []
    assert service.claim_due_conversations(now=2000.0) == []
