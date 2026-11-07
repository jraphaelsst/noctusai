"""`execute(...)` -- the command loop: load -> fold -> decide -> append, re-deciding on a version conflict.

    def evolve(state, event):            # pure fold of one (upcast) event
        ...
    def decide(state) -> list[NewEvent]: # the business rule; [] = nothing to do
        ...
    result = execute(store, org, "subscription", sid, decide, evolve=evolve, initial=None, upcasters=up)

On `conflict` (someone appended since our load) the stream is RELOADED and `decide` runs again on the new state --
never a blind re-append of the first decision, which was taken on stale facts. After `max_attempts` conflicts it
raises `ConcurrencyConflict`. Give events stable ids (derived from the command) so a retried request answers
`replayed`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from .types import AppendOutcome, NewEvent, StoredEvent
from .upcasting import Upcasters, load_stream

DEFAULT_MAX_ATTEMPTS = 3


class ConcurrencyConflict(RuntimeError):
    def __init__(self, stream_type: str, stream_id: str, attempts: int, current_version: Optional[int]) -> None:
        super().__init__(f"{stream_type}/{stream_id}: still conflicting after {attempts} attempts "
                         f"(current version {current_version})")
        self.stream_type, self.stream_id = stream_type, stream_id
        self.attempts, self.current_version = attempts, current_version


@dataclass(frozen=True)
class ExecuteResult:
    """`outcome` is None when `decide` returned no events (nothing appended); otherwise ok / replayed / refused."""

    outcome: Optional[AppendOutcome]
    state: Any
    events: tuple[NewEvent, ...]
    attempts: int


def fold(events: Sequence[StoredEvent], evolve: Callable[[Any, StoredEvent], Any], initial: Any) -> Any:
    state = initial
    for e in events:
        state = evolve(state, e)
    return state


def execute(store: Any, org_id: str, stream_type: str, stream_id: str, decide: Callable[[Any], Sequence[NewEvent]], *,
            evolve: Callable[[Any, StoredEvent], Any], initial: Any = None, upcasters: Optional[Upcasters] = None,
            max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> ExecuteResult:
    if max_attempts < 1:
        raise ValueError("max_attempts >= 1")
    current: Optional[int] = None
    for attempt in range(1, max_attempts + 1):
        stream = load_stream(store, org_id, stream_type, stream_id, upcasters=upcasters)
        state = fold(stream.events, evolve, initial)
        events = tuple(decide(state))
        if not events:
            return ExecuteResult(None, state, (), attempt)
        outcome = store.append(org_id, stream_type, stream_id, events, expected_version=stream.version)
        if outcome.status != "conflict":
            return ExecuteResult(outcome, state, events, attempt)
        current = outcome.current_version
    raise ConcurrencyConflict(stream_type, str(stream_id), max_attempts, current)


__all__ = ["ConcurrencyConflict", "DEFAULT_MAX_ATTEMPTS", "ExecuteResult", "execute", "fold"]
