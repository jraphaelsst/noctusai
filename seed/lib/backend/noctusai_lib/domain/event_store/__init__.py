"""Event store -- the seed organ for "the log IS the truth" (event-sourcing program P3, 2026-11-07).

State is derived from an append-only, per-stream-versioned log; projections (sync, inside the append; async,
checkpointed) build the read models. KB § PATTERNS/backend/event-store.md (and, for "the state row is the truth",
the sibling `noctusai_lib.domain.transition_log`).

    sql = event_store_migration(EventStoreConfig(schema="core"))     # via noctus.dev.render_organ_migration organ=event_store
    store = make_event_store("supabase", client=db)                  # or "fake" in tests
    out = store.append(org, "subscription", sid, [NewEvent("subscription.created", {"plan_id": p}, event_id=cmd_id)],
                       expected_version=0)
    result = execute(store, org, "subscription", sid, decide, evolve=evolve, upcasters=up)   # load-fold-decide-append
    store.run_projection("subscription_summary")                      # async: batch + checkpoint in ONE transaction
    rebuild_projection(store, "subscription_summary")                 # shadow -> replay from 0 -> swap
"""
from .config import (
    ANY_VERSION,
    APPEND_ONLY_SQLSTATE,
    EVENT_TYPE_PATTERN,
    METADATA_KEYS,
    NAME_PATTERN,
    PROJECTION_MODES,
    EventStoreConfig,
)
from .execute import ConcurrencyConflict, ExecuteResult, execute, fold
from .guards import event_store_guard_probes
from .port import (
    CheckpointStore,
    EventStore,
    FakeCheckpointStore,
    FakeEventStore,
    RealSupabaseCheckpointStore,
    RealSupabaseEventStore,
    make_checkpoint_store,
    make_event_store,
    new_stream_id,
)
from .projections import (
    PROJECTION_JOB_TYPE,
    ExternalProjectionRunner,
    ExternalRun,
    projection_job_handler,
    rebuild_projection,
)
from .sql import (
    CHECKPOINTS_TABLE,
    EVENTS_TABLE,
    MIGRATION_HEADER,
    PROJECTIONS_TABLE,
    RPC_NAMES,
    STREAMS_TABLE,
    event_store_migration,
)
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
)
from .upcasting import (
    UpcastError,
    Upcasters,
    assert_every_stored_type_handled,
    load_stream,
    unhandled_stored_types,
)

__all__ = [
    "ANY_VERSION",
    "APPEND_ONLY_SQLSTATE",
    "AppendOutcome",
    "CHECKPOINTS_TABLE",
    "Checkpoint",
    "CheckpointStore",
    "ConcurrencyConflict",
    "Cursor",
    "EVENTS_TABLE",
    "EVENT_TYPE_PATTERN",
    "EventStore",
    "EventStoreConfig",
    "ExecuteResult",
    "ExternalProjectionRunner",
    "ExternalRun",
    "FakeCheckpointStore",
    "FakeEventStore",
    "LoadedStream",
    "METADATA_KEYS",
    "MIGRATION_HEADER",
    "NAME_PATTERN",
    "NewEvent",
    "PROJECTIONS_TABLE",
    "PROJECTION_JOB_TYPE",
    "PROJECTION_MODES",
    "ProjectionRun",
    "RPC_NAMES",
    "ReadBatch",
    "RealSupabaseCheckpointStore",
    "RealSupabaseEventStore",
    "RebuildOutcome",
    "RebuildStep",
    "STREAMS_TABLE",
    "StoredEvent",
    "UpcastError",
    "Upcasters",
    "assert_every_stored_type_handled",
    "event_store_guard_probes",
    "event_store_migration",
    "execute",
    "fold",
    "load_stream",
    "make_checkpoint_store",
    "make_event_store",
    "new_stream_id",
    "projection_job_handler",
    "rebuild_projection",
    "unhandled_stored_types",
]
