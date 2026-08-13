## Slice A — migration 048 + identity-resolution engine

**Commit:** `28dde67b` on `feat/lch-p1a-person-layer` (based on `origin/dev@04b51790`). Working tree clean, nothing left uncommitted.

### Files
- `products/social-wiring/backend/migrations/048_clientes_person_layer.sql` — DDL only, **UNAPPLIED** (contract §7)
- `products/social-wiring/backend/app/services/identidade_service.py` — the I/O-free C1-C6 predicate
- `products/social-wiring/backend/app/services/clientes_service.py` — backfill orchestration, merge/undo, read surface
- `products/social-wiring/backend/tests/test_migration_048_clientes_person_layer.py`
- `products/social-wiring/backend/tests/services/test_identidade_service.py`
- `products/social-wiring/backend/tests/services/test_clientes_service.py`

### C1-C6 counts — honest caveat first
I have **no live-DB access** (no Supabase MCP tool in this agent's allowlist, and §7 forbids applying the migration). The counts below are therefore from my own constructed test fixtures, not the live 1 413/389/13/31/212/68 the contract states — **I cannot validate those against production from this dispatch**.

What I *can* offer that directly serves §7's "state the row counts, get an explicit decision" step: `clientes_service.run_backfill(client, org_id, dry_run=True)` only ever `SELECT`s `leads`/`meta_ads_leads` — it never touches `clientes`/`cliente_touches`/anything else, so it can run against **live production, read-only, before 048 is even applied**, and returns the real `counts_by_motivo` + keyless + touch-count report. Recommend the tech-lead run that (via a short script or a REPL against the real admin client) to get the actual numbers before presenting them to the user, rather than trusting my fixture's classification alone.

My fixture (12 leads + 2 meta_ads_leads, one of each C-code deliberately including the roadmap's Carmen Real Dias / Luana Batista shared-phone C5 example) classifies correctly end-to-end: `{"C1": 2, "C2": 1, "C3": 0, "C4": 1, "C5": 1, "C6": 1}`, 1 keyless cliente, 11 clientes created, 14 touches, 1 merge, 4/4 negociações repointed with zero orphans. Full scenario in `TestRunBackfillFullFixture`.

### Concurrency / idempotency strategy (§7)
1. Every source row already represented in `cliente_touches` (by the exact `(origem_tabela, origem_id)` the UNIQUE index enforces) is skipped — re-running on unchanged data is a true no-op (tested: `TestIdempotency.test_rerun_on_unchanged_data_is_a_no_op`).
2. A genuinely new row under an **already-seen key** is reconciled against whatever exists for that key rather than reclassified from scratch: exact normalized-name match (or a lone nameless straggler against a single existing identity) attaches as a new touch + recomputes span; anything else is parked as its own new review-visible cliente (never silently guessed, never re-opens a past decision). Both branches tested.
3. `negociacoes_venda.cliente_id` repoint only touches rows where `cliente_id IS NULL`.

This is a deliberately conservative reconciliation (documented as a known limitation in `clientes_service.py`'s module docstring) — it does not re-classify OLD + NEW rows together, so a straggler cannot retroactively un-confirm a prior automatic merge. A fuller reconciliation engine is a plausible follow-up, not built here.

### How a merge is reversed (D3)
`cliente_merges` holds a full snapshot of the absorbed identity (`nome_absorvido`, `chave_canonica_absorvido`, `chave_tipo_absorvido`, `identidade_incerta_absorvido`) plus `touches_movidos` (JSONB array of exactly which `(origem_tabela, origem_id)` pairs moved). `undo_merge` recreates a **new** cliente row from that snapshot (a fresh id — the original `cliente_id_absorvido` is a synthetic handle for an automatic merge, since no row was ever inserted for the losing cluster; see the column's `COMMENT ON COLUMN`) and moves exactly those touches back. Tested round-trip: merge → undo → clientes/touches state restored equivalently; undo-twice raises `MergeAlreadyUndone`; undo-unknown raises `MergeNotFound`.

### 🔴 A real contract tension found, and how I resolved it — please review
`clientes` carries `UNIQUE (org_id, chave_canonica) WHERE NOT NULL` (contract §4, explicit and load-bearing). A C4-C6 review group by definition has 2+ candidate identities that might all be the "real" owner of that phone/email — but the UNIQUE constraint means **at most one cliente can ever claim that key**. So a review group cannot be stored as N clientes all provisionally holding the same real key.

Resolution: every review-group cliente is created with `chave_canonica = NULL, identidade_incerta = true` — none of them claims the key until a human resolves the ambiguity via the (Slice B) merge/manter-separados flow. `identidade_incerta` is thereby generalised beyond its contract §2 definition ("no key at all") to also mean "a real key that is provably shared and not safe to claim yet." The real key is never lost — it's denormalised onto every `cliente_touches.chave_canonica` row, which is also what lets `list_review_groups` find these candidates (via a touches-join) even though their own `chave_canonica` is null.

I believe this is the only design that satisfies the UNIQUE constraint AND the review-queue requirement (§5) simultaneously, but it's a genuine interpretation call the contract doesn't spell out — flagged here explicitly rather than silently shipped. If the tech-lead / architect wants a different resolution (e.g. a separate `revisado`/status column, or a different key-claiming heuristic), the change is contained to `_create_clusters`/`_reconcile_against_existing` in `clientes_service.py`.

### Tests: 1765 → 1855 passed (90 new), 0 failed
- 37 `identidade_service` (pure, no DB) — every C1-C6 case incl. the shared-phone C5 example, the vacuous-all-nameless C1 edge case (documented as an interpretation call), `span()`'s bare-date-vs-timestamp sort correctness.
- 32 migration-structure (`pglast` when available + the real `noctusai_lib.testing.migration_parser` the platform's `MockSupabaseClient` schema-cache uses) — the partial-unique assertion, the `identidade_incerta`/`chave_tipo` CHECK constraints, the negociacoes_venda repoint being unconditional/undependent on a backfill, RLS shape.
- 21 `clientes_service` — the full backfill scenario, dry-run (no writes, no `cliente_touches` read prerequisite), idempotency + 3 reconciliation scenarios, merge/undo round-trip, `list_review_groups`, basic read surface.

### Confirmation: 048 is UNAPPLIED
Never ran against any database. `noctus.dev.migrate_product` was never invoked for social-wiring in this session. The row counts it would touch (per my own uncertain fixture, or better, the tech-lead's real dry-run) must be stated to the user for an explicit go-ahead before it is applied (§7).

### drift-found
1. `products/social-wiring/backend/app/services/marcas_service.py` (and `imoveis_service.py`) call `self._client.schema(SCHEMA).table(t)` fresh on every method — the SAME `MockSupabaseClient` data-loss defect `app/modules/leads/deps.py` already diagnosed and fixed once for this exact product (its docstring literally names `marcas_service.py` as an example of the unfixed shape). Not touched here (outside my `Files-to-modify`), but it means those two services' OWN test suites either don't exercise cross-call write-propagation, or are silently relying on the SQLite dev client's `.schema()` no-op instead of `MockSupabaseClient`. Worth a follow-up sweep.
2. `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` was auto-staged and committed alongside my change by the pre-commit hook's mechanical KB-count refresh (per its own documented KB-autostage-hook contract) — not authored content, just the count-marker regenerating against my new product files.

### scoped-improvement
1. **`noctusai_lib.testing.migration_parser`'s `--`-inside-a-string-literal footgun.** I hit this directly: a `COMMENT ON COLUMN ... IS '...row -- it never expects...';` used `--` as a prose em-dash INSIDE a single-quoted SQL string literal. The shared parser's `_strip_line_comments` does `re.sub(r"--[^\n]*", "", sql)` **before** any string-literal-aware walking, so it truncated the literal mid-string, desynchronized the statement walker, and caused a LATER, unrelated `ALTER TABLE ... ADD COLUMN` to be mis-attributed to the wrong table in the schema cache (`negociacoes_venda.cliente_id` silently vanished; `cliente_merges` gained a phantom `cliente_id` column). Caught only because my own test suite asserted the parsed schema explicitly (`test_migration_parses_via_the_mock_schema_cache_parser`) — a migration that merely CREATEs tables without such an assertion could ship this silently, degrading `MockSupabaseClient`'s schema validation for every OTHER product's tests too (graceful-degradation means it fails silent, not loud). Suggest either (a) a `check_sql_comment_token_inside_string_literal` keeper scanning migrations for `--` between an odd number of unescaped `'`s on a line, or (b) hardening `_strip_line_comments` itself to be quote-aware (bigger, shared-infra change). I did NOT fix the shared parser — out of my file-disjoint scope — only my own SQL.
2. **`clientes_service.py`'s "client must already be schema-scoped" convention** should get its own `get_clientes_client()` DI helper (mirroring `app/modules/leads/deps.py`'s `WeakKeyDictionary`-cached pattern exactly) when Slice B wires routers — I documented the requirement in the module docstring but did not build the deps.py helper itself (main.py/deps wiring is Slice B's file list).
3. The review-queue's "keep separate" outcome (§5 `POST /manter-separados`) has no durable "don't resurface" marker in my schema — `list_review_groups` will re-surface a group forever unless Slice B adds one (a `clientes.revisado_em`-shape column, or a small side table). Not built here since §4 doesn't name it; flagged for Slice B / the tech-lead to decide.

codification-events: s1=2 (the `--`-in-string-literal footgun; the `identidade_incerta` generalisation as a candidate contract clarification) s2=none s3=none s4=none
drift-found: see above (2 items)
scoped-improvement: see above (3 items)
delivery-note: this file

## Commit message (already landed)
```
feat(social-wiring): lead-card-hub P1 slice A — clientes person layer schema + resolution engine
```
(full message on `28dde67b`, `feat/lch-p1a-person-layer`)
