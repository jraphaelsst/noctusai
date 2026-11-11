# Roadmap — Event-Oriented Architecture (EOA) adoption · 2026-11

> Renamed 2026-11-08 from the "event-sourcing program" (owner decisions 2026-11-05/07). The architecture is declared in `KNOWLEDGE-BASE/CONTEXT/PATTERNS/architect/event-oriented-architecture.md`. Owner session: 1d87865a (products restructuring). Release steward: noctusai-51.

## Phases

| Phase | What | State 2026-11-08 |
|---|---|---|
| P0 | Finance balances summed in SQL; `projection_reconcile` drift tool | **Landed and deployed** |
| P1a | Seed E1 transition-log primitive + keeper `check_transition_log_hand_written` | Queued with the steward (c585f6f3b) |
| P3 | Seed E2 event store (`es_streams`/`es_events`/`es_checkpoints`), plus a CI real-Postgres proof | Queued, stacked on P1a (863187f67) |
| P1 pilots | Seed FUNNEL organ `pipeline_movimentos` (seed level, never per product); agents `thread_participantes` + opt-out; nosnolimiar `client_sessions` | Next, after P1a lands |
| P2 | nosnolimiar clinical tools on E1 | After the P1 pilots |
| P4 | core `public.subscriptions` on E2: direct cutover, `imported_initial_state` event, revenue-movements projection | After P3 lands |
| P5 | Broader projections and the first integration event (agents → SW Julia state feed; SW `cliente_touches`); outbox as a seed organ | After P4 |
| Adoption | The 15 hand-written history tables in `mcp/noctusai/tests/transition_log_hand_written_baseline.json`, ratcheted down | Rolling |

## Trigger conditions

- **P1 pilots:** P1a is on `dev`.
- **P4:** P3 is on `dev`.
- **Stored finance balance projection:** `account_balance` is MEASURED over its latency budget. Until then it stays a SQL `SUM`.
- **Outbox seed organ:** the first cross-product consumer.

## Open items

- `NOC-REMEDIATE[finance-ledger-sum-asleep-hosts]`, `NOC-REMEDIATE[finance-report-sql-aggregates]`
- Auto-improvement rows:
  - gate_sweep under load must report `inconclusive`;
  - `cli.py` imports the primary checkout's `noctusai_lib` from a worktree;
  - an `always_refuse_guard_sql` helper.
- Knowledge spread once P1a lands:
  - owns_kb for test-engineer on `transition-log.md` / `event-store.md`;
  - agent-context refresh;
  - a HEADS-UP to all sessions.
