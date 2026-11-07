"""`TransitionLog` -- the Python seam over one aggregate's transition log.

Protocol + Fake + Real + factory (CLAUDE.md §1 seed IO rule):

- `SupabaseTransitionLog(client, cfg)` -- the real one: the row-locked RPCs `transition_log_migration` renders,
  called over a schema-scoped PostgREST client (`client.rpc(name, params).execute()`);
- `FakeTransitionLog(cfg)` -- in memory with the SAME semantics (compare-and-set, idempotent replay, seq,
  lazy synthetic first event, gated erasure, refusal codes); consumers' tests run against it;
- `make_transition_log(kind, cfg=..., client=...)` -- the factory.

Both run ONE conformance suite (`tests/domain/transition_log/conformance.py`), the Real on a real Postgres.
A refusal is DATA (`TransitionOutcome.status == "refused"` + a stable `code`), never an exception -- the
inventory convention; a malformed key is a caller bug and raises `ValueError` before any IO, in both.

Refusal codes: `not_found` · `stale_state` (+ `current_state`) · `idempotency_conflict` · `history_exists` ·
`duplicate` · `invalid_row` · `invalid_key` · `invalid_data` · `invalid_actor_kind` · `invalid_event_type` ·
`reserved_event_type` · `invalid_reason`.
"""
from __future__ import annotations

import copy
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

from .config import (
    CREATED_EVENT,
    DEFAULT_EVENT_TYPE,
    EVENT_TYPE_PATTERN,
    IMPORTED_INITIAL_EVENT,
    SYNTHETIC_ACTOR_KIND,
    TransitionLogConfig,
    normalize_key,
    normalize_subject,
)

Status = Literal["ok", "replayed", "refused"]
_EVENT_TYPE_RE = re.compile(EVENT_TYPE_PATTERN)


@dataclass(frozen=True)
class TransitionOutcome:
    """What every write answers: `ok` / `replayed` carry the event; `refused` carries a stable `code`."""

    status: Status
    event: Optional[dict] = None
    code: Optional[str] = None
    current_state: Any = None
    detail: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "replayed")

    @classmethod
    def from_payload(cls, payload: Any) -> "TransitionOutcome":
        if not isinstance(payload, Mapping) or payload.get("status") not in ("ok", "replayed", "refused"):
            raise RuntimeError(f"transition log RPC answered an unexpected payload: {payload!r}")
        return cls(
            status=payload["status"], event=payload.get("event"), code=payload.get("code"),
            current_state=payload.get("current_state"), detail=payload.get("detail"),
        )


@dataclass(frozen=True)
class ErasureOutcome:
    status: Literal["ok", "refused"]
    deleted: int = 0
    code: Optional[str] = None


@runtime_checkable
class TransitionLog(Protocol):
    cfg: TransitionLogConfig

    def create(self, org_id: str, row: Mapping[str, Any], *, data: Optional[Mapping] = None, actor_id: Optional[str] = None,
               actor_kind: str = "user", correlation_id: Optional[str] = None, event_id: Optional[str] = None,
               occurred_at: Any = None) -> TransitionOutcome:
        """Insert the state row AND its seq-1 `created` event atomically. Idempotent on `event_id`."""
        ...

    def record_created(self, org_id: str, key: Any, *, data: Optional[Mapping] = None, actor_id: Optional[str] = None,
                       actor_kind: str = "user", correlation_id: Optional[str] = None, event_id: Optional[str] = None,
                       occurred_at: Any = None) -> TransitionOutcome:
        """Seq-1 `created` for a state row inserted elsewhere (refused `history_exists` when it already has events)."""
        ...

    def transition(self, org_id: str, key: Any, *, from_state: Any, to_state: Any, event_type: str = DEFAULT_EVENT_TYPE,
                   data: Optional[Mapping] = None, actor_id: Optional[str] = None, actor_kind: str = "user",
                   correlation_id: Optional[str] = None, event_id: Optional[str] = None,
                   occurred_at: Any = None) -> TransitionOutcome:
        """Compare-and-set `from_state` -> `to_state` and append the next event, under the state row's lock."""
        ...

    def history(self, org_id: str, key: Any) -> list[dict]:
        """The entity's events, oldest first (seq order)."""
        ...

    def erase_subject(self, org_id: str, subject: Any, *, reason: str, actor_id: Optional[str] = None) -> ErasureOutcome:
        """LGPD erasure: delete the subject's events (a non-empty subset of the key) through the ONE gated path."""
        ...

    def backfill_initial_state(self, org_id: Optional[str] = None) -> int:
        """One synthetic `imported_initial_state` per entity without history; returns how many were written."""
        ...


def _jsonable(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, Mapping):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def _opt(v: Any) -> Any:
    return None if v is None else _jsonable(v)


class SupabaseTransitionLog:
    """The real one: one RPC call per operation, over a schema-scoped PostgREST client."""

    def __init__(self, client: Any, cfg: TransitionLogConfig) -> None:
        if client is None:
            raise ValueError("SupabaseTransitionLog needs a schema-scoped client")
        self.client = client
        self.cfg = cfg

    def _call(self, name: str, params: dict) -> Any:
        return self.client.rpc(self.cfg.rpc(name), params).execute().data

    def _event_params(self, data, actor_id, actor_kind, correlation_id, event_id, occurred_at) -> dict:
        return {
            "p_data": {} if data is None else _jsonable(data), "p_actor_id": _opt(actor_id), "p_actor_kind": actor_kind,
            "p_correlation_id": _opt(correlation_id), "p_event_id": _opt(event_id), "p_occurred_at": _opt(occurred_at),
        }

    def create(self, org_id, row, *, data=None, actor_id=None, actor_kind="user", correlation_id=None, event_id=None,
               occurred_at=None) -> TransitionOutcome:
        params = {"p_org": str(org_id), "p_row": _jsonable(dict(row)),
                  **self._event_params(data, actor_id, actor_kind, correlation_id, event_id, occurred_at)}
        return TransitionOutcome.from_payload(self._call("create", params))

    def record_created(self, org_id, key, *, data=None, actor_id=None, actor_kind="user", correlation_id=None,
                       event_id=None, occurred_at=None) -> TransitionOutcome:
        params = {"p_org": str(org_id), "p_key": normalize_key(self.cfg, key),
                  **self._event_params(data, actor_id, actor_kind, correlation_id, event_id, occurred_at)}
        return TransitionOutcome.from_payload(self._call("record_created", params))

    def transition(self, org_id, key, *, from_state, to_state, event_type=DEFAULT_EVENT_TYPE, data=None, actor_id=None,
                   actor_kind="user", correlation_id=None, event_id=None, occurred_at=None) -> TransitionOutcome:
        params = {"p_org": str(org_id), "p_key": normalize_key(self.cfg, key), "p_from": _opt(from_state),
                  "p_to": _opt(to_state), "p_event_type": event_type,
                  **self._event_params(data, actor_id, actor_kind, correlation_id, event_id, occurred_at)}
        return TransitionOutcome.from_payload(self._call("transition", params))

    def history(self, org_id, key) -> list[dict]:
        payload = self._call("history", {"p_org": str(org_id), "p_key": normalize_key(self.cfg, key)})
        if not isinstance(payload, Mapping) or payload.get("status") != "ok":
            raise RuntimeError(f"{self.cfg.rpc('history')} answered {payload!r}")
        return list(payload.get("events") or [])

    def erase_subject(self, org_id, subject, *, reason, actor_id=None) -> ErasureOutcome:
        payload = self._call("erase_subject", {"p_org": str(org_id), "p_subject": normalize_subject(self.cfg, subject),
                                               "p_reason": reason, "p_actor_id": _opt(actor_id)})
        if not isinstance(payload, Mapping) or payload.get("status") not in ("ok", "refused"):
            raise RuntimeError(f"{self.cfg.rpc('erase_subject')} answered {payload!r}")
        return ErasureOutcome(status=payload["status"], deleted=int(payload.get("deleted") or 0), code=payload.get("code"))

    def backfill_initial_state(self, org_id=None) -> int:
        n = self._call("backfill_initial_state", {"p_org": _opt(org_id)})
        if not isinstance(n, int):
            raise RuntimeError(f"{self.cfg.rpc('backfill_initial_state')} answered {n!r}")
        return n


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _State:
    org_id: str
    row: dict


class FakeTransitionLog:
    """In memory, full parity with the SQL (one `RLock` stands in for `SELECT ... FOR UPDATE`).

    `state_columns` (optional) is the state table's column set: `create` refuses `invalid_row` for any other
    key, exactly as the dynamic INSERT does. `state_defaults` fills omitted columns the way the table's
    DEFAULTs would. A single-column `uuid` key whose state column is omitted is generated (the
    `DEFAULT gen_random_uuid()` every state table carries on its id).
    """

    def __init__(self, cfg: TransitionLogConfig, *, state_columns: Optional[Sequence[str]] = None,
                 state_defaults: Optional[Mapping[str, Any]] = None) -> None:
        self.cfg = cfg
        self.state_columns = set(state_columns) if state_columns is not None else None
        self.state_defaults = dict(state_defaults or {})
        self._lock = threading.RLock()
        self._states: dict[tuple, _State] = {}
        self._events: list[dict] = []
        self.erasures: list[dict] = []

    # -- seams for tests / consumers ------------------------------------------------------------------------
    def put_state_row(self, org_id: str, row: Mapping[str, Any]) -> dict:
        """A state row inserted OUTSIDE the log (a legacy entity, or the product's own SQL): no event written."""
        with self._lock:
            full = {**self.state_defaults, **dict(row), self.cfg.state_org_column: str(org_id)}
            self._fill_generated_key(full)
            k = self._state_key(full)
            if k in self._states:
                raise ValueError(f"duplicate state row {k}")
            self._states[k] = _State(str(org_id), full)
            return dict(full)

    def state_row(self, org_id: str, key: Any) -> Optional[dict]:
        k = tuple(normalize_key(self.cfg, key)[n] for n in self.cfg.key_names)
        st = self._states.get(k)
        return dict(st.row) if st and st.org_id == str(org_id) else None

    # -- helpers ----------------------------------------------------------------------------------------------
    def _fill_generated_key(self, row: dict) -> None:
        if len(self.cfg.key) == 1 and self.cfg.key[0].type == "uuid" and row.get(self.cfg.key[0].state_column) is None:
            row[self.cfg.key[0].state_column] = str(uuid.uuid4())

    def _state_key(self, row: Mapping) -> tuple:
        return tuple(_jsonable(row.get(k.state_column)) for k in self.cfg.key)

    def _events_of(self, key: Mapping) -> list[dict]:
        return sorted((e for e in self._events if all(e[n] == key[n] for n in self.cfg.key_names)), key=lambda e: e["seq"])

    def _event(self, org_id, key, seq, from_state, to_state, event_type, data, actor_id, actor_kind, correlation_id,
               event_id, occurred_at) -> dict:
        now = _now()
        ev = {"id": str(event_id or uuid.uuid4()), "org_id": str(org_id), **key, "seq": seq, "from_state": from_state,
              "to_state": to_state, "event_type": event_type, "data": copy.deepcopy(data), "actor_id": _opt(actor_id),
              "actor_kind": actor_kind, "correlation_id": _opt(correlation_id),
              "occurred_at": _opt(occurred_at) or now, "recorded_at": now}
        ordered = {c: ev[c] for c in self.cfg.event_columns}
        self._events.append(ordered)
        return copy.deepcopy(ordered)

    def _validate(self, data, actor_kind) -> Optional[TransitionOutcome]:
        if data is not None and not isinstance(data, Mapping):
            return TransitionOutcome("refused", code="invalid_data")
        if actor_kind not in self.cfg.actor_kinds:
            return TransitionOutcome("refused", code="invalid_actor_kind")
        return None

    def _by_id(self, event_id) -> Optional[dict]:
        if event_id is None:
            return None
        return next((e for e in self._events if e["id"] == str(event_id)), None)

    def _locked_state(self, org_id, key) -> Optional[_State]:
        st = self._states.get(tuple(key[n] for n in self.cfg.key_names))
        return st if st and st.org_id == str(org_id) else None

    # -- the protocol -----------------------------------------------------------------------------------------
    def create(self, org_id, row, *, data=None, actor_id=None, actor_kind="user", correlation_id=None, event_id=None,
               occurred_at=None) -> TransitionOutcome:
        if not isinstance(row, Mapping):
            return TransitionOutcome("refused", code="invalid_row")
        bad = self._validate(data, actor_kind)
        if bad:
            return bad
        with self._lock:
            prev = self._by_id(event_id)
            if prev is not None:
                if prev["org_id"] == str(org_id) and prev["event_type"] == CREATED_EVENT:
                    return TransitionOutcome("replayed", event=copy.deepcopy(prev))
                return TransitionOutcome("refused", code="idempotency_conflict")
            full = {**self.state_defaults, **_jsonable(dict(row)), self.cfg.state_org_column: str(org_id)}
            if self.state_columns is not None and set(full) - self.state_columns:
                return TransitionOutcome("refused", code="invalid_row")
            self._fill_generated_key(full)
            if any(full.get(k.state_column) is None for k in self.cfg.key) or full.get(self.cfg.state_column) is None:
                return TransitionOutcome("refused", code="invalid_row")
            k = self._state_key(full)
            if k in self._states:
                return TransitionOutcome("refused", code="duplicate")
            self._states[k] = _State(str(org_id), full)
            key = {kc.name: full[kc.state_column] for kc in self.cfg.key}
            ev = self._event(org_id, key, 1, None, full[self.cfg.state_column], CREATED_EVENT, dict(data or {}),
                             actor_id, actor_kind, correlation_id, event_id, occurred_at)
            return TransitionOutcome("ok", event=ev)

    def record_created(self, org_id, key, *, data=None, actor_id=None, actor_kind="user", correlation_id=None,
                       event_id=None, occurred_at=None) -> TransitionOutcome:
        key = normalize_key(self.cfg, key)
        bad = self._validate(data, actor_kind)
        if bad:
            return bad
        with self._lock:
            st = self._locked_state(org_id, key)
            if st is None:
                return TransitionOutcome("refused", code="not_found")
            prev = self._by_id(event_id)
            if prev is not None:
                same = prev["org_id"] == str(org_id) and all(prev[n] == key[n] for n in key) and prev["event_type"] == CREATED_EVENT
                return TransitionOutcome("replayed", event=copy.deepcopy(prev)) if same else TransitionOutcome("refused", code="idempotency_conflict")
            if self._events_of(key):
                return TransitionOutcome("refused", code="history_exists")
            ev = self._event(org_id, key, 1, None, st.row[self.cfg.state_column], CREATED_EVENT, dict(data or {}),
                             actor_id, actor_kind, correlation_id, event_id, occurred_at)
            return TransitionOutcome("ok", event=ev)

    def transition(self, org_id, key, *, from_state, to_state, event_type=DEFAULT_EVENT_TYPE, data=None, actor_id=None,
                   actor_kind="user", correlation_id=None, event_id=None, occurred_at=None) -> TransitionOutcome:
        key = normalize_key(self.cfg, key)
        bad = self._validate(data, actor_kind)
        if bad:
            return bad
        if not isinstance(event_type, str) or not _EVENT_TYPE_RE.match(event_type):
            return TransitionOutcome("refused", code="invalid_event_type")
        if event_type in (CREATED_EVENT, IMPORTED_INITIAL_EVENT):
            return TransitionOutcome("refused", code="reserved_event_type")
        from_state, to_state = _opt(from_state), _opt(to_state)
        with self._lock:
            st = self._locked_state(org_id, key)
            if st is None:
                return TransitionOutcome("refused", code="not_found")
            prev = self._by_id(event_id)
            if prev is not None:
                same = (prev["org_id"] == str(org_id) and all(prev[n] == key[n] for n in key)
                        and prev["event_type"] == event_type and prev["to_state"] == to_state)
                return TransitionOutcome("replayed", event=copy.deepcopy(prev)) if same else TransitionOutcome("refused", code="idempotency_conflict")
            cur = st.row[self.cfg.state_column]
            if cur != from_state:
                return TransitionOutcome("refused", code="stale_state", current_state=cur)
            seq = len(self._events_of(key))
            if seq == 0:
                created = st.row.get(self.cfg.state_created_at_column) if self.cfg.state_created_at_column else None
                self._event(org_id, key, 1, None, cur, IMPORTED_INITIAL_EVENT,
                            {"synthetic": True, "source": "lazy_first_transition"}, None, SYNTHETIC_ACTOR_KIND,
                            correlation_id, None, created)
                seq = 1
            st.row[self.cfg.state_column] = to_state
            if self.cfg.state_updated_at_column:
                st.row[self.cfg.state_updated_at_column] = _now()
            ev = self._event(org_id, key, seq + 1, cur, to_state, event_type, dict(data or {}), actor_id, actor_kind,
                             correlation_id, event_id, occurred_at)
            return TransitionOutcome("ok", event=ev)

    def history(self, org_id, key) -> list[dict]:
        key = normalize_key(self.cfg, key)
        with self._lock:
            return [copy.deepcopy(e) for e in self._events_of(key) if e["org_id"] == str(org_id)]

    def erase_subject(self, org_id, subject, *, reason, actor_id=None) -> ErasureOutcome:
        subject = normalize_subject(self.cfg, subject)
        if not isinstance(reason, str) or not reason.strip():
            return ErasureOutcome("refused", code="invalid_reason")
        with self._lock:
            keep, gone = [], 0
            for e in self._events:
                if e["org_id"] == str(org_id) and all(e[n] == v for n, v in subject.items()):
                    gone += 1
                else:
                    keep.append(e)
            self._events = keep
            self.erasures.append({"org_id": str(org_id), "aggregate": self.cfg.aggregate, "subject": dict(subject),
                                  "events_deleted": gone, "reason": reason, "actor_id": _opt(actor_id), "erased_at": _now()})
            return ErasureOutcome("ok", deleted=gone)

    def backfill_initial_state(self, org_id=None) -> int:
        n = 0
        with self._lock:
            for k, st in self._states.items():
                if org_id is not None and st.org_id != str(org_id):
                    continue
                key = dict(zip(self.cfg.key_names, k))
                if self._events_of(key):
                    continue
                created = st.row.get(self.cfg.state_created_at_column) if self.cfg.state_created_at_column else None
                self._event(st.org_id, key, 1, None, st.row[self.cfg.state_column], IMPORTED_INITIAL_EVENT,
                            {"synthetic": True, "source": "transition_log_backfill"}, None, SYNTHETIC_ACTOR_KIND,
                            None, None, created)
                n += 1
        return n


def make_transition_log(kind: Literal["supabase", "fake"] = "supabase", *, cfg: TransitionLogConfig,
                        client: Any = None, **fake_kwargs: Any) -> TransitionLog:
    """The factory: `"supabase"` (needs `client`, the product's schema-scoped PostgREST client) or `"fake"`."""
    if kind == "supabase":
        return SupabaseTransitionLog(client, cfg)
    if kind == "fake":
        return FakeTransitionLog(cfg, **fake_kwargs)
    raise ValueError(f"unknown transition log kind {kind!r} (expected 'supabase' or 'fake')")


__all__ = [
    "ErasureOutcome",
    "FakeTransitionLog",
    "SupabaseTransitionLog",
    "TransitionLog",
    "TransitionOutcome",
    "make_transition_log",
]
