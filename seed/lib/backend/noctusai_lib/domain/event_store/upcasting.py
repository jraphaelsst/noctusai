"""Upcasters -- read-time migration of old event shapes. Stored events are NEVER rewritten.

An upcaster is a pure function `data -> data` keyed by `(event_type, from_version)` that produces the shape of
`from_version + 1`. On load the chain runs until the event reaches the type's current version:

    up = Upcasters()
    up.register("subscription.created", 1, lambda d: {**d, "currency": "BRL"})   # v1 -> v2
    stream = load_stream(store, org, "subscription", sid, upcasters=up)          # every event at its current version

`assert_every_stored_type_handled` is the test a consumer runs against its real store
(`store.stored_event_types()`): every `(event_type, schema_version)` that exists in the log must have a handler
AND a complete upcaster chain to the current version. There is deliberately NO CHECK constraint on
`event_type` in the database -- a closed list there would make every new event type a migration; this test is
the gate instead (KB § PATTERNS/backend/event-store.md § Upcasting).
"""
from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any, Callable, Iterable, Mapping, Optional

from .types import LoadedStream, StoredEvent

Upcaster = Callable[[dict], dict]


class UpcastError(LookupError):
    pass


class Upcasters:
    def __init__(self) -> None:
        self._fns: dict[tuple[str, int], Upcaster] = {}

    def register(self, event_type: str, from_version: int, fn: Upcaster) -> "Upcasters":
        if from_version < 1:
            raise ValueError("from_version starts at 1")
        key = (event_type, from_version)
        if key in self._fns:
            raise ValueError(f"upcaster {key} already registered")
        self._fns[key] = fn
        return self

    def current_version(self, event_type: str) -> int:
        versions = [v for (t, v) in self._fns if t == event_type]
        return max(versions) + 1 if versions else 1

    def chain_gap(self, event_type: str, schema_version: int) -> Optional[int]:
        """The first version with no upcaster on the way to current (None = the chain is complete)."""
        current = self.current_version(event_type)
        if schema_version > current:
            return schema_version
        for v in range(schema_version, current):
            if (event_type, v) not in self._fns:
                return v
        return None

    def upcast(self, event: StoredEvent) -> StoredEvent:
        gap = self.chain_gap(event.event_type, event.schema_version)
        if gap is not None:
            raise UpcastError(f"no upcaster for {event.event_type} v{gap} (stored v{event.schema_version}, "
                              f"current v{self.current_version(event.event_type)})")
        data, version = copy.deepcopy(event.data), event.schema_version
        while version < self.current_version(event.event_type):
            data = self._fns[(event.event_type, version)](data)
            version += 1
        return replace(event, data=data, schema_version=version)


def upcast_stream(stream: LoadedStream, upcasters: Optional[Upcasters]) -> LoadedStream:
    if upcasters is None:
        return stream
    return LoadedStream(stream.version, tuple(upcasters.upcast(e) for e in stream.events))


def load_stream(store: Any, org_id: str, stream_type: str, stream_id: str, *, from_version: int = 1,
                upcasters: Optional[Upcasters] = None) -> LoadedStream:
    """`store.load(...)` with every event upcast to its type's current version."""
    return upcast_stream(store.load(org_id, stream_type, stream_id, from_version=from_version), upcasters)


def unhandled_stored_types(stored: Mapping[tuple[str, int], int], *, handled: Iterable[str],
                           upcasters: Optional[Upcasters] = None) -> list[str]:
    """Every stored `(event_type, schema_version)` without a handler or without a complete upcaster chain."""
    handled = set(handled)
    up = upcasters or Upcasters()
    problems: list[str] = []
    for (event_type, version), count in sorted(stored.items()):
        if event_type not in handled:
            problems.append(f"{event_type} v{version} ({count} stored): no handler")
            continue
        gap = up.chain_gap(event_type, version)
        if gap is not None:
            problems.append(f"{event_type} v{version} ({count} stored): no upcaster from v{gap} "
                            f"to current v{up.current_version(event_type)}")
    return problems


def assert_every_stored_type_handled(store_or_types: Any, *, handled: Iterable[str],
                                     upcasters: Optional[Upcasters] = None) -> None:
    """Fail when the log holds an event the code cannot read. Pass the store (its `stored_event_types()` is
    called) or the mapping itself."""
    stored = store_or_types.stored_event_types() if hasattr(store_or_types, "stored_event_types") else store_or_types
    problems = unhandled_stored_types(stored, handled=handled, upcasters=upcasters)
    assert not problems, "stored events the code cannot read:\n  " + "\n  ".join(problems)


__all__ = [
    "UpcastError",
    "Upcaster",
    "Upcasters",
    "assert_every_stored_type_handled",
    "load_stream",
    "unhandled_stored_types",
    "upcast_stream",
]
