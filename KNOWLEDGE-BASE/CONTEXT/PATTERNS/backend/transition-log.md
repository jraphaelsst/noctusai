# Transition log — state row + append-only transition row, one transaction

> Seed primitive `noctusai_lib.domain.transition_log` (P1a of the event-sourcing program,
> 2026-11-07). Self-contained. Keeper: `check_transition_log_hand_written`. Guard
> probes: `verify_db_guards.derive_transition_log_probes`.

## 1. When to use this shape (and when not)

**The state row is the truth; the log explains how it got there.** Reach for it when an
entity moves through states (a card's stage, a participant's status, an opt-out flag) and
you need *who moved it, from what, to what, when, why* — with a guarantee that the history
cannot be edited and cannot drift from the state.

| Need | Shape |
|---|---|
| Current state is what the app reads; history is for audit, timelines, analytics | **transition log** (this doc) |
| The history IS the truth; state is a projection rebuilt from events (replay, temporal queries, several projections) | the **event store** (later phase of the event-sourcing program — not built yet) |
| A request/action trail across every mutating call | `KB § PATTERNS/backend/audit-trail.md` |
| An immutable version table (agent versions, prompt versions) | not this — a version is a snapshot, not a transition |

Before this primitive the shape was hand-built about eight times (`pipeline_movimentos` ×4,
`thread_participante_eventos`, `editorial_events`, `fotos_eventos`, `imovel_preco_historico`, …)
with inconsistent immutability, no sequence, `ON DELETE CASCADE` history, and state/log
written in two round-trips. New ones are refused by the keeper (§7).

## 2. Shape

`transition_log_migration(TransitionLogConfig(...))` renders, per schema and aggregate:

- **`<schema>.<aggregate>_events`** — `id` (client event id), `org_id`, the key column(s),
  `seq`, `from_state`, `to_state`, `event_type`, `data jsonb`, `actor_id`, `actor_kind`,
  `correlation_id`, `occurred_at`, `recorded_at`. `UNIQUE(<key>, seq)` + index
  `(org_id, <key>, seq)`. CHECKs: `seq > 0`; `(seq = 1) = (event_type IN creation types)` and a
  creation event has `from_state IS NULL`; `event_type` snake_case; `data` is an object;
  `actor_kind` from a closed set that includes the reserved `synthetic`.
- **FK to the state table** `NO ACTION DEFERRABLE INITIALLY IMMEDIATE` — never
  `ON DELETE CASCADE`: deleting a state row with history is refused until the history is erased.
  `foreign_key=False` for a state table you cannot reference.
- **RLS on, `tier:org`, service-role only** (`authenticated` gets no direct read; products
  serve history through their own API). Every function is `SECURITY DEFINER`, `search_path`
  pinned, `EXECUTE` revoked from `PUBLIC, anon, authenticated`.
- **RPCs** (all return jsonb `{status: ok|replayed|refused, ...}`):
  `<agg>_create` (insert the state row + seq-1 `created`), `<agg>_record_created` (state row
  already inserted by the product), `<agg>_transition`, `<agg>_history`,
  `<agg>_erase_subject`, `<agg>_backfill_initial_state`.
- A `-- transition-log-config: {json}` marker line per aggregate — the derivation source for
  guard probes and the keepers. Never hand-edit a render; re-render.

### Transition semantics

`<agg>_transition(p_org, p_key, p_from, p_to, p_event_type, p_data, p_actor_id, p_actor_kind, p_correlation_id, p_event_id, p_occurred_at)`:

1. validate inputs (refused `invalid_*`);
2. `SELECT ... FOR UPDATE` the state row (refused `not_found` / wrong org);
3. **idempotency** — if `p_event_id` already exists for this entity: `replayed` with the
   original event (checked AFTER the lock, so a concurrent retry cannot double-append);
4. **compare-and-set** — current state `IS DISTINCT FROM p_from` → refused `stale_state` with
   `current_state`;
5. **lazy first event** — an entity with no history yet (pre-primitive row) first gets a
   synthetic seq-1 `imported_initial_state`;
6. update the state column (+ `updated_at` when configured), append the event at `max(seq)+1`.

**Creation is the first event (seq 1).** Existing rows: `transition_log_backfill_sql(cfg)`
renders `SELECT <s>.<agg>_backfill_initial_state(NULL);` — one synthetic
`imported_initial_state` event per entity without history (`actor_kind='synthetic'`,
`data.synthetic=true`, `occurred_at` = the row's `created_at` when configured). Idempotent.

### Composite keys

`key=(KeyColumn("thread_id"), KeyColumn("agent_id", "text"))` — the key columns are real
columns on the events table (no synthetic hashed id), so history is queryable by any key
prefix and the erasure subject can be a subset. Python passes a mapping
`{"thread_id": ..., "agent_id": ...}` (a scalar is accepted for a single-column key);
`KeyColumn(name, type, state_column)` maps an events column onto a differently-named state
column (default key: `entity_id` → state `id`).

## 3. LGPD erasure — the ONE gated delete

UPDATE, DELETE and TRUNCATE on the events table are refused (`guc_carveout_guard_sql`,
SQLSTATE `TL001`, plus a statement-level TRUNCATE trigger the GUC guard does not cover).
Exactly one path deletes: `<agg>_erase_subject(p_org, p_subject jsonb, p_reason, p_actor_id)`.

- `SECURITY DEFINER`; sets the transaction-local GUC `noctus_tl.erase_<aggregate>` (one flag
  per aggregate — another aggregate's flag does not open this table), deletes the subject's
  events, turns the flag off, and appends a row to the schema's shared, append-only
  **`transition_log_erasures`** (aggregate, subject, count, reason, actor, at). The reason is
  mandatory.
- `p_subject` may be a **subset** of the key (e.g. every participant row of a `thread_id`) —
  this keeps agents' delete-by-lead implementable; after erasure the product deletes the state
  row with a real `DELETE` (monica's requirement) because the FK no longer blocks.
- It is a real delete. Not crypto-shredding, not "no delete".
- The erasure log stores the subject KEY (identifiers), not the erased payload.

## 4. Python helper

`TransitionLog` Protocol · `FakeTransitionLog` (full parity, in-memory, thread-safe) ·
`SupabaseTransitionLog` (calls the RPCs via `client.rpc(...)`) · `make_transition_log("supabase"|"fake", cfg=..., client=...)`.
Results: `TransitionOutcome(status, event, code, current_state, detail)` and
`ErasureOutcome(status, deleted, code)`. One shared conformance suite
(`seed/lib/backend/tests/domain/transition_log/conformance.py`) runs against the Fake AND the
Real adapter on real Postgres (PGlite) — parity is proven, not asserted.

## 5. Guard probes

`verify_db_guards` derives probes for every rendered aggregate in any product (from the
config marker): UPDATE and DELETE refused, TRUNCATE refused, every CHECK and the
`UNIQUE(key, seq)` refuse, the erasure log is append-only, and **the erasure function works**
(a `write_allowed` probe: one seeded event erased, zero left). An unparseable marker becomes a
failing probe, never silence. `check_migration_guard_has_probe` accepts the render's guards
because the probes are declared by `transition_log_guard_probes(cfg)`.

## 6. Adopting it (pilots)

1. Render into a new migration (`transition_log_migration(cfg)` + `transition_log_backfill_sql(cfg)`);
   keep the legacy history table read-only until the cut-over, then copy it in as events
   (synthetic `actor_kind` when the original actor is unknown) and drop it.
2. Replace the two-round-trip write (update state, then insert history) with
   `log.transition(...)`; pass a client event id from the request for retries.
3. Remove the table's entry from `mcp/noctusai/tests/transition_log_hand_written_baseline.json`
   (shrink-only ratchet).
4. A delete-by-subject flow calls `erase_subject` before the state-row delete.

## 7. Keeper

`check_transition_log_hand_written` (`--check-transition-log-hand-written`, pre-commit shadow
→ blocking after the shadow record): flags a `CREATE TABLE` with a from/to state-column pair
(`de_*`/`para_*`, `*_anterior`/`*_novo`, `from_*`/`to_*`, … — temporal ranges and two-entity
pairs excluded) or a `BEFORE UPDATE OR DELETE` trigger on a history-named table. Seed renders
pass; legacy copies are baselined; a reasoned non-fit carries
`-- transition-log-ok: <table> <reason>`.

## Sources

- PostgreSQL 16 docs — *Explicit Locking* § Row-Level Locks (`SELECT ... FOR UPDATE` serialises
  concurrent transitions on one entity); *CREATE TRIGGER* (`BEFORE TRUNCATE` is statement-level
  only — why the render adds its own TRUNCATE trigger); *SET CONSTRAINTS* (deferrable FKs);
  *CREATE FUNCTION* § Writing SECURITY DEFINER Functions Safely (pinned `search_path`, revoked
  `EXECUTE`). <https://www.postgresql.org/docs/16/>
- Martin Fowler, *Event Sourcing* (2005) and *Audit Log* — the distinction between a log that
  explains state (this primitive) and a log that IS the state (the future event store).
  <https://martinfowler.com/eaaDev/EventSourcing.html>
- LGPD, Lei 13.709/2018, art. 18 VI (eliminação dos dados) and art. 16 (retention exceptions) —
  why the erasure is a real, logged delete and not crypto-shredding.
- Verified in-tree: the conformance suite and the PGlite proofs
  (`seed/lib/backend/tests/domain/transition_log/`) run the rendered SQL on PG16; nothing above
  is relied on unverified.
