"""ConversationWorker tests.

Sibling test (1 case) ported verbatim + 4 seed-lib-only tests covering
the idle-processor path that the sibling left untested in unit form.
"""

from noctusai_lib.domain.chatbot.worker import ConversationWorker


class FakeBufferService:
    """Minimal buffer surface for worker tests. Mirrors the BufferReader
    Protocol; smaller than the full ConversationBufferService."""

    def __init__(self) -> None:
        self.claimed: list[str] = []
        self.cleared: list[str] = []
        self.memory: dict[str, list[dict]] = {
            "+5511999999999": [
                {"direction": "inbound", "text": "Preciso de fotos", "timestamp": 1000},
                {"direction": "inbound", "text": "ONE0007 amanha", "timestamp": 1005},
            ],
            "+5511888888888": [],
        }
        self.due: list[str] = ["+5511999999999", "+5511888888888"]
        self.idle: list[str] = []

    def claim_due_conversations(self, limit: int = 25) -> list[str]:
        # Atomic-ish pull-and-claim — drains `due` and records the claims.
        ids = self.due[:limit]
        self.due = self.due[limit:]
        self.claimed.extend(ids)
        return ids

    def idle_conversations(self, limit: int = 25) -> list[str]:
        return self.idle[:limit]

    def memory_for(self, conversation_id: str) -> list[dict]:
        return self.memory[conversation_id]

    def clear_conversation(self, conversation_id: str) -> None:
        self.cleared.append(conversation_id)


def test_worker_processes_due_conversations_and_claims_them() -> None:
    """Worker dispatches `processor` for each non-empty-memory conversation
    that was claimed atomically. Empty-memory conversations are skipped
    without dispatch (claim already happened inside claim_due_conversations)."""
    processed: list[tuple[str, list[dict]]] = []
    fake_buffer = FakeBufferService()
    worker = ConversationWorker(
        buffer_service=fake_buffer,
        processor=lambda cid, memory: processed.append((cid, memory)),
    )

    count = worker.process_due_once()

    assert count == 2
    assert processed == [("+5511999999999", fake_buffer.memory["+5511999999999"])]
    assert fake_buffer.claimed == ["+5511999999999", "+5511888888888"]


def test_sweep_idle_returns_zero_without_processor() -> None:
    """idle_processor None → sweep is a no-op."""
    fake_buffer = FakeBufferService()
    fake_buffer.idle = ["+5511999999999"]
    worker = ConversationWorker(buffer_service=fake_buffer, processor=lambda c, m: None)

    assert worker.sweep_idle_once() == 0
    assert fake_buffer.cleared == []


def test_sweep_idle_dispatches_and_clears() -> None:
    fake_buffer = FakeBufferService()
    fake_buffer.idle = ["+5511999999999", "+5511888888888"]
    summarized: list[tuple[str, list[dict]]] = []
    worker = ConversationWorker(
        buffer_service=fake_buffer,
        processor=lambda c, m: None,
        idle_processor=lambda cid, memory: summarized.append((cid, memory)),
    )

    count = worker.sweep_idle_once()

    assert count == 2
    # Empty-memory conversation cleared without dispatch.
    assert summarized == [("+5511999999999", fake_buffer.memory["+5511999999999"])]
    # Both conversations were cleared (one with dispatch, one without).
    assert fake_buffer.cleared == ["+5511999999999", "+5511888888888"]


def test_sweep_idle_logs_exception_and_does_not_clear_on_processor_error() -> None:
    """Per sibling behavior: idle_processor exception is logged + the
    conversation is NOT cleared so the next sweep retries."""
    fake_buffer = FakeBufferService()
    fake_buffer.idle = ["+5511999999999"]

    def failing_processor(cid: str, memory: list[dict]) -> None:
        raise RuntimeError("boom")

    worker = ConversationWorker(
        buffer_service=fake_buffer,
        processor=lambda c, m: None,
        idle_processor=failing_processor,
    )

    worker.sweep_idle_once()

    # NOT cleared — retry on next sweep.
    assert fake_buffer.cleared == []


def test_stop_sets_flag_for_run_forever_exit() -> None:
    """`stop` accepts signal-handler (signum, frame) args without TypeError."""
    fake_buffer = FakeBufferService()
    worker = ConversationWorker(buffer_service=fake_buffer, processor=lambda c, m: None)

    assert worker.should_stop is False
    worker.stop()
    assert worker.should_stop is True

    # Signal-handler-style invocation
    worker.should_stop = False
    worker.stop(15, None)  # SIGTERM
    assert worker.should_stop is True
