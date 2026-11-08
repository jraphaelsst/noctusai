# Contract — "Uso e custo de IA" (core `/admin/uso`) · v1 · 2026-11-08

Owner-approved mockup: https://claude.ai/artifact/JQdErx9ASLvrSis7AEUuuE.
Authored by the architect and pinned by tech-lead noctusai-51.
The BE slice commits this file to the repo at `products/core/docs/ai-usage-contract.md`. It must not go under CONTRACTS/: `.gitignore` matches that path on case-insensitive macOS.

**Owner-level decisions (tech-lead, recommended path):**
- Currency is USD only.
- The two sources are never summed.
- The default view is "Comparar".
- The BRL "Agentes da plataforma" section moves to `/admin/operacao/custos`.
- The rate-limits table ships (endpoint 6).
- Opus vs Sonnet covers dispatched slices only.

## 0. Existing surface (origin/dev) and what happens to it
`lib/usage.ts:174-196` calls five endpoints. All use `require_platform_admin_dep` and return bare objects (no envelope).
- `GET /api/admin/llm-usage`: **stays**. Its UI section moves to `/admin/operacao/custos`.
- `GET /api/admin/usage/fx`: **stays**.
- `GET /api/admin/usage/machine` and `/usage/jobs`: **stay**. Their UI moves to a "Máquina e jobs" tab under `/admin/operacao/*`.
- `GET /api/admin/usage/dev`: **VESTIGIAL**. It is replaced by `/ai/usage?source=ledger`. It gets a `Deprecation` header once the new FE ships, and slice S4 removes it.

## 1. Endpoints
- Prefix: `/api/admin/usage/ai`.
- Tier: **platform**. Dependency `require_platform_admin_dep`, which is already in `DEP_TIERS`.
- No token: **strict 401**.
- Non-admin: **403** `{"detail":{"code":"platform_admin_required"}}`.

**Common query params:**
- `source` ∈ `anthropic|ledger`. It is REQUIRED. There is one source per call, so "Comparar" makes two calls.
- `from` and `to` are `YYYY-MM-DD`, UTC, inclusive.
- `bucket` ∈ `day|week`.

**Typed 422 errors** (`detail.code`): `range_invalid`, `range_too_long` (more than 31 days), `range_before_coverage` (before 2026-01-01), `filter_not_supported_by_source`, `group_by_not_supported_by_source`.

**Source unavailable:** returns **200** with `source.status="unavailable"` and empty arrays. It is never a 5xx. A real failure returns 500 `{detail:{code,message}}`.

**`SourceStatus`** is embedded as `source` in every response:
```
{id:'anthropic'|'ledger', status:'unavailable'|'ok'|'stale'|'error',
 reason_code:null|'individual_org'|'no_admin_key'|'http_4xx'|'http_5xx'|'schema_drift',
 data_refreshed_at:ts|null, last_sync_at:ts|null, last_success_at:ts|null,
 coverage_from:date|null, coverage_to:date|null, final_through:date|null, is_estimate:bool}
```
- `stale` means more than 24h since `data_refreshed_at` (anthropic) or since `last_sync_at` (ledger).
- `is_estimate` is true for the ledger, whose costs are "equivalente API".

**Endpoints:**
1. `GET /sources` returns `{anthropic:SourceStatus, ledger:SourceStatus}`.
2. `GET /usage`
   - `group_by`: anthropic allows `model|token_type|service_tier|context_window|workspace|api_key`; ledger allows `model|agent|ambiente|origem`.
   - Filters: `model`, `workspace_id` and `api_key_id` (anthropic only), and `ambiente`, `origem` and `agent` (ledger only).
   - Response: `{source, window:{from,to,days}, bucket, group_by, totals:Tok, series:[{bucket_start:date, key:str|null} & Tok], groups:[{key,label} & Tok]}`.
   - `Tok = {input_tokens, uncached_input_tokens, cache_write_tokens, cache_read_tokens, output_tokens, requests:int|null, web_search_requests:int|null}`.
   - A field the source doesn't record is `null`, never 0. Empty buckets are omitted.
3. `GET /cost`
   - Same params as `/usage`, plus `group_by=cost_type` (anthropic only).
   - Cost fields: `{amount_usd:number, list_amount_usd:number|null}`.
   - `cost_type` ∈ `tokens|web_search|code_execution|session_usage`.
4. `GET /spend?source&month=YYYY-MM`
   - Response: `{source, month, derived_spend_usd:number|null, is_final:bool, daily:[{day,amount_usd}], spend_limit:null, credit_balance:null, unavailable_fields:['spend_limit','credit_balance','invoices']}`.
5. `GET /deliveries?from&to&model&agent&ambiente&bucket=week`
   - Ledger only; any other `source` returns 422.
   - `compare:[{model, n, small_sample:bool(n<10), q_weighted_mean, first_pass_rate, cost_usd_median:number|null, cost_is_estimate:true, wall_s_median|null, duration_min_median|null}]`.
   - `trend:[{week_start, model, n, …same metrics}]`. Gaps are omitted, never zero.
   - `rows:[{slug, agent, model, ambiente, ts, q_weighted, first_pass, rework_commits, tokens|null, cost_usd|null, wall_s|null, duration_minutes|null, outcome}]`.
6. `GET /rate-limits` (anthropic only)
   - Response: `{source, limits:[{scope:'org'|'workspace', workspace_id|null, model_group, metric, limit:int}], peak_pct:null}`.

## 2. DB tables (core migration 112 (111 is taken by feat/sso-s2-session-registry))
Every table:
- lives in `public`;
- has `ENABLE ROW LEVEL SECURITY` with NO policies;
- has `REVOKE ALL … FROM anon, authenticated`;
- carries `COMMENT … 'tier:platform'`.

Writes are service-role only; reads go through the BE only. Never PostgREST-exposed.

| Table | Key | Columns |
|---|---|---|
| `ai_anthropic_usage_daily` | PK `(day, dims_key)` | `dims_key` = sha1 of 5 dimensions (`''` for null): `model, workspace_id, api_key_id, service_tier, context_window`. Plus `uncached_input, cache_write_5m, cache_write_1h, cache_read, output_tokens` (bigint), `web_search_requests, requests` (int), `data_refreshed_at, is_final, synced_at` |
| `ai_anthropic_cost_daily` | PK `(day, dims_key)` | Dimensions `model, workspace_id, api_key_id, cost_type, token_type`. `amount_cents, list_amount_cents` are `numeric(20,6)` (the API returns decimal CENTS). `currency CHECK='USD'`, plus `data_refreshed_at, is_final, synced_at` |
| `ai_anthropic_rate_limits` | PK `(scope, workspace_id_key, model_group, metric)` | `limit_value int, synced_at` |
| `ai_source_sync_runs` | identity id | `source, endpoint, window_from, window_to, started_at, finished_at, status ok/error/unavailable, reason_code, http_status, rows_written, rows_deleted, data_refreshed_at`. `SourceStatus` is derived from this table |
| `dev_deliveries` | PK `line_hash`; UNIQUE `(slug, agent, ts)` | `slug, branch, sha, agent, model (canonical), planner_model, ts, q jsonb, q_weighted, first_pass, rework_commits, tokens, tool_uses, wall_s_measured, wall_s_self_reported, duration_minutes, outcome, cost_usd, cost_is_estimate, price_version, ambiente, origem, ingested_at` |
| `dev_telemetry_claude` (expand only) | PK unchanged | `ADD ambiente text NOT NULL DEFAULT 'local' CHECK in (prod,local,ci)` and `ADD origem text NOT NULL DEFAULT 'desconhecido' CHECK in (api_key,assinatura,desconhecido)` |

**Revisions are replace-window**, never a bare upsert (a bare upsert keeps rows that a revision removed):
- In ONE transaction, delete the window's days and insert the freshly pulled rows.
- Commit only after every page is fetched.
- `is_final` is true once the day's month end + 7 days is earlier than `data_refreshed_at`.

## 3. Sync job (core prod container)
- **Registration:** the seed scheduler, in `products/core/backend/app/scheduler.py`: `register("anthropic_usage_snapshot", …, cron="20 */6 * * *", misfire_grace_time=3*3600)`.
- **Catch-up:** at startup, if coverage has a gap, fill it.
- **Backfill:** from 2026-01-01 in chunks of at most 31 days, resuming from the last `ok` window, with backoff on 429.
- **Revision window:** every run re-pulls the current month; until day 7 it also re-pulls the previous month.
- **Endpoints:** the beta `/v1/organizations/analytics/usage` and `/analytics/cost`, with header `anthropic-beta: analytics-usage-cost-2026-08-24`. Rate limits come from `/v1/organizations/rate_limits`.
- **Key:** `ANTHROPIC_ADMIN_API_KEY` from the existing secrets path. It is never logged, never returned, and never sent to the FE.
- **Unavailable** (no key, or a 403 for an individual org) is recorded as status `unavailable` with a `reason_code`. Platform admins are notified once, on the status change.
- **A failure RAISES.** The `scheduler_runs` ledger records `error` and `notify_platform_admins` fires (`scheduler_job_failed`).
- **Fix-on-contact:** `storage_cost_snapshot_job` (`scheduler.py:120-127`) catches its exception and returns `{"error":…}`, so it may be recorded as ok, which is a silent error. Verify it and fix it in this slice.
- **Adapter:** `anthropic_client` ships Protocol + Fake + Real + factory. The Real adapter is tested against recorded fixtures, since live calls are impossible until the account becomes an org.

## 4. Ingest (ledger → `dev_deliveries`)
Extend the existing writer with `noctus.dev.usage_eval action=sync_deliveries` (`mcp/noctusai/tools/noctus/dev/usage_eval.py`). It must NOT be a second tool.
- **Inputs:** `since`, `until`, `dry_run`. It reads `slice-scores.ndjson` and `dispatch-budget.ndjson` from `origin/ledgers` via `read_dual`.
- **Dedup:** `line_hash` = sha256 of the canonical JSON line, plus the natural key `(slug, agent, ts)`.
- **Join:** a budget row matches a score on `(slug, agent)` within ±15 minutes. An unmatched row is kept with null scores.
- **Model ids:** canonicalized via the seed model registry. An unknown model keeps its raw id and is counted in `unknown_model`; it is never dropped.
- **Tokens:** null stays null.
- **Cost:** computed only when tokens exist, using the seed `estimate_cost_usd` with the 90/10 split. Such rows carry `cost_is_estimate=true` and a `price_version`.
- **`ambiente`:**
  1. `NOC_AMBIENTE` wins if set.
  2. Else `CI` or `GITHUB_ACTIONS=true` means `ci`.
  3. Else a host found in the fleet inventory (derived from it, never a hand-kept list) means `prod`.
  4. Else `local`.
- **`origem`:** `api_key` or `assinatura` ONLY when the session auth mode is readable; otherwise `desconhecido`. Never guess. Verifying whether the transcripts record the auth mode is part of the slice.

## 5. Slices
- **S0+S1 BE** (backend-engineer, one branch):
  - S0: migration 112.
  - S1: `routers/admin_ai_usage.py` and `services/ai_usage/{anthropic_client,snapshot,reports}.py`, plus the scheduler registration, one `include_router` line in `main.py`, and this contract committed to the repo.
  - Collision: `main.py` also changes in feat/core-sidebar-modules, but only additively (C2).
- **S2 tooling** (tooling-engineer): `usage_eval.py` and its tests. C1. It needs S0's table to write; dry-run works before that.
- **S3 FE** (frontend-engineer, dispatched AFTER feat/core-sidebar-modules lands):
  - Rewrite `AdminUsoCustos.tsx` → `pages/admin/uso/*`, add the new hooks in `lib/usage.ts`, and move the BRL section and Máquina/Jobs into `AdminOperacao`.
  - The route goes in `src/admin/routes.ts` and the label in `navConfig.ts`, the files that branch introduces.
  - Seed adds `ChartTableToggle` and `DateRangePreset`; everything else is consumed from seed (StatTile/Row, ChartCard, BarChart stacked, LineChart, FilterBar, SectionTabsPage, QueryErrorState, EmptyState, Skeleton).
  - Group-by on the Anthropic side is trimmed to the 5-dimension grain (no agent/environment there).
- **S4:** remove `/usage/dev`.

## 6. Tests (both sides assert THIS contract)
- Strict 401 and 403.
- 422 for every typed code.
- Fake-adapter tests for `unavailable`, `stale` and `replace_window_drops_revised_rows`.
- null-not-zero for unrecorded fields.
- `check_access_tier_routes/tables` green.
- One E2E shape check against the live route.

## 7. As built (feat/ai-usage-be, 2026-11-08) — these override §1–§2 where they differ
1. **403 body is flat.** The seed handler flattens `require_platform_admin_dep`, so the body is `{"detail": "<message>", "code": "platform_admin_required"}`. Consumers read the top-level `code` on 403. The 422 and 500 bodies stay `{detail:{code,message}}`.
2. **`/cost` group_by** (anthropic) = `model|token_type|workspace|api_key|cost_type`. The cost table has no `service_tier`/`context_window`, so those return 422 `group_by_not_supported_by_source` on `/cost`. They remain valid on `/usage`.
3. **422 validation order:** `range_invalid` → `range_before_coverage` → `range_too_long`.
4. **Replace-window** is executed by three SECURITY INVOKER RPCs, `ai_replace_anthropic_{usage_window,cost_window,rate_limits}` (EXECUTE granted to service_role only). PostgREST cannot delete+insert in one transaction.
5. **Scheduler job id** `anthropic_usage_snapshot`, cron `20 */6 * * *`. Startup catch-up is not wired; each 6-hourly run fills gaps (misfire grace 3h).
6. **Rate limits:** org scope only for now; no workspace rows.
