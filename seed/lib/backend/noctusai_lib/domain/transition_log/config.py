"""`TransitionLogConfig` -- everything that differs between two transition-log aggregates.

One config = one aggregate in one product schema: the STATE table that holds the current state (the truth),
the column carrying the state, and the entity key the events are keyed by. The events table, its guard and
its RPCs are all derived from it (`<aggregate>_events`, `<aggregate>_transition`, ...).

Composite entity keys (2026-11-07 decision): the key is a tuple of :class:`KeyColumn`. A single-column key
defaults to ``entity_id uuid`` mapped to the state table's ``id``. A composite key (agents keys a thread
participant on ``(thread_id, agent_id)``) renders those REAL columns on the events table -- no synthetic
hashed id: the key stays queryable, joinable and FK-able, ``UNIQUE(<key...>, seq)`` and the
``(org_id, <key...>, seq)`` index are just wider. Python passes a key as a mapping ``{column: value}``
(a bare scalar is accepted for a single-column key).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

#: Column types a key / state column may have (cast targets in the rendered SQL).
SQL_TYPES: tuple[str, ...] = ("uuid", "text", "bigint", "integer")

#: Actor kinds a CALLER may record. `synthetic` is reserved for events the primitive fabricates itself
#: (backfill / the lazy first event) and is refused from callers.
DEFAULT_ACTOR_KINDS: tuple[str, ...] = ("user", "agent", "system", "integration")
SYNTHETIC_ACTOR_KIND = "synthetic"

#: Event types only the primitive writes (always seq 1, from_state NULL).
CREATED_EVENT = "created"
IMPORTED_INITIAL_EVENT = "imported_initial_state"
CREATION_EVENT_TYPES: tuple[str, ...] = (CREATED_EVENT, IMPORTED_INITIAL_EVENT)
DEFAULT_EVENT_TYPE = "transitioned"
EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9_.]*$"

#: Longest events-table name: leaves room for the derived object names (`guard_<t>_append_only` = +18) under
#: Postgres' 63-byte identifier limit.
MAX_EVENTS_TABLE_LEN = 40


def _ident(value: Any, what: str) -> str:
    if not isinstance(value, str) or not _IDENT.match(value):
        raise ValueError(f"TransitionLogConfig.{what} must be a bare lowercase identifier, got {value!r}")
    return value


@dataclass(frozen=True)
class KeyColumn:
    """One column of the entity key.

    Attributes:
        name: the column name on the EVENTS table (and the key in the Python mapping / RPC `p_key`).
        type: one of :data:`SQL_TYPES`.
        state_column: the matching column on the STATE table (default: same name).
    """

    name: str
    type: str = "uuid"
    state_column: Optional[str] = None

    def __post_init__(self) -> None:
        _ident(self.name, "key.name")
        if self.type not in SQL_TYPES:
            raise ValueError(f"KeyColumn.type must be one of {SQL_TYPES}, got {self.type!r}")
        if self.state_column is None:
            object.__setattr__(self, "state_column", self.name)
        _ident(self.state_column, "key.state_column")


@dataclass(frozen=True)
class TransitionLogConfig:
    """One aggregate's transition log.

    Attributes:
        schema: the product's Postgres schema.
        aggregate: names every derived object (`<aggregate>_events`, `<aggregate>_transition`, ...).
        state_table: the table holding the current state (the truth; the log explains it).
        state_column: the column of `state_table` carrying the state.
        state_type: SQL type of the state (one of :data:`SQL_TYPES`).
        key: the entity key (default `entity_id uuid` -> state `id`).
        state_org_column: the state table's org column.
        state_updated_at_column: bumped by a transition (None = none).
        state_created_at_column: `occurred_at` of a synthetic first event (None = `now()`).
        foreign_key: emit `<key...> -> state_table(<state cols>)` (DEFERRABLE INITIALLY IMMEDIATE, NO ACTION:
            never ON DELETE CASCADE -- deleting a state row with history goes through `erase_subject` first).
        actor_kinds: what callers may record (`synthetic` is always reserved for the primitive).
        org_id_expr: kept for parity with the organs (the events table is service-role only, `tier:org`).
    """

    schema: str
    aggregate: str
    state_table: str
    state_column: str
    state_type: str = "text"
    key: tuple[KeyColumn, ...] = field(default_factory=lambda: (KeyColumn("entity_id", "uuid", "id"),))
    state_org_column: str = "org_id"
    state_updated_at_column: Optional[str] = "updated_at"
    state_created_at_column: Optional[str] = "created_at"
    foreign_key: bool = True
    actor_kinds: tuple[str, ...] = DEFAULT_ACTOR_KINDS

    def __post_init__(self) -> None:
        for label in ("schema", "aggregate", "state_table", "state_column", "state_org_column"):
            _ident(getattr(self, label), label)
        for label in ("state_updated_at_column", "state_created_at_column"):
            if getattr(self, label) is not None:
                _ident(getattr(self, label), label)
        if self.state_type not in SQL_TYPES:
            raise ValueError(f"TransitionLogConfig.state_type must be one of {SQL_TYPES}, got {self.state_type!r}")
        key = tuple(k if isinstance(k, KeyColumn) else KeyColumn(**k) for k in self.key)
        if not key:
            raise ValueError("TransitionLogConfig.key needs at least one KeyColumn")
        names = [k.name for k in key]
        reserved = set(EVENT_COLUMNS_FIXED)
        if len(set(names)) != len(names) or reserved & set(names):
            raise ValueError(f"TransitionLogConfig.key names must be unique and not clash with {sorted(reserved)}")
        object.__setattr__(self, "key", key)
        kinds = tuple(self.actor_kinds)
        if not kinds or SYNTHETIC_ACTOR_KIND in kinds:
            raise ValueError(f"TransitionLogConfig.actor_kinds must be non-empty and must not contain {SYNTHETIC_ACTOR_KIND!r}")
        for k in kinds:
            _ident(k, "actor_kinds[]")
        object.__setattr__(self, "actor_kinds", kinds)
        if len(self.events_table) > MAX_EVENTS_TABLE_LEN:
            raise ValueError(f"events table {self.events_table!r} exceeds {MAX_EVENTS_TABLE_LEN} chars (derived names would overflow)")

    # -- derived names ---------------------------------------------------------------------------------------
    @property
    def events_table(self) -> str:
        return f"{self.aggregate}_events"

    def rpc(self, name: str) -> str:
        """`<aggregate>_<name>` (`transition`, `create`, `record_created`, `history`, `erase_subject`, ...)."""
        return f"{self.aggregate}_{name}"

    @property
    def erase_guc(self) -> str:
        """The transaction-local flag the erasure function sets (one per aggregate: unlocking A never unlocks B)."""
        return f"noctus_tl.erase_{self.aggregate}"

    @property
    def key_names(self) -> tuple[str, ...]:
        return tuple(k.name for k in self.key)

    @property
    def event_columns(self) -> tuple[str, ...]:
        """Every column of the events table, in table order (the keys of an event dict, Fake and Real alike)."""
        return ("id", "org_id", *self.key_names, *EVENT_COLUMNS_FIXED[2:])

    @property
    def all_actor_kinds(self) -> tuple[str, ...]:
        return (*self.actor_kinds, SYNTHETIC_ACTOR_KIND)

    # -- the marker a rendered migration carries (verify_db_guards + the keepers re-derive the config from it) --
    def to_marker_json(self) -> str:
        d = asdict(self)
        d["key"] = [asdict(k) for k in self.key]
        d["actor_kinds"] = list(self.actor_kinds)
        return json.dumps(d, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_marker_json(cls, text: str) -> "TransitionLogConfig":
        d: Mapping[str, Any] = json.loads(text)
        data = dict(d)
        data["key"] = tuple(KeyColumn(**k) for k in data.get("key", ()))
        data["actor_kinds"] = tuple(data.get("actor_kinds", DEFAULT_ACTOR_KINDS))
        return cls(**data)


#: Events-table columns that are the same for every aggregate. `id`/`org_id` lead, the key columns follow,
#: then these (the slice [2:]).
EVENT_COLUMNS_FIXED: tuple[str, ...] = (
    "id",
    "org_id",
    "seq",
    "from_state",
    "to_state",
    "event_type",
    "data",
    "actor_id",
    "actor_kind",
    "correlation_id",
    "occurred_at",
    "recorded_at",
)


def normalize_key(cfg: TransitionLogConfig, key: Any) -> dict[str, Any]:
    """A FULL entity key as `{column: value}` (a scalar is accepted for a single-column key). ValueError otherwise."""
    if not isinstance(key, Mapping):
        if len(cfg.key) != 1:
            raise ValueError(f"{cfg.aggregate}: composite key {cfg.key_names} must be passed as a mapping")
        key = {cfg.key[0].name: key}
    unknown = set(key) - set(cfg.key_names)
    missing = [n for n in cfg.key_names if key.get(n) in (None, "")]
    if unknown or missing:
        raise ValueError(f"{cfg.aggregate}: key must carry exactly {cfg.key_names} (unknown={sorted(unknown)}, missing={missing})")
    return {n: _scalar(key[n]) for n in cfg.key_names}


def normalize_subject(cfg: TransitionLogConfig, subject: Any) -> dict[str, Any]:
    """An ERASURE subject: a non-empty SUBSET of the key columns (e.g. `{thread_id}` erases every participant
    of the thread). ValueError on an empty or unknown subset."""
    if not isinstance(subject, Mapping):
        return normalize_key(cfg, subject)
    unknown = set(subject) - set(cfg.key_names)
    present = {n: subject[n] for n in cfg.key_names if subject.get(n) not in (None, "")}
    if unknown or not present:
        raise ValueError(f"{cfg.aggregate}: erasure subject must be a non-empty subset of {cfg.key_names} (unknown={sorted(unknown)})")
    return {n: _scalar(v) for n, v in present.items()}


def _scalar(v: Any) -> Any:
    return v if isinstance(v, (str, int)) else str(v)


__all__ = [
    "CREATED_EVENT",
    "CREATION_EVENT_TYPES",
    "DEFAULT_ACTOR_KINDS",
    "DEFAULT_EVENT_TYPE",
    "EVENT_COLUMNS_FIXED",
    "EVENT_TYPE_PATTERN",
    "IMPORTED_INITIAL_EVENT",
    "KeyColumn",
    "SQL_TYPES",
    "SYNTHETIC_ACTOR_KIND",
    "TransitionLogConfig",
    "normalize_key",
    "normalize_subject",
]
