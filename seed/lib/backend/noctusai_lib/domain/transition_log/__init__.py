"""Transition log -- the seed primitive for "state row + append-only transition row in ONE transaction".

The state row is the truth; the log explains how it got there (KB § PATTERNS/backend/transition-log.md --
and when to reach for the future event store instead, where the log IS the truth). One render per aggregate:

    cfg = TransitionLogConfig(schema="social_wiring", aggregate="pipeline_card",
                              state_table="pipeline_cards", state_column="stage_id", state_type="uuid")
    sql = transition_log_migration(cfg)                    # -> migrations/0NN_<aggregate>_transition_log.sql
    sql += transition_log_backfill_sql(cfg)                # existing entities get a synthetic seq-1 event
    log = make_transition_log("supabase", cfg=cfg, client=db)
    log.create(org, {"title": ..., "stage_id": first})     # state row + seq-1 `created`, atomically
    log.transition(org, card_id, from_state=a, to_state=b) # lock -> compare-and-set -> state + next seq
    log.erase_subject(org, card_id, reason="LGPD art. 18") # the ONE gated delete (logged)

Composite keys: `key=(KeyColumn("thread_id"), KeyColumn("agent_id"))`; pass keys as `{"thread_id": ..., "agent_id": ...}`.
"""
from .config import (
    CREATED_EVENT,
    CREATION_EVENT_TYPES,
    DEFAULT_ACTOR_KINDS,
    DEFAULT_EVENT_TYPE,
    IMPORTED_INITIAL_EVENT,
    SYNTHETIC_ACTOR_KIND,
    KeyColumn,
    TransitionLogConfig,
    normalize_key,
    normalize_subject,
)
from .guards import transition_log_guard_probes
from .port import (
    ErasureOutcome,
    FakeTransitionLog,
    SupabaseTransitionLog,
    TransitionLog,
    TransitionOutcome,
    make_transition_log,
)
from .sql import (
    APPEND_ONLY_SQLSTATE,
    CONFIG_MARKER,
    ERASURES_TABLE,
    MIGRATION_HEADER,
    RPC_NAMES,
    configs_in_migration,
    transition_log_backfill_sql,
    transition_log_migration,
)

__all__ = [
    "APPEND_ONLY_SQLSTATE",
    "CONFIG_MARKER",
    "CREATED_EVENT",
    "CREATION_EVENT_TYPES",
    "DEFAULT_ACTOR_KINDS",
    "DEFAULT_EVENT_TYPE",
    "ERASURES_TABLE",
    "ErasureOutcome",
    "FakeTransitionLog",
    "IMPORTED_INITIAL_EVENT",
    "KeyColumn",
    "MIGRATION_HEADER",
    "RPC_NAMES",
    "SYNTHETIC_ACTOR_KIND",
    "SupabaseTransitionLog",
    "TransitionLog",
    "TransitionLogConfig",
    "TransitionOutcome",
    "configs_in_migration",
    "make_transition_log",
    "normalize_key",
    "normalize_subject",
    "transition_log_backfill_sql",
    "transition_log_guard_probes",
    "transition_log_migration",
]
