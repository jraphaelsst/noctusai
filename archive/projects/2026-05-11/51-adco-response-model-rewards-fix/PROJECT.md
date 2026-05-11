# projects/adco-response-model-rewards-fix · 2026-05-11

> Fix 3 of 4 REAL_BUGs surfaced by `projects/response-model-silent-drop-audit` (`de045c3`) that live in `products/adconnect/backend/app/schemas/rewards.py`. Scope: **R1 + R3 + R4** (R2 absorbed under R4's fan-out). User decision on R3: **Option A — extend the table**.
>
> Branch: `adco-response-model-rewards-fix-2026-05-11`. Base: `de045c3`.

---

## 1 · Context

The audit found four schema-vs-DB drift bugs in adconnect. This project closes three of them in a single coordinated change because they all live in `app/schemas/rewards.py` and the corresponding services / migrations — bundling avoids file-collision with the parallel `ADCO-SELLOUT-FIX` engineer (separate file, `app/schemas/sellout.py`).

| Bug | Disposition |
|---|---|
| R1 — duplicate `RewardRuleOut` in `rewards.py` (broken) vs `admin.py` (correct) | **FIXED** — deleted broken duplicate; `RewardRulesListOut` switched to `list[dict[str, Any]]` pass-through (mirrors `admin.RewardRuleListOut`). |
| R3 — `RedemptionOut` ↔ `resgates_recompensa` divergence (8 schema-only fields + 5 DB-only columns) | **FIXED** — Option A: new migration `003_resgates_recompensa_align.sql` adds the 9 missing columns to the table; `RedemptionOut` extended to expose the 5 original-migration columns. |
| R4 — `RewardLedgerEntry.source_relatorio_id` mis-named vs DB column `source_relatorio_sellout_id` | **FIXED** — schema field renamed; service callers + tests updated. |

R2 (`RewardLedgerEntry` schema-side `expires_at` / `created_at` additions, drop `moeda`) — DEFERRED, not included in this brief.

---

## 2 · Interrogation transcript

The dispatch brief was self-contained — no live Q&A needed. Two architect calls codified the live decisions:

- "**R3 — USER DECISION: OPTION A — extend the table.**" Schema is the contract; migration grows to match.
- "**R4 — rename schema field to `source_relatorio_sellout_id`**" — direct align to DB column name.

---

## 3 · Baseline

Pre-change: **230 passed + 18 skipped** in `products/adconnect/backend/`. The brief quoted 229 (post-Wave-1 strict-http rollout); the extra +1 is from intermediate work that landed between Wave 1 close and this brief. No drift in scope.

---

## 3a · Seed-first analysis

The three bugs are **product-specific schema-vs-DB drifts**, not cross-cutting concerns:

- R1 — the duplicate-class slip is local to adconnect (two schema files within one product collided on a class name). Seed has no shape to formalize here; the keeper-detector `seed-keeper-check-response-model-vs-migration` already filed in the audit's §8 covers the detection side.
- R3 — table-extension migration is product-local (only `adconnect.resgates_recompensa`).
- R4 — field rename is product-local.

**Replication-to-seed symmetry check**: no "per-product X" phrasing fires. Nothing in this fix should land at the seed level; the *detector* for the bug class is the seed-side artifact, and that's already tracked.

---

## 4 · Goal

- Schemas in `app/schemas/rewards.py` match the (post-migration-003) `resgates_recompensa` + `regras_recompensa` + `recompensas_acumuladas` tables verbatim.
- Service layer (`rewards_service.py`) writes / reads columns that exist in the real DB.
- Tests seed real DB column names so they detect production-shape regressions, not just mock-shape regressions.

---

## 5 · Files touched

- `products/adconnect/backend/app/schemas/rewards.py` — deleted duplicate `RewardRuleOut`; renamed `source_relatorio_id` → `source_relatorio_sellout_id`; loosened `RewardRulesListOut` to `list[dict[str, Any]]`; extended `RedemptionOut` with 5 pre-existing DB columns + `Optional` for fields that may be NULL until backfilled.
- `products/adconnect/backend/app/schemas/__init__.py` — dropped re-export of `RewardRuleOut` from `rewards`; the canonical variant (from `admin.py`) remains.
- `products/adconnect/backend/app/services/rewards_service.py` — `.eq("ativo", True)` → `.eq("ativa", True)`; `rule.get("cashback_pct")` → `rule.get("valor")`; param + payload key + docstring `source_relatorio_id` → `source_relatorio_sellout_id`.
- `products/adconnect/backend/app/routers/rewards.py` — `.eq("ativo", True)` → `.eq("ativa", True)`.
- `products/adconnect/backend/migrations/003_resgates_recompensa_align.sql` — **NEW**. ALTER TABLE adding `org_id, tipo, valor, pedido_ref, review_notes, reviewed_by, reviewed_at, paid_at, requested_at` to `adconnect.resgates_recompensa`. Schema-locked via inline `SET search_path = adconnect, public;` (prelude-equivalent for a single-product ALTER; the `noctusai_lib.sql.prelude` helper was not used — it requires schema-name strings unsuitable for hyphen-free schemas already locked by `001_adconnect.sql`).
- `products/adconnect/backend/tests/routers/test_rewards_router.py` — updated 1 seed (`cashback_pct`/`ativo` → `valor`/`ativa`); appended 3 regression tests (one per audit bug).
- `products/adconnect/backend/tests/services/test_rewards_engine.py` — updated 6 seed rules (`cashback_pct`/`ativo` → `valor`/`ativa`) + 2 assertions (`source_relatorio_id` → `source_relatorio_sellout_id`).

---

## 6 · Phases

### Phase 1 — Worktree preamble + audit re-read

Verified base includes `de045c3`. Bootstrap green. Disk OK. Audit report fully re-read.

### Phase 2 — Read fan-out

Greppped `RewardRuleOut|RewardLedgerEntry|RedemptionOut|source_relatorio_id|cashback_pct|ativo` across adconnect backend. Identified:
- `financial_service.py` has zero references (the brief's authorization list mentioned it but it turned out clean).
- `rewards_service.py` uses `cashback_pct` (3 ref) + `.eq("ativo")` (1 ref) + `source_relatorio_id` (5 ref incl. docstring).
- `routers/rewards.py` uses `.eq("ativo")` (1 ref).
- Tests use these names heavily — 6 dict seeds + 2 assertions.

### Phase 3 — R4 rename (schema + service + tests)

`source_relatorio_id` → `source_relatorio_sellout_id` everywhere it appears in `app/schemas/rewards.py` and `app/services/rewards_service.py` (including docstring). Test assertions in `test_rewards_engine.py` updated.

### Phase 4 — R1 dedup + service column-name fix

Deleted broken `RewardRuleOut` from `rewards.py`; rewrote `RewardRulesListOut` to use `list[dict[str, Any]]` (matches `admin.RewardRuleListOut` pattern). Dropped re-export from `app/schemas/__init__.py` (the `admin.py` re-export at line 97 was already canonical). Service + router switched `.eq("ativo")` to `.eq("ativa")` and `rule.get("cashback_pct")` to `rule.get("valor")`. Updated test seeds.

### Phase 5 — R3 table extension

Authored `migrations/003_resgates_recompensa_align.sql`. Added 9 `ADD COLUMN IF NOT EXISTS` clauses + a partial index on `org_id`. Did NOT use `noctusai_lib.sql.prelude("adconnect")` — the existing `002_invitations_accepted_columns.sql` skips it (no new schema established; the file is purely ALTER), so following the in-repo precedent. The inline `SET search_path = adconnect, public;` is equivalent for the ALTER-only case. Extended `RedemptionOut` with the 5 original-migration columns (`valor_total`, `metodo`, `observacoes`, `created_at`, `processed_at`) and marked schema-driven fields `Optional` so pre-backfill rows pass validation.

### Phase 6 — Regression tests

Three new tests in `tests/routers/test_rewards_router.py`:
- `test_rules_serializes_real_db_column_names` — seeds a row with `valor` + `ativa` + `created_at` + `updated_at`; asserts all four come through (R1 + R2 partial).
- `test_redemption_response_includes_pre_and_post_migration_columns` — seeds a full row with every schema field; iterates the 14 documented keys and asserts each is in the response body (R3).
- `test_ledger_carries_source_relatorio_sellout_id` — seeds a ledger row with the renamed key; asserts response has the renamed field (R4).

### Phase 7 — Verification

- `pytest products/adconnect/backend/` → **233 passed, 18 skipped** (230 baseline + 3 new).
- `noctus.dev.review --product adconnect` → **0 issues**.
- `bash scripts/verify-kb-sync.sh` → **GREEN**.

---

## 7 · Open questions / improvements (deferred)

1. **R2 (deferred)**: `RewardLedgerEntry` should add `expires_at` + `created_at` (DB has them; schema doesn't surface them). The `moeda` schema-only field stays — frontend uses it for display formatting. Filing as out-of-scope.
2. **Service writes nonexistent columns** to `recompensas_acumuladas`: `org_id`, `moeda`, `descricao` are in the insert payload but NOT in the table per migration `001_adconnect.sql:670-688`. This is the inverse of R3 — the service writes columns that don't exist. Mock builder accepts them; production would silently lose them (Supabase ignores unknown insert keys in lax mode). **Recommend follow-up**: either add these columns to `recompensas_acumuladas` OR strip them from the insert payload. Audit report did not flag this (it was scoped to response-side); flagging now as bystander observation per the "flag MCP-first / AST-first opportunities proactively" rule (logic-bystander variant).
3. **`SubmissionMode 'attachment'`** vs DB CHECK `'freeform'` — out of scope for this engineer (in `ADCO-SELLOUT-FIX`'s scope).

---

## 8 · Improvements found mid-flight

- Audit-report bug count is more nuanced than the dispatch brief: R1 said "rewards.py duplicate" but the SERVICE also uses the wrong column names (`cashback_pct`, `ativo`). Fixing only the schema would leave the service broken against production DB. Brief authorized service edits, so applied — but the connection between R1 (schema) and the service-column-name drift wasn't called out explicitly in the audit, only implicitly via "production rows that previously would 500-on-response-validation now serialize cleanly". Captured in findings.md.

---

## 9 · Verification commands

```bash
# Full test suite
cd products/adconnect/backend
PYTHONPATH="$REPO/seed/lib/backend:$REPO/seed/framework/backend:$PYTHONPATH" pytest -q
# → 233 passed, 18 skipped

# Keeper review
mcp__noctusai__noctus_dev_review --product adconnect
# → issues_found: 0

# KB sync
bash scripts/verify-kb-sync.sh
# → GREEN
```

---

## 10 · Commit

Single commit on branch `adco-response-model-rewards-fix-2026-05-11`. Author-staged only paths in §5. HEREDOC commit message with `Co-Authored-By: Claude Opus 4.7 (1M context)`.

---

## 11 · Change log

- 2026-05-11 — R4 rename `source_relatorio_id` → `source_relatorio_sellout_id` across schema + service + tests.
- 2026-05-11 — R1 dedup: deleted broken `RewardRuleOut` from `rewards.py`; `RewardRulesListOut` switched to pass-through dicts; service + router column-name fixes (`ativo`→`ativa`, `cashback_pct`→`valor`); test seeds aligned.
- 2026-05-11 — R3 migration `003_resgates_recompensa_align.sql` authored; `RedemptionOut` extended with 5 original-migration columns and marked schema-driven fields Optional for pre-backfill compatibility.
- 2026-05-11 — 3 regression tests added; baseline 230 → 233 green.
- 2026-05-11 — `noctus.dev.review --product adconnect` → 0 NEW issues. `verify-kb-sync.sh` GREEN.
