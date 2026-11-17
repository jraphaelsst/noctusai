"""Value types of the event store seam (inputs, stored events, outcomes, cursors)."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Mapping, Optional

from .config import EVENT_TYPE_PATTERN, METADATA_KEYS, NAME_PATTERN

_EVENT_TYPE_RE = re.compile(EVENT_TYPE_PATTERN)
_NAME_RE = re.compile(NAME_PATTERN)


@dataclass(frozen=True, order=True)
class Cursor:
    """A reader's position in the global log: `(tx_id, position)` of the last event it consumed.

    Ordered as a pair -- never by `position` alone (KB § PATTERNS/backend/event-store.md § read visibility)."""

    tx_id: int = 0
    position: int = 0

    @classmethod
    def from_payload(cls, payload: Any) -> "Cursor":
        if not isinstance(payload, Mapping):
            return cls()
        return cls(int(payload.get("tx_id") or 0), int(payload.get("position") or 0))


@dataclass(frozen=True)
class NewEvent:
    """One event to append. `event_id` is the idempotency key: pass a stable one (e.g. derived from the command)
    so a retried append answers `replayed` instead of appending twice; None = a fresh uuid4."""

    event_type: str
    data: Mapping[str, Any] = field(default_factory=dict)
    event_id: Optional[str] = None
    schema_version: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: Optional[datetime | str] = None

    def with_id(self) -> "NewEvent":
        if self.event_id:
            return self
        return NewEvent(self.event_type, self.data, str(uuid.uuid4()), self.schema_version, self.metadata, self.occurred_at)

    def to_payload(self) -> dict:
        out: dict[str, Any] = {"event_type": self.event_type, "data": dict(self.data), "schema_version": self.schema_version,
                               "metadata": dict(self.metadata)}
        if self.event_id:
            out["event_id"] = str(self.event_id)
        if self.occurred_at is not None:
            out["occurred_at"] = self.occurred_at.isoformat() if isinstance(self.occurred_at, datetime) else str(self.occurred_at)
        return out


@dataclass(frozen=True)
class StoredEvent:
    global_position: int
    event_id: str
    org_id: str
    stream_type: str
    stream_id: str
    version: int
    event_type: str
    schema_version: int
    data: dict
    metadata: dict
    occurred_at: str
    recorded_at: str
    tx_id: int

    @property
    def cursor(self) -> Cursor:
        return Cursor(self.tx_id, self.global_position)

    @classmethod
    def from_payload(cls, p: Mapping[str, Any]) -> "StoredEvent":
        return cls(
            global_position=int(p["global_position"]), event_id=str(p["event_id"]), org_id=str(p["org_id"]),
            stream_type=str(p["stream_type"]), stream_id=str(p["stream_id"]), version=int(p["version"]),
            event_type=str(p["event_type"]), schema_version=int(p.get("schema_version") or 1),
            data=dict(p.get("data") or {}), metadata=dict(p.get("metadata") or {}),
            occurred_at=str(p.get("occurred_at") or ""), recorded_at=str(p.get("recorded_at") or ""),
            tx_id=int(p.get("tx_id") or 0),
        )


AppendStatus = Literal["ok", "replayed", "conflict", "refused"]


@dataclass(frozen=True)
class AppendOutcome:
    """`ok` / `replayed` carry the stream `version` after the events and their global `positions`;
    `conflict` carries `current_version`; `refused` a stable `code` (+ `detail`, `projection`)."""

    status: AppendStatus
    version: Optional[int] = None
    positions: tuple[int, ...] = ()
    current_version: Optional[int] = None
    code: Optional[str] = None
    detail: Optional[str] = None
    projection: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "replayed")

    @classmethod
    def from_payload(cls, p: Any) -> "AppendOutcome":
        if not isinstance(p, Mapping) or p.get("status") not in ("ok", "replayed", "conflict", "refused"):
            raise RuntimeError(f"es_append answered an unknown shape: {p!r}")
        return cls(
            status=p["status"], version=p.get("version"), positions=tuple(int(x) for x in (p.get("positions") or ())),
            current_version=p.get("current_version"), code=p.get("code"), detail=p.get("detail"),
            projection=p.get("projection"),
        )


@dataclass(frozen=True)
class LoadedStream:
    version: int
    events: tuple[StoredEvent, ...]


@dataclass(frozen=True)
class ReadBatch:
    events: tuple[StoredEvent, ...]
    next: Cursor


ProjectionStatus = Literal["ok", "idle", "busy", "error", "refused"]


@dataclass(frozen=True)
class ProjectionRun:
    status: ProjectionStatus
    applied: int = 0
    cursor: Cursor = Cursor()
    error: Optional[str] = None
    code: Optional[str] = None

    @classmethod
    def from_payload(cls, p: Mapping[str, Any]) -> "ProjectionRun":
        return cls(status=p["status"], applied=int(p.get("applied") or 0), cursor=Cursor.from_payload(p.get("cursor")),
                   error=p.get("error"), code=p.get("code"))


@dataclass(frozen=True)
class RebuildStep:
    status: Literal["ok", "refused"]
    applied: int = 0
    done: bool = False
    cursor: Cursor = Cursor()
    code: Optional[str] = None


@dataclass(frozen=True)
class RebuildOutcome:
    status: Literal["ok", "refused"]
    rows: int = 0
    cursor: Cursor = Cursor()
    steps: int = 0
    code: Optional[str] = None


@dataclass(frozen=True)
class Checkpoint:
    projection: str
    cursor: Cursor = Cursor()
    last_error: Optional[str] = None
    updated_at: Optional[str] = None


def validate_events(stream_type: str, events: Any) -> Optional[str]:
    """The caller-input refusal code for an append (None = valid); the SQL refuses the same inputs the same way."""
    if not isinstance(stream_type, str) or not _NAME_RE.match(stream_type):
        return "invalid_stream_type"
    if not events:
        return "empty"
    for ev in events:
        if not isinstance(ev, NewEvent) or not isinstance(ev.event_type, str) or not _EVENT_TYPE_RE.match(ev.event_type):
            return "invalid_event_type"
        if not isinstance(ev.data, Mapping):
            return "invalid_data"
        if not isinstance(ev.metadata, Mapping) or set(ev.metadata) - set(METADATA_KEYS):
            return "invalid_metadata"
        if isinstance(ev.schema_version, bool) or not isinstance(ev.schema_version, int) or ev.schema_version < 1:
            return "invalid_schema_version"
    ids = [str(e.event_id) for e in events if e.event_id]
    if len(ids) != len(set(ids)):
        return "duplicate_event_id"
    return None


__all__ = [
    "AppendOutcome",
    "Checkpoint",
    "Cursor",
    "LoadedStream",
    "NewEvent",
    "ProjectionRun",
    "ReadBatch",
    "RebuildOutcome",
    "RebuildStep",
    "StoredEvent",
    "validate_events",
]
