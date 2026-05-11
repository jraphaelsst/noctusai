# projects/response-model-silent-drop-audit · 2026-05-11

> **READ-ONLY AUDIT.** No product code edits. Output informs follow-up engineer dispatches.
> Trigger: `STRICT-HTTP-WAVE-1` surfaced `RedemptionOut` missing `org_id` (silently dropped from response pre-migration). Need a one-time pass over every `response_model=` to catch the same bug class on other routes.
> Branch: `response-model-silent-drop-audit-2026-05-11`. Base: `dfa6e3b`.

---

## 1 · Bug class restated

Pydantic v2's default `extra="ignore"` silently drops unknown fields on both the request and response sides. When a `response_model=` wraps a Pydantic class around a raw DB-row dict, every column the schema doesn't list is *dropped from the response* — the route returns 200, the row had the data, the client never sees it.

Tighten the schema (add missing fields) so the response contract matches the row shape. Mark intentional hides (PII, internal state) with a comment. Migrating to `StrictHttpModel` (`extra="forbid"`) is orthogonal — it catches the request side; the response side still drops silently because FastAPI builds the response from the row dict using `model_validate`, which still respects the model's extra-policy.

The migration to `StrictHttpModel` already happened across `adconnect / imobi-scheduling / media-scheduling` in Wave 1. This audit checks whether the *fields the schema declares* match the *columns the DB returns*.

---

## 2 · Survey — per-product `response_model=` count

| Product | `response_model=` uses | Notes |
|---|---:|---|
| adconnect | 35 | Audit target. Heavy DB-row return. |
| core | 1 | `SSOSessionResponse` — custom DTO, not DB row. Out of scope. |
| imobi-scheduling | 2 | Seed-skeleton `example_router` only. No real domain routes yet. |
| seed | 2 | Skeleton itself. |
| daily-life / dev-team / erp / mailing / media-scheduling / pf / therapy / youtube-crawler | 0 each | These products do NOT use `response_model=` at all — they return raw dicts/lists or use `success_response()` wrappers; no silent-drop risk via this mechanism. |
| **Total** | **40** | Effectively 35 in-scope (adconnect). |

The audit scope is dominated by adconnect. Other products that lack `response_model=` are immune to *this specific* bug class — they can have other shape bugs (e.g. service-layer dropping cols), but not the `response_model=`-mediated silent-drop.

> **Cross-product slip surfaced**: only adconnect uses `response_model=` heavily. This is itself an N=1 vs N=10 inconsistency — every other product returns raw dicts. Worth noting for a later "should we standardise on response_model=" decision (not in this project's scope).

---

## 3 · Cross-reference: schema fields vs DB columns

Schemas under `products/adconnect/backend/app/schemas/`; tables under `products/adconnect/backend/migrations/001_adconnect.sql`. Routes inspected for whether the row data they return is service-mediated (low risk) or raw `db.table(...).select("*").execute()` rows (high risk).

### 3.1 Schema-by-schema audit

| Schema | Table | Verdict | Notes |
|---|---|---|---|
| `RewardRuleOut` (rewards.py) | `regras_recompensa` | **REAL BUG** | Schema names `cashback_pct` (DB has `valor`), `ativo` (DB has `ativa`), `tipo: Literal["cashback","verba_mkt"]` (DB CHECK: `cashback_percentual|cashback_fixo|pontos`). Missing `created_at,updated_at`. Routes: `GET /rewards/rules` returns raw DB rows via `db.table(REGRAS_TABLE).select("*")`. Triple mismatch — column-name mismatch (silent drop of `valor`, `ativa`, `created_at`, `updated_at`) and Literal-value mismatch (response-validation would 500 on a real row). |
| `RewardLedgerEntry` (rewards.py) | `recompensas_acumuladas` | **REAL BUG** | Schema field `source_relatorio_id` (DB column is `source_relatorio_sellout_id`) — silent drop. Schema field `moeda` and `descricao` are NOT in the table (no impact — schema-only). Missing `expires_at`, `created_at`. Route `GET /rewards/ledger` returns raw rows. |
| `RedemptionOut` (rewards.py) | `resgates_recompensa` | **REAL BUG — DEEPER THAN org_id** | Wave-1 fix added `org_id`, but the table doesn't have `org_id`, `tipo`, `valor`, `pedido_ref`, `review_notes`, `reviewed_by`, `reviewed_at`, `paid_at`, `requested_at`, `requested_by`. DB columns are `id, distributor_id, requested_by, valor_total, metodo, status, observacoes, created_at, processed_at`. The schema is nearly entirely fictional vs the migration. **Action**: full reconciliation needed — either fix the schema OR ALTER the table. The insert in `request_redemption()` writes columns that don't exist (silent failure in real Supabase; mock builder accepts everything). |
| `SelloutOut` (sellout.py) | `relatorios_sellout` | **REAL BUG** | Schema names `periodo: str` — DB has TWO columns `periodo_inicio DATE NOT NULL` and `periodo_fim DATE NOT NULL`. Schema field `org_id` — DB has no `org_id` column on this table. SubmissionMode literal `["estruturado","nfe_xml","attachment"]` — DB CHECK is `('estruturado','nfe_xml','freeform')` (attachment≠freeform; the `submit_attachment` endpoint writes `'attachment'` which would violate the DB CHECK). Missing `created_at`, `updated_at`. **Compounding issue**: `sellout_service.submit_*` writes payloads with `org_id` and `periodo` keys that don't exist in the table — works only because mock builder ignores; production would 500 or silently drop on insert. |
| `OrderOut`, `OrderItemOut`, `CartOut`, `CartItemOut` (orders.py) | `pedidos / itens_pedido / carts / itens_carrinho` | **CLEAN** | All four schemas match their tables. Routes pass through `orders_service` / `cart_service` which return enriched dicts (`sku`, `nome`, `line_total` come from joins). Service-mediated. |
| `FaturaOut` (financial.py) | `faturas` | **CLEAN** | All 23 columns covered. Service-mediated. |
| `DistributorWithMetricsOut` (admin.py) | `distributors + computed metrics` | **INTENTIONAL_HIDE / EXPLICIT CARVE-OUT** | Declares `model_config = ConfigDict(extra="allow")` — explicit opt-out from StrictHttpModel, deliberately accepts unknown DB columns. Wave-1 documented this. |
| `RewardRuleListOut`, `AdminInvoiceListOut`, `AdminSelloutQueueOut` (admin.py) | various | **CLEAN — pass-through** | Typed as `data: list[dict[str, Any]]` — no schema validation, raw rows flow through verbatim. Intentional. |
| `DashboardMetricsOut`, `DashboardCounts`, `DistributorMetrics` (admin.py) | computed aggregates | **CLEAN** | Built explicitly by `admin_service.dashboard_metrics()` — not raw DB rows. |
| `RewardRuleOut` (admin.py) | `regras_recompensa` | **CLEAN** | Different class from rewards.py's `RewardRuleOut`. This one inherits from `RewardRuleIn` and lists every column (including `valor`, `ativa`). Use this one wherever you can — drop the rewards.py variant. |
| `MembershipOut`, `DistributorOut` (identity.py) | `distributor_memberships / distributors` | **CLEAN** | Match table. |
| `RewardLedgerOut`, `RewardRulesListOut`, `OrderListOut`, `FaturaListOut`, `SelloutListOut` | n/a | **CLEAN — wrappers** | List wrappers; risk lives in the entry schema, not the wrapper. |
| `ExampleOut`, `ExampleListResponse` (seed/imobi-scheduling) | placeholder `examples` table | **CLEAN — skeleton** | Service-mediated; placeholder schemas for scaffolded products. |
| `SSOSessionResponse` (core/sso.py) | n/a — Supabase auth response | **CLEAN — custom DTO** | Built explicitly via `return SSOSessionResponse(access_token=..., ...)`. |

### 3.2 Counts

- **Schemas surveyed**: 25 (across adconnect, core, seed, imobi-scheduling).
- **REAL_BUG mismatches**: 4 distinct schemas (`RewardRuleOut`-rewards.py, `RewardLedgerEntry`, `RedemptionOut`, `SelloutOut`).
- **INTENTIONAL_HIDE**: 1 (`DistributorWithMetricsOut` — explicit carve-out).
- **CLEAN**: 20.
- **AMBIGUOUS**: 0 — every mismatch traces to a concrete table-column comparison.

---

## 4 · REAL_BUG list — top 5 most actionable

Ranked by client visibility + ease of fix. Each item lists the file, line, what's silently dropped, and the recommended fix.

### #1 — `RedemptionOut` does not match `resgates_recompensa` at all (nuclear)

- **File**: `products/adconnect/backend/app/schemas/rewards.py:69-83` + `products/adconnect/backend/app/routers/rewards.py:101-155`
- **Schema fields**: `id, org_id, distributor_id, tipo, valor, pedido_ref, status, review_notes, reviewed_by, reviewed_at, paid_at, requested_at, requested_by`
- **Table columns** (`migrations/001_adconnect.sql:717-727`): `id, distributor_id, requested_by, valor_total, metodo, status, observacoes, created_at, processed_at`
- **Drop-from-response**: `metodo`, `valor_total`, `observacoes`, `created_at`, `processed_at` are all in the DB row but absent from the schema → silently stripped.
- **Drop-from-insert** (writes to nonexistent columns): `tipo, valor, pedido_ref, review_notes, reviewed_by, reviewed_at, paid_at, requested_at`.
- **Why it ranks #1**: every `request_redemption` and `process_redemption` call is broken against the real DB shape. Wave 1's `org_id` patch papered over a single column on a schema that has nearly zero correspondence to the migration. Either the schema is wrong or the migration is missing fields. **Tabling for follow-up engineer dispatch** with explicit decision: "fix schema to match table" (cheap) OR "ALTER TABLE to match schema" (expensive — likely the intent, since the schema is richer and matches the route's payload).

### #2 — `RewardRuleOut` (rewards.py) ships wrong column names

- **File**: `products/adconnect/backend/app/schemas/rewards.py:17-31` + `products/adconnect/backend/app/routers/rewards.py:88-98`
- **Schema names**: `cashback_pct` (DB: `valor`), `ativo` (DB: `ativa`), `tipo` Literal `["cashback","verba_mkt"]` (DB CHECK: `cashback_percentual|cashback_fixo|pontos`)
- **Drop-from-response**: `valor`, `ativa`, `created_at`, `updated_at` (all in DB row, none in schema).
- **Side-effect**: response-side Literal mismatch on `tipo` → 500 ResponseValidationError when a real DB row hits the route (because the table allows `cashback_percentual` but the schema rejects that value). Tests pass because the mock seed data uses `tipo: "cashback"`.
- **Why it ranks #2**: dual fault — silent drop of legitimate fields AND a Literal mismatch that 500s on production rows. Recommended fix: align schema names with table OR delete the duplicate and point `GET /rewards/rules` at `admin.RewardRuleOut` (the inherits-from-`RewardRuleIn` variant which is correct).

### #3 — `SelloutOut.periodo` collapses two DB columns

- **File**: `products/adconnect/backend/app/schemas/sellout.py:47-67` + `products/adconnect/backend/app/services/sellout_service.py`
- **Schema field**: `periodo: Optional[str] = None`
- **DB columns**: `periodo_inicio DATE NOT NULL`, `periodo_fim DATE NOT NULL`
- **Drop-from-response**: both `periodo_inicio` and `periodo_fim` are dropped silently → client can never display the period range, just a `null` field.
- **Other mismatch**: `SubmissionMode` Literal includes `"attachment"`; DB CHECK is `freeform`. The `submit_attachment` route writes `'attachment'` to the DB → CHECK violation in production. Mock builder doesn't enforce CHECK constraints.
- **Recommended fix**: split schema to `periodo_inicio: date` and `periodo_fim: date`; rename `submission_mode='attachment'` writes to `'freeform'` everywhere (router + service + tests).

### #4 — `RewardLedgerEntry.source_relatorio_id` mis-named

- **File**: `products/adconnect/backend/app/schemas/rewards.py:34-45` + `products/adconnect/backend/app/routers/rewards.py:66-85`
- **Schema field**: `source_relatorio_id`
- **DB column**: `source_relatorio_sellout_id`
- **Drop-from-response**: every ledger entry that originated from an approved sellout has its source-link dropped to `null` in the response → frontend can't link the accrual back to the sellout report.
- **Other gaps**: `expires_at`, `created_at` missing from schema.
- **Recommended fix**: rename schema field to `source_relatorio_sellout_id` and add the two missing date fields.

### #5 — `RedemptionOut.tipo` is also a Literal mismatch (bundled with #1, but worth calling out for the follow-up dispatch brief)

- The schema's `tipo: Literal["cashback", "verba_mkt"]` is independent of #1's structural mismatch. Even if a `tipo` column existed in `resgates_recompensa`, this Literal would be a new arbitrary constraint not present in the table. Bundle the fix with #1.

---

## 5 · INTENTIONAL_HIDE list

| Class | Reason |
|---|---|
| `DistributorWithMetricsOut` (admin.py) | Explicit `model_config = ConfigDict(extra="allow")`. Documented in Wave 1 PROJECT.md §6 and in `seed/lib/backend/noctusai_lib/api/schemas.py` as the canonical carve-out. Surfaces unknown DB columns rather than dropping. |

---

## 6 · AMBIGUOUS list

None. Every mismatch resolved to a concrete REAL_BUG verdict. The `accrued_at` field on the ledger could be argued ambiguous (some legacy code may use `created_at`) but the DB defines `accrued_at TIMESTAMPTZ NOT NULL DEFAULT now()` so the schema aligns there.

---

## 7 · Follow-up dispatch recipe

The architect should dispatch **four** focused fixer-engineers in parallel (no file overlap — separate schema files for adconnect, all `products/adconnect/backend/app/schemas/`). Each engineer handles ONE schema:

1. **Engineer R1 — `RewardRuleOut` (rewards.py)**: rename `cashback_pct→valor`, `ativo→ativa`, fix `tipo` Literal to `["cashback_percentual","cashback_fixo","pontos"]`, add `created_at` + `updated_at`. Update consumers if any reference the old field names. Frontend hook tightening tracked as a follow-up.
2. **Engineer R2 — `RewardLedgerEntry`**: rename `source_relatorio_id→source_relatorio_sellout_id`, add `expires_at` + `created_at`, drop the schema-only `moeda` field (or keep with a comment if used by frontend).
3. **Engineer R3 — `RedemptionOut` + `resgates_recompensa`**: USER-decision-required (schema vs migration). Brief should ask: do we extend the table (ALTER MIGRATION + new fields like `tipo`, `valor`, `pedido_ref`, `review_notes`, `reviewed_by`, `reviewed_at`, `paid_at`, `requested_at`) OR shrink the schema to match the current table (`valor_total`, `metodo`, `observacoes`, `created_at`, `processed_at`)? The route's `request_redemption` payload SUGGESTS the schema is the intended shape and the migration is incomplete. **Block this engineer until user confirms direction**.
4. **Engineer R4 — `SelloutOut` + service**: split `periodo` into `periodo_inicio` + `periodo_fim`, rename `'attachment'` → `'freeform'` in the SubmissionMode literal and at the writers, drop the schema-only `org_id` field (or migrate the table). Compounding bug: the service inserts `org_id` and `periodo` to non-existent columns — production is broken; mocks paper over. **Coordinate with the migration owner.**

Wave-2 strict-http migration to other products is unblocked by this audit — those products don't use `response_model=` so the silent-drop class doesn't apply to them.

---

## 8 · Seed-side opportunity (KB §3a)

This bug class is detectable by static analysis: for each route declaring `response_model=X` where the route body returns `db.table(...).select("*").execute().data`, the schema's fields should be a superset of the migration's column list for that table. A keeper detector `check_response_model_has_db_columns` could parse `*.py` AST + the per-product migrations and warn on the diff.

- **N=4 confirmed REAL_BUG instances within a single product** → easily meets the "would a Fake here exercise different code than the Real" exemption test inversion. **N=4 within adconnect alone** justifies a seed-side detector.
- The detector belongs in `seed/keeper/checks/` or `mcp/noctusai/keeper_checks/`, exposed via `noctus.dev.review` and the per-PR keeper run.
- **File a follow-up project**: `seed-keeper-check-response-model-vs-migration` after this audit's four fixer-engineers land. Don't bundle — keeper-detector authoring is distinct from per-product schema fixes.

---

## 9 · Findings (text — §17.6.1 return-as-text)

### errors
- None — read-only audit; no commands errored.

### mistakes-slips
- Initial framing assumed `response_model=` is widespread. It isn't — only adconnect uses it heavily. This means the audit is much smaller than expected (effectively a single-product audit), but the bug class is also narrower than feared at the platform level.
- I almost stopped after confirming `RedemptionOut.org_id` was the only fix needed in `rewards.py`. Reading the migration revealed `RedemptionOut` is a near-total mismatch to its table — the `org_id` patch was the tip of an iceberg.

### lessons
- **Strict-HTTP migrates the schema-side defense; it does NOT validate that the schema matches reality.** Wave 1 added `extra="forbid"`, which catches MISROUTED CLIENT keys. It does nothing to catch SCHEMA-vs-MIGRATION drift on the response side. The bug class StrictHttpModel reveals (PROJECT.md line 130: "exactly the bug class StrictHttpModel reveals, on the response side") only fires when a column EXISTS but is dropped. It does NOT fire when a schema FIELD doesn't correspond to any DB column — those are silently `None`.
- **A schema-correctness keeper is orthogonal to a strict-http keeper.** Two different rules at two different layers.
- **The `response_model=` adoption pattern is uneven.** 35 in adconnect, 0 in eight other products. This is itself an inconsistency worth surfacing — either every product should use it (and audit drift) or none should (and rely on success_response wrappers).

### interesting-findings
- `RedemptionOut` is more broken than the Wave 1 fix indicated: 8 schema fields don't exist in the table, and 5 table columns are silently dropped from responses. The `request_redemption` route writes a payload with nonexistent columns — production-only failure (mocks accept anything).
- `SelloutOut.SubmissionMode = Literal[..., "attachment"]` while `relatorios_sellout` CHECK allows `'freeform'`. The `submit_attachment` route would CHECK-violation in production. Tests pass because mock builder doesn't enforce CHECK.
- Tests can't catch any of these because they all rely on `MockSupabaseClient` (or `MockRequestBuilder`), which doesn't model column existence or CHECK constraints. **Adopter for the seed: a "MockSchemaValidator" mode where MockSupabaseClient knows the table shape from the migration and rejects unknown columns + violates CHECKs**. Higher fidelity tests → catches these bugs.
- The duplicate `RewardRuleOut` (one in `rewards.py`, one in `admin.py`) — the `admin.py` variant is correct, the `rewards.py` one is broken. N=2 same-name divergent definitions → file/triage.

### knowledge-pieces
- Adconnect uses `db.table(...).select("*").execute()` heavily in routers, returning raw row dicts to FastAPI. Other products route through services that return pre-shaped dicts.
- The strict-http migration in Wave 1 affected 81 schema classes across 3 products — but for adconnect, only the request-side schemas got real protection from misrouted keys. Response-side bugs continue to live until a separate audit (this one) catches them.
- `mcp/noctusai` keeper detector authoring is straightforward: AST-walk router files for `response_model=X`, AST-walk schema files for class `X`, parse migrations with a simple `CREATE TABLE` regex, diff. The detector could also surface duplicate class names across schema files (the rewards/admin `RewardRuleOut` clash).

---

## 10 · Verification

- No code changes.
- All inspection was via `Read` + `grep`. AST parsing not strictly required for this audit (column comparison is regex-tractable).
- Audit accuracy depends on the migration file being canonical; spot-checked `001_adconnect.sql` against schemas; `002_invitations_accepted_columns.sql` patch is irrelevant (only modifies invitations table, which has no `response_model=` route).
