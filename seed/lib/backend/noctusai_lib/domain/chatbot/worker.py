"""Polling worker that drains the conversation buffer's due / idle queues.

Ported from
`whatsapp-google-scheduling/app/workers/conversation_worker.py:ConversationWorker`
2026-05-03 via `projects/whatsapp-seed-absorption/` Phase 4.

The seed lifts ONLY the `ConversationWorker` shell (lines 41-91 of the
sibling) — the consumer-side `build_full_ai_processor` / `build_idle_summary_processor`
glue that wires DB sessions, OpenAI services, signal handlers, etc.
stays inside each product. The seed contract is:

  worker = ConversationWorker(
      buffer_service=ConversationBufferService(redis),
      processor=lambda conversation_id, memory: ...,    # consumer-side
      idle_processor=lambda conversation_id, memory: ...,  # optional
  )
  worker.run_forever()  # poll-loop; signal handler in consumer's main()

`processor` and `idle_processor` are arbitrary callables (sync) — the
seed worker doesn't care what's inside; it just makes sure they're
called for every due conversation and that the buffer's claim semantics
are honored.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

ConversationProcessor = Callable[[str, list[dict[str, Any]]], None]


class BufferReader(Protocol):
    """The buffer surface the worker consumes. `ConversationBufferService`
    satisfies this. Tests use a smaller fake."""

    def claim_due_conversations(self, limit: int = 25) -> list[str]: ...

    def memory_for(self, conversation_id: str) -> list[dict[str, Any]]: ...

    def idle_conversations(self, limit: int = 25) -> list[str]: ...

    def clear_conversation(self, conversation_id: str) -> None: ...


@dataclass
class ConversationWorker:
    """Poll loop + due/idle dispatch. Stop with `worker.stop()` (e.g.
    from a signal handler in the consumer's `main()`)."""

    buffer_service: BufferReader
    processor: ConversationProcessor
    idle_processor: ConversationProcessor | None = None
    poll_seconds: float = 2.0
    due_batch_size: int = 25
    should_stop: bool = False

    def process_due_once(self) -> int:
        """Drain one batch of due conversations.

        Uses `claim_due_conversations` — atomic-ish pull-and-claim with
        score recheck so a late inbound that bumped the debounce score
        past `now` is left for the next pass instead of being claimed
        prematurely. Empty-memory conversations are simply skipped (the
        claim already happened). Returns the batch size."""
        conversation_ids = self.buffer_service.claim_due_conversations(
            limit=self.due_batch_size
        )
        for conversation_id in conversation_ids:
            memory = self.buffer_service.memory_for(conversation_id)
            if not memory:
                continue
            self.processor(conversation_id, memory)
        return len(conversation_ids)

    def sweep_idle_once(self) -> int:
        """Drain one batch of idle-timed-out conversations. Empty-memory
        conversations are cleared without dispatching. Idle processor
        exceptions are logged + the conversation is NOT cleared so the
        next sweep retries (sibling behavior preserved)."""
        if self.idle_processor is None:
            return 0
        idle_ids = self.buffer_service.idle_conversations(
            limit=self.due_batch_size
        )
        for conversation_id in idle_ids:
            memory = self.buffer_service.memory_for(conversation_id)
            if not memory:
                self.buffer_service.clear_conversation(conversation_id)
                continue
            try:
                self.idle_processor(conversation_id, memory)
            except Exception:
                logger.exception("Idle sweep failed for %s", conversation_id)
                continue
            self.buffer_service.clear_conversation(conversation_id)
        return len(idle_ids)

    def run_forever(self) -> None:
        """Poll loop. Calls `process_due_once` + `sweep_idle_once` per
        tick; sleeps `poll_seconds` only when both batches were empty so
        steady-state load doesn't accumulate poll latency."""
        logger.info("Conversation worker started")
        while not self.should_stop:
            processed = self.process_due_once()
            idle_processed = self.sweep_idle_once()
            if processed == 0 and idle_processed == 0:
                time.sleep(self.poll_seconds)
        logger.info("Conversation worker stopped")

    def stop(self, *_args: object) -> None:
        """SIGTERM/SIGINT-compatible stop. The `*_args` swallows the
        signal-handler `(signum, frame)` arguments."""
        self.should_stop = True
