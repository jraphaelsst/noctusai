# Event store — the log IS the truth; read models are projections

> Seed organ `noctusai_lib.domain.event_store` (P3 of the event-sourcing program, 2026-11-07),
> registered as organ `event_store` (`noctus.dev.render_organ_migration organ=event_store`).
> Self-contained. Guard probes: `event_store_guard_probes` (derived by `verify_db_guards`).
> Rebuild tool: `noctus.dev.projection_rebuild`. Sibling: `KB § PATTERNS/backend/transition-log.md`.

## 1. When to use this shape (and when not)

| Need | Shape |
|---|---|
| Current state is what the app reads; history explains it (audit, timeline) | **transition log** — `KB § PATTERNS/backend/transition-log.md` |
| The history IS the truth: state is folded from events; replay, temporal queries, several read models, rebuild a read model after a bug | **event store** (this doc) |
| A request/action trail across every mutating call | `KB § PATTERNS/backend/audit-trail.md` |

Pick the event store only when the replay is the point. It costs a projection per read model
and an upcaster per payload change; a state machine with an audit need is a transition log.

## 2. Shape (rendered per product schema)

- **`es_streams`** — one row per stream (`stream_type`, `stream_id`, `org_id`, `version`). Written
  only by `es_append` (insert/update under the append flag; delete and TRUNCATE refused).
- **`es_events`** — `global_position` (identity PK), `event_id` (UNIQUE — the idempotency key),
  `stream_type`/`stream_id`/`version` (UNIQUE together, `version >= 1`), `event_type` (shape CHECK
  only — **no closed list**, see §6), `schema_version >= 1`, `data` (JSON object), `metadata`
  (closed key set: `causation_id`, `correlation_id`, `actor_id`, `actor_kind`, `source`),
  `occurred_at`, `recorded_at`, `tx_id xid8 DEFAULT pg_current_xact_id()`, and the reserved
  `pii` / `subject_id` (CHECK: both NULL). FK to `es_streams` is `NO ACTION` — nothing cascades a
  delete into the log. UPDATE / DELETE / TRUNCATE refused always (`ES001`); INSERT only under the
  transaction-local flag `noctus_es.append_<schema>` that `es_append` sets
  (`guc_carveout_guard_sql` + `truncate_guard_sql`, `noctusai_lib.domain.sql_templates`).
- **`es_projections`** — registry: `projection`, `handler` (a function NAME), `target` (a table
  NAME), `stream_types text[]`, `mode sync|async`. Names, not `regprocedure`/`regclass` columns
  (those break `pg_upgrade`).
- **`es_checkpoints`** — `projection` PK, `tx_id xid8`, `position`, `last_error`.
- Snapshots are **deferred**: when a stream gets long enough to need one, the shape is
  `es_snapshots(stream_type, stream_id, version, state jsonb, schema_version)` read as
  "load snapshot, then events after `version`"; it is a cache, never the truth.

RLS on every table, no policies (service-role only — tier:org for the event tables, tier:platform
for registry + checkpoints). Every function `SECURITY DEFINER`, `search_path` pinned, `EXECUTE`
revoked from PUBLIC/anon/authenticated; service_role gets the RPCs only.

## 3. Writing — `es_append`

`es_append(p_org, p_stream_type, p_stream_id, p_expected_version, p_events)`:
upsert + lock the stream row (`FOR UPDATE`), check `expected_version` (`-1` = any, `0` = new
stream), insert the events, run the **sync** projections, return
`{status: ok, version, positions}`. Outcomes are data:

- `conflict` + `current_version` — nothing written (not even an empty stream row: the whole body
  is one subtransaction, rolled back by an internal `ES409` raise).
- `replayed` — every `event_id` already stored, same stream and types: the first attempt's
  answer. A partial or mismatched replay is `refused/idempotency_conflict`.
- `refused` + code (`org_mismatch`, `pii_disabled`, `invalid_*`, `projection_failed`, …).

Python: `make_event_store("supabase", client=db)` / `"fake"`; `execute(store, org, type, id, decide,
evolve=..., upcasters=...)` = load → fold → decide → append; on `conflict` it **reloads and runs
`decide` again** (never re-appends a decision taken on stale facts), up to 3 attempts, then raises
`ConcurrencyConflict`. Give events ids derived from the command so a retried request replays.

## 4. Reading — the visibility rule

`es_load` returns one stream (another org's stream reads as empty — no existence oracle).
`es_read_all(after_tx, after_position, limit, stream_types)` is the global feed for projections,
and it returns **only settled events**: `tx_id < pg_snapshot_xmin(pg_current_snapshot())`,
ordered and paged by the pair `(tx_id, global_position)`.

Why: `global_position` is assigned at INSERT, visibility at COMMIT. A transaction that inserted
early and commits late would land *behind* a cursor that already moved past it — a position-only
reader skips it forever. Below `xmin` no transaction can still commit, so the settled set only
grows at the end; and because one transaction's events share one `tx_id`, the pair orders a
late-position/early-xid writer correctly too. Cost: a long-open transaction anywhere in the
database delays the feed (lag, never loss). The checkpoint therefore stores `(tx_id, position)`,
not a position. Proven with two real connections in
`seed/lib/backend/tests/domain/event_store/test_event_store_concurrency.py` (both orderings).

## 5. Projections — sync vs async

**Registration** is data (`es_register_projection(name, handler, target, stream_types, mode)`),
done in the product's migration after it creates the handler and the target table. A handler is
`<schema>.<handler>(p_events jsonb, p_target regclass) RETURNS void` — the target is a parameter
so the rebuild can point the same code at a shadow table.

- **sync** — run by `es_append` inside the append's transaction: the read model is never behind,
  a handler error refuses the append (`projection_failed`, nothing written). Use for small,
  same-schema read models the next request must see. Keep them cheap: they hold the stream lock.
- **async** — `es_run_projection(name, limit)` locks the checkpoint row `FOR UPDATE SKIP LOCKED`
  (a second runner answers `busy`), applies one settled batch and moves the checkpoint **in the
  same transaction** → exactly-once effect on an in-database read model. A failing batch moves
  neither and records `last_error`. Drive it from the seed jobs worker:
  `Worker(repo, handlers={PROJECTION_JOB_TYPE: projection_job_handler(store)})` (queue claim =
  `SKIP LOCKED` + lease; `refused` dead-letters, `error` retries).
- **external effects** (email, webhook) — `ExternalProjectionRunner` over a `CheckpointStore`:
  `read_all` → handler → compare-and-set advance. At-least-once by nature: dedupe downstream on
  `event_id`.

## 6. Upcasting — old shapes are read, never rewritten

`Upcasters().register(event_type, from_version, fn)` chains `v1→v2→…→current`; `load_stream` /
`execute` apply it on load. A stored event is never updated (the guard refuses it). There is no
CHECK on `event_type` on purpose — a closed list in the database makes every new event type a
migration; the gate is the test: `assert_every_stored_type_handled(store, handled=..., upcasters=...)`
fails when the log holds a `(type, version)` the code has no handler or no complete chain for.

## 7. Rebuild

`es_rebuild_begin` (shadow `<target>__rebuild` `LIKE target INCLUDING ALL`, RLS on, cursor
`<projection>#rebuild` at 0) → `es_rebuild_step` × N (one settled batch per transaction; the live
read model keeps serving) → `es_rebuild_swap` (`LOCK target IN EXCLUSIVE MODE`, catch up — settled
events for async with the live checkpoint locked, every committed event for sync since appends
wait on the lock — then replace the target's **contents** with the shadow's, drop the shadow,
reset the checkpoint). The swap copies rows instead of renaming tables so the target keeps its
policies, grants, triggers and dependants. Python: `rebuild_projection(store, name)`; agents:
`noctus.dev.projection_rebuild product=… projection=…` (dry-run plan, `confirm=True` runs).
Rebuild repairs a read model; *detecting* that one drifted from the log is the job of the
projection-reconcile pattern (doc `projection-reconcile.md`, tool `noctus.dev.projection_reconcile`,
on branch `feat/projection-reconcile-tool` — not on `dev` yet, so not linked here).

## 8. LGPD

**No personal data in events, by default.** `pii` and `subject_id` exist only as reserved columns
and a CHECK keeps them NULL; `metadata` is a closed set of ids. Events carry ids that point at
rows which hold personal data (and can be erased there). When a stream genuinely must carry
personal data, the planned path is crypto-shredding: encrypt `pii` per `subject_id` with a key
held outside the log and delete the key to erase — that is a deliberate future change (drop the
CHECK, add the key table), not a default. Events are never deleted.

## 9. Guard probes

`event_store_guard_probes(schema)` declares one probe per emitted guard — the append-only trigger
(insert/update/delete variants), both TRUNCATE triggers, the streams guard, every CHECK and both
UNIQUE indexes — so `verify_db_guards` proves each refuses on the live database inside a
rolled-back transaction, for every product that renders the organ.

## Sources

- PostgreSQL 16 docs — *System Information Functions* (`pg_current_xact_id`,
  `pg_current_snapshot`, `pg_snapshot_xmin`, `xid8`); *Explicit Locking* (`FOR UPDATE`,
  `SKIP LOCKED`, `LOCK TABLE … EXCLUSIVE`); *CREATE TRIGGER* (`BEFORE TRUNCATE` is statement
  level); *CREATE FUNCTION* § Writing SECURITY DEFINER Functions Safely; *pg_upgrade* (reg* OID
  types unsupported in user tables). <https://www.postgresql.org/docs/16/>
- Martin Fowler, *Event Sourcing* (2005) — log as source of truth, rebuild, temporal query.
  <https://martinfowler.com/eaaDev/EventSourcing.html>
- Greg Young, *Versioning in an Event Sourced System* (2017) — upcasting on read, never mutating
  stored events. <https://leanpub.com/esversioning>
- Marten / Message DB / EventStoreDB docs — global-position gaps from late commits and the
  high-water-mark / settled-read answer (Marten's "HighWaterMark" agent; Message DB's per-stream
  version + global position). Read for the problem statement; the `xmin` rule here is our
  implementation. <https://martendb.io/events/projections/async-daemon.html>
- LGPD, Lei 13.709/2018, art. 18 VI (elimination) — why personal data stays out of an
  undeletable log.
- Verified in-tree: the conformance suite (Fake + Real on PGlite), the posture tests and the organ
  guard probes run the rendered SQL on PG16. The two-connection proofs need a real server
  (`noctusai_lib.testing.pgserver`) — unverified on a machine without one (they skip, visibly).
