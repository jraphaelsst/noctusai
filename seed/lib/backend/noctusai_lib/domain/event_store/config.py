"""`EventStoreConfig` + the event store's fixed vocabulary (names, patterns, reserved values).

One event store per product schema (the organ convention: `event_store_migration(EventStoreConfig(schema=...))`).
Table names are fixed (`es_streams`, `es_events`, `es_checkpoints`, `es_projections`) so tooling
(`verify_db_guards`, `noctus.dev.projection_rebuild`) never needs a per-product config.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

#: `stream_type` / projection names: a stable machine name.
NAME_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"
#: `event_type`: snake_case segments, optionally dotted (`subscription.renewed`). Never free text.
EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"
#: The ONLY metadata keys an event may carry (ids + provenance -- never personal data, see the LGPD rule).
METADATA_KEYS: tuple[str, ...] = ("causation_id", "correlation_id", "actor_id", "actor_kind", "source")
#: `expected_version` meaning "append whatever the current version is".
ANY_VERSION = -1
#: Refusal SQLSTATE of the append-only guards.
APPEND_ONLY_SQLSTATE = "ES001"
#: Internal SQLSTATE es_append raises to roll its own subtransaction back before answering a non-ok outcome.
OUTCOME_SQLSTATE = "ES409"
#: Projection modes: `sync` runs inside `es_append`'s transaction; `async` runs from its checkpoint.
PROJECTION_MODES: tuple[str, ...] = ("sync", "async")
#: Suffix of the rebuild's shadow table and of its private checkpoint row.
REBUILD_SUFFIX = "__rebuild"
REBUILD_CHECKPOINT_SUFFIX = "#rebuild"

_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


@dataclass(frozen=True)
class EventStoreConfig:
    schema: str

    def __post_init__(self) -> None:
        if not _IDENT_RE.match(self.schema or ""):
            raise ValueError(f"invalid schema {self.schema!r}")

    @property
    def append_guc(self) -> str:
        """Transaction-local flag `es_append` alone sets around its writes to `es_streams` / `es_events`
        (one per schema: another schema's store never opens this one)."""
        return f"noctus_es.append_{self.schema}"


__all__ = [
    "ANY_VERSION",
    "APPEND_ONLY_SQLSTATE",
    "EVENT_TYPE_PATTERN",
    "EventStoreConfig",
    "METADATA_KEYS",
    "NAME_PATTERN",
    "OUTCOME_SQLSTATE",
    "PROJECTION_MODES",
    "REBUILD_CHECKPOINT_SUFFIX",
    "REBUILD_SUFFIX",
]
