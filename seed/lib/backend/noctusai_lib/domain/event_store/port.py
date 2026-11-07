"""`EventStore` + `CheckpointStore` -- the Python seams over the event store organ.

Protocol + Fake + Real + factory (CLAUDE.md §1 seed IO rule), for each:

- `RealSupabaseEventStore(client)` / `RealSupabaseCheckpointStore(client)` -- call the RPCs
  `event_store_migration` renders, over the product's schema-scoped PostgREST client
  (`client.rpc(name, params).execute()`);
- `FakeEventStore()` / `FakeCheckpointStore(store)` -- in memory with the SAME semantics (expected-version
  conflicts, idempotent replay, org isolation, sync projections inside the append, async projections that move
  the read model and the checkpoint together, shadow rebuild, refusal codes); consumers' tests run against it;
- `make_event_store(kind, client=...)` / `make_checkpoint_store(kind, client=..., store=...)`.

ONE conformance suite (`tests/domain/event_store/conformance.py`) runs against the Fake and against the Real on
real Postgres (PGlite). A refusal is DATA (`status == "refused"` + a stable `code`), never an exception; a
caller bug (an inverted checkpoint cursor) raises `ValueError` in both.

A projection's handler is backend-shaped: for the Real it is the NAME of a SQL function
`<schema>.<handler>(p_events jsonb, p_target regclass) RETURNS void` (registered from the product's migration);
for the Fake a Python callable `handler(events: list[StoredEvent], table: dict) -> None` writing a dict read model.

Append refusal codes: `invalid_stream` · `invalid_stream_type` · `invalid_expected_version` · `empty` ·
`invalid_event_type` · `invalid_data` · `invalid_metadata` · `invalid_schema_version` · `duplicate_event_id` ·
`pii_disabled` · `org_mismatch` · `idempotency_conflict` · `invalid_event` · `projection_failed`.
"""
from __future__ import annotations

import copy
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

from .config import ANY_VERSION, NAME_PATTERN, PROJECTION_MODES
from .types import (
    AppendOutcome,
    Checkpoint,
    Cursor,
    LoadedStream,
    NewEvent,
    ProjectionRun,
    ReadBatch,
    RebuildOutcome,
    RebuildStep,
    StoredEvent,
    validate_events,
)

_NAME_RE = re.compile(NAME_PATTERN)
MAX_BATCH = 5000

#: Fake handler: mutate the read-model dict in place; raise to fail the batch.
FakeHandler = Callable[[list[StoredEvent], dict], None]


@runtime_checkable
class EventStore(Protocol):
    def append(self, org_id: str, stream_type: str, stream_id: str, events: Sequence[NewEvent], *,
               expected_version: int = ANY_VERSION) -> AppendOutcome: ...

    def load(self, org_id: str, stream_type: str, stream_id: str, *, from_version: int = 1) -> LoadedStream: ...

    def read_all(self, after: Cursor = Cursor(), *, limit: int = 500,
                 stream_types: Optional[Sequence[str]] = None) -> ReadBatch: ...

    def stored_event_types(self) -> dict[tuple[str, int], int]: ...

    def register_projection(self, name: str, *, handler: Any, target: str, stream_types: Sequence[str],
                            mode: Literal["sync", "async"] = "async") -> Optional[str]: ...

    def run_projection(self, name: str, *, limit: int = 500) -> ProjectionRun: ...

    def rebuild_begin(self, name: str) -> Optional[str]: ...

    def rebuild_step(self, name: str, *, limit: int = 1000) -> RebuildStep: ...

    def rebuild_swap(self, name: str) -> RebuildOutcome: ...


@runtime_checkable
class CheckpointStore(Protocol):
    def get(self, projection: str) -> Checkpoint: ...

    def advance(self, projection: str, *, expected: Cursor, to: Cursor) -> Literal["ok", "conflict"]: ...

    def record_error(self, projection: str, error: str) -> None: ...

    def reset(self, projection: str, *, to: Cursor = Cursor()) -> None: ...


def _uuid(value: Any, what: str) -> str:
    """Canonical uuid text; a malformed id is a caller bug (ValueError), in the Fake and the Real alike."""
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise ValueError(f"{what} must be a uuid, got {value!r}") from None


def _check_advance(expected: Cursor, to: Cursor) -> None:
    if to <= expected:
        raise ValueError(f"checkpoint must move forward: {expected} -> {to}")


# -- Real ---------------------------------------------------------------------------------------------------


class _Rpc:
    def __init__(self, client: Any) -> None:
        if client is None:
            raise ValueError("the Supabase event store needs `client` (the product's schema-scoped PostgREST client)")
        self._client = client

    def _call(self, name: str, params: Optional[dict] = None) -> Any:
        return self._client.rpc(name, params or {}).execute().data


class RealSupabaseEventStore(_Rpc):
    """The organ's RPCs over PostgREST."""

    def append(self, org_id, stream_type, stream_id, events, *, expected_version=ANY_VERSION) -> AppendOutcome:
        if org_id is None or stream_id is None:
            return AppendOutcome("refused", code="invalid_stream")
        org, sid = _uuid(org_id, "org_id"), _uuid(stream_id, "stream_id")
        events = [e.with_id() if isinstance(e, NewEvent) else e for e in events]
        code = validate_events(stream_type, events)
        if code:
            return AppendOutcome("refused", code=code)
        return AppendOutcome.from_payload(self._call("es_append", {
            "p_org": org, "p_stream_type": stream_type, "p_stream_id": sid,
            "p_expected_version": int(expected_version), "p_events": [e.to_payload() for e in events],
        }))

    def load(self, org_id, stream_type, stream_id, *, from_version=1) -> LoadedStream:
        out = self._call("es_load", {"p_org": _uuid(org_id, "org_id"), "p_stream_type": stream_type,
                                     "p_stream_id": _uuid(stream_id, "stream_id"),
                                     "p_from_version": int(from_version)})
        return LoadedStream(int(out["version"]), tuple(StoredEvent.from_payload(e) for e in out["events"]))

    def read_all(self, after=Cursor(), *, limit=500, stream_types=None) -> ReadBatch:
        params: dict[str, Any] = {"p_after_tx": str(after.tx_id), "p_after_position": after.position, "p_limit": int(limit)}
        if stream_types is not None:
            params["p_stream_types"] = list(stream_types)
        out = self._call("es_read_all", params)
        return ReadBatch(tuple(StoredEvent.from_payload(e) for e in out["events"]), Cursor.from_payload(out["next"]))

    def stored_event_types(self) -> dict[tuple[str, int], int]:
        out = self._call("es_stored_event_types")
        return {(t["event_type"], int(t["schema_version"])): int(t["count"]) for t in out["types"]}

    def register_projection(self, name, *, handler, target, stream_types, mode="async") -> Optional[str]:
        if not isinstance(handler, str):
            return "invalid_handler"
        out = self._call("es_register_projection", {"p_projection": name, "p_handler": handler, "p_target": target,
                                                    "p_stream_types": list(stream_types), "p_mode": mode})
        return None if out.get("status") == "ok" else out.get("code")

    def run_projection(self, name, *, limit=500) -> ProjectionRun:
        return ProjectionRun.from_payload(self._call("es_run_projection", {"p_projection": name, "p_limit": int(limit)}))

    def rebuild_begin(self, name) -> Optional[str]:
        out = self._call("es_rebuild_begin", {"p_projection": name})
        return None if out.get("status") == "ok" else out.get("code")

    def rebuild_step(self, name, *, limit=1000) -> RebuildStep:
        out = self._call("es_rebuild_step", {"p_projection": name, "p_limit": int(limit)})
        if out.get("status") != "ok":
            return RebuildStep("refused", code=out.get("code"))
        return RebuildStep("ok", int(out["applied"]), bool(out["done"]), Cursor.from_payload(out["cursor"]))

    def rebuild_swap(self, name) -> RebuildOutcome:
        out = self._call("es_rebuild_swap", {"p_projection": name})
        if out.get("status") != "ok":
            return RebuildOutcome("refused", code=out.get("code"))
        return RebuildOutcome("ok", int(out["rows"]), Cursor.from_payload(out["cursor"]))


class RealSupabaseCheckpointStore(_Rpc):
    def get(self, projection) -> Checkpoint:
        c = self._call("es_checkpoint_get", {"p_projection": projection})["checkpoint"]
        return Checkpoint(projection, Cursor.from_payload(c), c.get("last_error"), c.get("updated_at"))

    def advance(self, projection, *, expected, to) -> Literal["ok", "conflict"]:
        _check_advance(expected, to)
        out = self._call("es_checkpoint_advance", {
            "p_projection": projection, "p_expected_tx": str(expected.tx_id), "p_expected_position": expected.position,
            "p_tx": str(to.tx_id), "p_position": to.position})
        if out.get("status") == "refused":
            raise ValueError(f"checkpoint advance refused: {out.get('code')}")
        return out["status"]

    def record_error(self, projection, error) -> None:
        self._call("es_checkpoint_error", {"p_projection": projection, "p_error": str(error)})

    def reset(self, projection, *, to=Cursor()) -> None:
        self._call("es_checkpoint_reset", {"p_projection": projection, "p_tx": str(to.tx_id), "p_position": to.position})


# -- Fake ---------------------------------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(v: Any) -> str:
    if v is None:
        return _now()
    return v.isoformat() if isinstance(v, datetime) else str(v)


class FakeEventStore:
    """In memory, thread-safe, every append committed at once (so every event is immediately settled).

    Read models are dicts in `self.tables` (create with `create_table`); checkpoints live in the store and are
    exposed through `FakeCheckpointStore(store)` -- the same state `run_projection` moves."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._streams: dict[tuple[str, str], dict] = {}
        self._events: list[StoredEvent] = []
        self._by_id: dict[str, StoredEvent] = {}
        self._tx = 1000
        self.tables: dict[str, dict] = {}
        self.projections: dict[str, dict] = {}
        self.checkpoints: dict[str, Checkpoint] = {}

    # read-model helpers (test + consumer setup)
    def create_table(self, name: str) -> dict:
        with self._lock:
            return self.tables.setdefault(name, {})

    def read_model(self, name: str) -> dict:
        with self._lock:
            return copy.deepcopy(self.tables[name])

    # -- writes --
    def append(self, org_id, stream_type, stream_id, events, *, expected_version=ANY_VERSION) -> AppendOutcome:
        if org_id is None or stream_id is None:
            return AppendOutcome("refused", code="invalid_stream")
        org, sid = _uuid(org_id, "org_id"), _uuid(stream_id, "stream_id")
        events = [e.with_id() if isinstance(e, NewEvent) else e for e in events]
        code = validate_events(stream_type, events)
        if code:
            return AppendOutcome("refused", code=code)
        if not isinstance(expected_version, int) or expected_version < -1:
            return AppendOutcome("refused", code="invalid_expected_version")
        with self._lock:
            stream = self._streams.get((stream_type, sid))
            if stream is not None and stream["org_id"] != org:
                return AppendOutcome("refused", code="org_mismatch")
            current = stream["version"] if stream else 0
            dupes = [self._by_id[e.event_id] for e in events if e.event_id in self._by_id]
            if dupes:
                same = [d for d, e in zip(dupes, events) if d.org_id == org and d.stream_type == stream_type
                        and d.stream_id == sid and d.event_type == e.event_type]
                if len(dupes) == len(events) and len(same) == len(events):
                    ordered = sorted(dupes, key=lambda d: d.version)
                    return AppendOutcome("replayed", version=ordered[-1].version,
                                         positions=tuple(d.global_position for d in ordered))
                return AppendOutcome("refused", code="idempotency_conflict")
            if expected_version != ANY_VERSION and expected_version != current:
                return AppendOutcome("conflict", current_version=current)
            self._tx += 1
            new = [
                StoredEvent(global_position=len(self._events) + i + 1, event_id=str(e.event_id), org_id=org,
                            stream_type=stream_type, stream_id=sid, version=current + i + 1, event_type=e.event_type,
                            schema_version=e.schema_version, data=copy.deepcopy(dict(e.data)),
                            metadata=copy.deepcopy(dict(e.metadata)), occurred_at=_iso(e.occurred_at),
                            recorded_at=_now(), tx_id=self._tx)
                for i, e in enumerate(events)
            ]
            # sync projections run "inside the transaction": on failure every touched table is restored
            hooks = sorted((n, p) for n, p in self.projections.items() if p["mode"] == "sync" and stream_type in p["stream_types"])
            saved = {p["target"]: copy.deepcopy(self.tables[p["target"]]) for _, p in hooks}
            for name, p in hooks:
                try:
                    p["handler"]([copy.deepcopy(e) for e in new], self.tables[p["target"]])
                except Exception as exc:  # noqa: BLE001 -- the hook's failure IS the outcome (projection_failed)
                    for target, rows in saved.items():
                        self.tables[target] = rows
                    return AppendOutcome("refused", code="projection_failed", detail=str(exc), projection=name)
            self._events.extend(new)
            for e in new:
                self._by_id[e.event_id] = e
            self._streams[(stream_type, sid)] = {"org_id": org, "version": current + len(new)}
            return AppendOutcome("ok", version=current + len(new), positions=tuple(e.global_position for e in new))

    # -- reads --
    def load(self, org_id, stream_type, stream_id, *, from_version=1) -> LoadedStream:
        org, sid = _uuid(org_id, "org_id"), _uuid(stream_id, "stream_id")
        with self._lock:
            stream = self._streams.get((stream_type, sid))
            if stream is None or stream["org_id"] != org:
                return LoadedStream(0, ())
            evs = tuple(copy.deepcopy(e) for e in self._events
                        if e.stream_type == stream_type and e.stream_id == sid and e.version >= (from_version or 1))
            return LoadedStream(stream["version"], evs)

    def _batch(self, after: Cursor, limit: int, stream_types: Optional[Sequence[str]]) -> ReadBatch:
        limit = max(1, min(int(limit), MAX_BATCH))
        evs = [e for e in sorted(self._events, key=lambda e: e.cursor)
               if e.cursor > after and (stream_types is None or e.stream_type in stream_types)][:limit]
        return ReadBatch(tuple(copy.deepcopy(e) for e in evs), evs[-1].cursor if evs else after)

    def read_all(self, after=Cursor(), *, limit=500, stream_types=None) -> ReadBatch:
        with self._lock:
            return self._batch(after, limit, stream_types)

    def stored_event_types(self) -> dict[tuple[str, int], int]:
        with self._lock:
            out: dict[tuple[str, int], int] = {}
            for e in self._events:
                out[(e.event_type, e.schema_version)] = out.get((e.event_type, e.schema_version), 0) + 1
            return out

    # -- projections --
    def register_projection(self, name, *, handler, target, stream_types, mode="async") -> Optional[str]:
        if not isinstance(name, str) or not _NAME_RE.match(name):
            return "invalid_projection"
        if mode not in PROJECTION_MODES:
            return "invalid_mode"
        if not stream_types or any(not isinstance(t, str) or not _NAME_RE.match(t) for t in stream_types):
            return "invalid_stream_types"
        if not callable(handler):
            return "invalid_handler"
        with self._lock:
            if target not in self.tables:
                return "invalid_target"
            self.projections[name] = {"handler": handler, "target": target, "stream_types": tuple(stream_types), "mode": mode}
            return None

    def _apply(self, p: dict, events: Sequence[StoredEvent], target: str) -> Optional[str]:
        saved = copy.deepcopy(self.tables[target])
        try:
            p["handler"]([copy.deepcopy(e) for e in events], self.tables[target])
        except Exception as exc:  # noqa: BLE001 -- returned as the run's error, read model restored
            self.tables[target] = saved
            return str(exc)
        return None

    def run_projection(self, name, *, limit=500) -> ProjectionRun:
        with self._lock:
            p = self.projections.get(name)
            if p is None:
                return ProjectionRun("refused", code="unknown_projection")
            if p["mode"] != "async":
                return ProjectionRun("refused", code="not_async")
            cp = self.checkpoints.get(name) or Checkpoint(name)
            batch = self._batch(cp.cursor, limit, p["stream_types"])
            if not batch.events:
                return ProjectionRun("idle", 0, cp.cursor)
            err = self._apply(p, batch.events, p["target"])
            if err is not None:
                self.checkpoints[name] = Checkpoint(name, cp.cursor, err, _now())
                return ProjectionRun("error", 0, cp.cursor, error=err)
            self.checkpoints[name] = Checkpoint(name, batch.next, None, _now())
            return ProjectionRun("ok", len(batch.events), batch.next)

    def _shadow(self, name: str) -> str:
        return f"{self.projections[name]['target']}__rebuild"

    def rebuild_begin(self, name) -> Optional[str]:
        with self._lock:
            if name not in self.projections:
                return "unknown_projection"
            self.tables[self._shadow(name)] = {}
            self.checkpoints[f"{name}#rebuild"] = Checkpoint(f"{name}#rebuild", Cursor(), None, _now())
            return None

    def rebuild_step(self, name, *, limit=1000) -> RebuildStep:
        with self._lock:
            p = self.projections.get(name)
            if p is None:
                return RebuildStep("refused", code="unknown_projection")
            key, shadow = f"{name}#rebuild", self._shadow(name)
            if key not in self.checkpoints or shadow not in self.tables:
                return RebuildStep("refused", code="not_rebuilding")
            limit = max(1, min(int(limit), MAX_BATCH))
            batch = self._batch(self.checkpoints[key].cursor, limit, p["stream_types"])
            if batch.events:
                p["handler"]([copy.deepcopy(e) for e in batch.events], self.tables[shadow])
                self.checkpoints[key] = Checkpoint(key, batch.next, None, _now())
            return RebuildStep("ok", len(batch.events), len(batch.events) < limit, batch.next)

    def rebuild_swap(self, name) -> RebuildOutcome:
        with self._lock:
            p = self.projections.get(name)
            if p is None:
                return RebuildOutcome("refused", code="unknown_projection")
            key, shadow = f"{name}#rebuild", self._shadow(name)
            if key not in self.checkpoints or shadow not in self.tables:
                return RebuildOutcome("refused", code="not_rebuilding")
            cursor = self.checkpoints[key].cursor
            while True:
                batch = self._batch(cursor, MAX_BATCH, p["stream_types"])
                if not batch.events:
                    break
                p["handler"]([copy.deepcopy(e) for e in batch.events], self.tables[shadow])
                cursor = batch.next
            self.tables[p["target"]] = self.tables.pop(shadow)
            del self.checkpoints[key]
            if p["mode"] == "async":
                self.checkpoints[name] = Checkpoint(name, cursor, None, _now())
            return RebuildOutcome("ok", len(self.tables[p["target"]]), cursor)


class FakeCheckpointStore:
    """Checkpoints of a `FakeEventStore` (the same ones `run_projection` moves)."""

    def __init__(self, store: Optional[FakeEventStore] = None) -> None:
        self._store = store or FakeEventStore()

    def get(self, projection) -> Checkpoint:
        with self._store._lock:
            return self._store.checkpoints.get(projection) or Checkpoint(projection)

    def advance(self, projection, *, expected, to) -> Literal["ok", "conflict"]:
        _check_advance(expected, to)
        with self._store._lock:
            cur = self.get(projection)
            if cur.cursor != expected:
                return "conflict"
            self._store.checkpoints[projection] = Checkpoint(projection, to, None, _now())
            return "ok"

    def record_error(self, projection, error) -> None:
        with self._store._lock:
            cur = self.get(projection)
            self._store.checkpoints[projection] = Checkpoint(projection, cur.cursor, str(error)[:2000], _now())

    def reset(self, projection, *, to=Cursor()) -> None:
        with self._store._lock:
            self._store.checkpoints[projection] = Checkpoint(projection, to, None, _now())


# -- factories ----------------------------------------------------------------------------------------------


def make_event_store(kind: Literal["supabase", "fake"] = "supabase", *, client: Any = None) -> EventStore:
    """`"supabase"` (needs `client`, the product's schema-scoped PostgREST client) or `"fake"`."""
    if kind == "supabase":
        return RealSupabaseEventStore(client)
    if kind == "fake":
        return FakeEventStore()
    raise ValueError(f"unknown event store kind {kind!r} (expected 'supabase' or 'fake')")


def make_checkpoint_store(kind: Literal["supabase", "fake"] = "supabase", *, client: Any = None,
                          store: Optional[FakeEventStore] = None) -> CheckpointStore:
    """`"supabase"` (needs `client`) or `"fake"` (pass the `FakeEventStore` whose checkpoints it shares)."""
    if kind == "supabase":
        return RealSupabaseCheckpointStore(client)
    if kind == "fake":
        return FakeCheckpointStore(store)
    raise ValueError(f"unknown checkpoint store kind {kind!r} (expected 'supabase' or 'fake')")


def new_stream_id() -> str:
    return str(uuid.uuid4())


__all__ = [
    "CheckpointStore",
    "EventStore",
    "FakeCheckpointStore",
    "FakeEventStore",
    "FakeHandler",
    "RealSupabaseCheckpointStore",
    "RealSupabaseEventStore",
    "make_checkpoint_store",
    "make_event_store",
    "new_stream_id",
]
