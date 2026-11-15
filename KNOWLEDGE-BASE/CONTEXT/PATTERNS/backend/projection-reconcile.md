# Projections — a stored state row must equal the fold of its log

> Formalized 2026-11-07 as phase P0 of the event-sourcing / projections
> program. Self-contained.

## The concept

A **projection** is a stored value that is fully derivable from an
append-only log. The platform already has several, kept in step only by the
convention that one function writes both sides:

| Pair id | State (stored) | Log (folded) | Fold |
|---|---|---|---|
| `finance.settled_cents@<product>` | `fin_entries.settled_cents` | `fin_settlements` by `entry_id` | `sum`: `payment` adds, `refund` subtracts, rows with `reversed_at` set are skipped |
| `sw.pipeline.<funil\|processos_venda\|esteira>` | `atendimentos` / `processos_venda` / `cs_posts`.`etapa_id` | `social_wiring.pipeline_movimentos` (`pipeline = <board>`) by `entidade_id` | `latest` `para_etapa_id` by `created_at` |
| `agents.thread_participante.estado` | `agents.thread_participantes.estado` | `agents.thread_participante_eventos` by `(thread_id, agent_id)` | `latest` `para` by `created_at` |

Finance pairs exist for every active schema carrying the seed finance organ:
`social_wiring`, `nosnolimiar`, `agents`, `public` (core).

## The check — `noctus.dev.projection_reconcile`

Folds each registered log and diffs it against the state rows. Read-only:
the only SQL it emits is a single `SELECT` built from registry identifiers
(validated against `^[a-z_][a-z0-9_]*$`), sent through the Supabase
Management API executor `migrate_product.make_sql_executor`.

Verdicts per pair, enumerated:

- `consistent`: every compared key agrees. `vacuous: true` when zero keys
  were compared (an empty table proves nothing yet).
- `drift`: at least one key disagrees. The result carries the count and the
  first `sample` mismatches (`{key, state, folded}`, max 50).
- `inconclusive`: unmeasured. No credentials, query failed (table or column
  missing), a side over `max_rows` (a truncated fold would invent drift), or
  keys whose latest log rows tie on `created_at` with different values.
- `skipped`: the product is asleep in `deploy/fleet/active-scope.txt`.

Overall: `drift` > `inconclusive` > `consistent`; `ok` only when consistent.
Unmeasurable is never green and never red.

Two counts are informational, not drift:

- `unlogged`: a state key with no log row, for a `latest` fold. A pipeline
  card created straight into a stage has no movement row. A participant
  with none means a writer bypassed the store.
- `orphan_log_keys`: log keys with no state row (a hard-deleted card whose
  history outlives it by design).

## Adding a pair

Append one `PairSpec` to `DEFAULT_REGISTRY` in
`mcp/noctusai/tools/noctus/dev/projection_reconcile.py`: product, schema,
`StateSpec(table, key, value)`, `LogSpec(table, key, fold, value, order,
where, sign_column, negative_values, skip_when_set)`, `missing_log`
(`identity` for `sum`, `unlogged` for `latest`). No new code path.
`validate_pair` refuses a malformed entry before any SQL runs, and the
registry test asserts every pair belongs to an active product.

## When to run it

- After a change to either writer of a registered pair.
- As the cutover gate when a projection moves to an event store: the fold
  of the new log must reconcile with the old state before reads switch.

CLI: `python mcp/noctusai/cli.py --projection-reconcile
[--projection-reconcile-pairs a,b] [--projection-reconcile-product <slug>]`.

## Composes with

`KB § PATTERNS/backend/database-rls.md` (live-DB read tools share the
Management API executor) · `KB § PATTERNS/common/methodology-execution-discipline.md`
(verdict-channel integrity: unmeasurable ⇒ inconclusive).
