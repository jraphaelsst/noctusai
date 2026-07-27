# meta-ads-console-2026-07 — Meta Ads console inside social-wiring

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: operator needs his own Meta ad campaigns in-house — structured as Meta structures them, but with a materially better UI, real time-series history, an explainable change log, and financial reporting.
> Decision: **read-only ads console on a System-User token; seed-build the Marketing-API read surface first (it is NOT shipped); writes + DM-attribution deferred behind named triggers.**

## Origin

2026-07-21 interview. The Meta integration (FB/IG read, content, comments, insights) is live in `social-wiring`; a parallel agent is currently wiring IG DMs. The operator runs paid traffic to boost his own campaigns and wants that spend surfaced in-platform: campaign → ad set → ad hierarchy, objective-appropriate KPIs, spend/pacing financials, time-series evolution, and an intra-day-accurate record of when campaigns were started/paused/restarted.

Pre-flight audit of the seed found the **read** side of the Marketing API largely absent despite the write side (`create_ad_campaign` / `create_ad_set` / `create_ad_creative` / `create_ad` / `update_campaign_status` / `update_ad_set_budget`) being present. Per the **verify-the-seed-ships-it** gate, this is a *seed-build + consume* initiative, not the pure consume slice it looked like at first sight.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| **T0** | ✅ **FIRED 2026-07-21.** Parallel meta-DMs work landed on `dev` (`0c453179`); DM initiative paused by operator at S3. Tree clean, no orphan branch, no salvage needed. | `origin/dev` tip `d5b74c38`; `git status` clean | Was blocking (no concurrent git ops in one checkout). Now clear — W1 may branch. |
| **T1** | System-User token with `ads_read` present in the credential vault | `meta` integration account resolves a token whose `/me/permissions` includes `ads_read`; `act_<id>` reachable | Unblocks every live verify-recipe. Until then W1 verifies against the Fake adapter only. |
| **T2** | Pixel audit confirms purchase / value events firing | `ad_insights` `action_values` returns non-empty for ≥1 campaign | Lights up ROAS / purchase-value tiles, which are hidden by default under objective-aware KPIs. |
| **T3** | DM ingestion live **and** ≥30 days of ads snapshots accumulated | `ig_dm` conversations table non-empty ∧ `ads_insight_snapshots` spans ≥30 days | Phase 2 spend↔conversation attribution becomes statistically meaningful. |
| **T4** | Operator wants to pause/resume/re-budget from our UI | Explicit user request | Fires the `ads_management` App-Review path (a *distinct* gate from `ads_read`). |
| **T5** | A second org / client ad account needs connecting | Any non-owner ad account requested | Fires the OAuth + App-Review path; the System-User token is single-business by construction. |
| **T6** | `leads_retrieval` scope granted on the System-User token | `/me/permissions` includes `leads_retrieval`; `{form_id}/leads` returns records instead of `(#200)` | Unlocks the per-lead RECORDS (name/phone/email + qualifying answers) in the Leads subtab. Form inventory + schema + counts already ship WITHOUT it. |

**Today's status**: T0 ✅ fired · **T1 ✅ FIRED 2026-07-23** (live System User token validated — see below) · T2 ✅ **resolved: N/A** (this account is lead-gen, not purchase — no ROAS to light up; objective-aware KPI design absorbs it) · T3 blocked (DM initiative paused) · T4–T5 not fired · **T6 not fired** (token lacks `leads_retrieval`; Leads subtab ships forms+schema+counts, records path built + gated 2026-07-27).

### ✅ T1 FIRED — live validation against the real account (2026-07-23)

Operator supplied a **System User token** (Facebook user `Raphael`, id `122134702173150635`). Validated every W1 method against live Graph v21.0. **Token is NOT stored in git** — held in-session only; must be Fernet-vaulted at W2 wiring time via the `meta` integration account, never committed.

**Permissions granted** (both read AND management — v1 uses read only): `ads_read`, `ads_management`, `read_insights`, `business_management`, `pages_show_list`, `pages_manage_ads`, `instagram_manage_messages` (← note: DM scope also present), + full IG/pages/whatsapp suite. **No App Review wall** — own-asset System User reads work exactly as the roadmap predicted. The DM initiative's Business-Verification blocker does **not** gate ads.

**The account (resolves O1):**
| Fact | Value |
|---|---|
| Ad account | `act_873947475957808` — "One Consultoria Imobiliária" |
| Currency | **BRL** |
| Timezone | **America/Sao_Paulo** (store snapshots against the *Meta* day in this tz, per O1) |
| Money fields | **cents** — `amount_spent: 674426` = R$6.744,26 lifetime; `balance: 12519` = R$125,19; `spend_cap: 50000000` = R$500.000 |
| Account status | `1` (active) |

**Every W1 method confirmed live:**
- `list_ad_accounts` → 1 account, all fields populated correctly, `act_` prefix present (mapper strips it).
- `list_ad_campaigns` → real campaigns, mostly `OUTCOME_LEADS` (real-estate Instant Forms, "SENSEYS"), some `OUTCOME_TRAFFIC`/`OUTCOME_ENGAGEMENT`, mix of ACTIVE/PAUSED. **Zero purchase campaigns → confirms objective-aware KPI was the correct call; a fixed ROAS tile would be dead on every card.**
- `ad_insights` account-level `last_30d` → **32 conversion metrics in the `actions` array** — the exact data the old method silently dropped (gap #4). Highlights: `lead = 320` (→ ~R$27 CPL on R$8.643,45 / 30d), `link_click = 5673`, and 🎯 **`onsite_conversion.messaging_conversation_started_7d = 26`** — the Phase-2 DM-attribution metric is present in the payload TODAY.
- `ad_insights_series` `time_increment=1` → clean N-rows-per-day (7 days → 7 rows), ~R$380/day.
- `list_activities` → live change log. **Confirmed: rows have NO `id` field** (W1's synthesized composite key was correct); `extra_data` is a JSON string with `old_value`/`new_value` (as assumed); actors include **real humans** ("Leonardo Salomão") AND "Meta" system events; `update_ad_run_status` rows carry `"Análise pendente" → "Ativo"` transitions — the "who changed what, when" layer, including Meta-UI-side edits, for free.

**O3 (activities retention) — partially resolved:** the `since`/`until` params are honored and the edge paginates. One month of this account = **500 events in a single page** with a `next` cursor continuing further back. So retention is NOT the constraint (goes well past 30d); **volume + pagination** is. The 12-month activity backfill is reachable but chunky (est. thousands of events/yr) — W2.3 must page defensively, not assume one call. Exact retention floor still unmeasured (would need to page to exhaustion); not worth the API spend now — treat "≥ several months, paginated" as the working fact.

### 🔴 Shared-gate risk inherited from the DM initiative (2026-07-21)

`ig-login-messaging-migration-2026-07.md` was paused **not on code** — S1 + S2 shipped green — but on **Meta-account gates: App Review → Advanced Access → Business Verification**. If Business Verification is still pending on this business, it may also gate Marketing API access.

**Why ads should still be materially less gated:** the DM blocker is reading *other people's* inboxes (inherently Advanced Access). Here the operator **owns the ad account**, and own-asset reads via a System User token in the owning Business Manager are the least-gated path Meta offers. Marketing API *Development Access* already permits reading ad accounts you hold a role on.

**Honest position:** unproven until W0 runs. This is precisely why W1 is built adapter-first against the Fake — the same sequencing that got the DM initiative's S1 shipped despite the live gate. **No wave's completion claim may depend on T1 until T1 actually fires.**

> **Every slice carries TWO recipes.** A *test-recipe* (unit/CI green at the module boundary) is **not** a *verify-recipe* (proof against LIVE state — Graph reachable, snapshot row actually written, route returns real numbers, page shows non-zero data). Tests-green ≠ verified-in-production.

## Decisions taken at interview (2026-07-21)

| Question | Decision |
|---|---|
| Auth path for `ads_read` | **System User token** in Business Manager. Bypasses App Review for owned assets. |
| "products inside campaigns" | **The Meta ad hierarchy** — campaign → ad set → ad → creative. Not Commerce-catalog products. |
| Write scope | **Read-only v1.** No mutations; `ads_management` deferred to T4. |
| Nav shape | **Third "Anúncios" network** in the MetaDashboard toggle (true campaign totals) **+ a compact top-ads strip** inside `IgVisaoGeral` / `FbVisaoGeral`. |
| Metric history | **Daily snapshot table** (mirrors `020_instagram_metric_snapshots`) — we own the series. |
| Status history | **Append-only change-log table fed from `act_/activities`** — daily snapshots cannot capture same-day activate→pause→reactivate. |
| Change-log scope | **Ingest all activity event types**, filter in the UI. Storage is trivial; re-backfill is not. |
| Financial metrics | Spend/CPM/CPC/CTR **+** conversions/CPA/ROAS **+** budget-vs-actual pacing **+** account totals & currency. |
| KPI rendering | **Objective-aware** — universal tiles always; objective-specific tiles swap on `campaign.objective`; ROAS only when `action_values` non-empty. |
| Ad accounts | **One** — the operator's own. `list_ad_accounts` still built (discovery + currency/timezone metadata). |
| Sync | **Scheduled daily job + manual "Sincronizar agora"**; first run backfills **12 months** via `time_increment=1`. |
| Reporting | Period comparison · CSV export · PDF export · saved views. |
| Charts | Spend-with-change-markers · multi-campaign comparison · placement split · funnel. |
| DM attribution | **Phase 2** — plan the seam now, build later. |

## Evidence: what the seed actually ships (audited 2026-07-21)

`seed/lib/backend/noctusai_lib/integrations/meta/` — 4,564 LoC across 8 modules.

**Present (write side):** `create_ad_campaign` · `create_ad_set` · `create_ad_creative` · `create_ad` · `update_campaign_status` · `update_ad_set_budget` · types `AdCampaign` / `AdSet` / `AdCreative` / `Ad` / `AdInsights` / `CampaignSpec` / `AdSetSpec` / `AdCreativeSpec` / `AdSpec` · Fake-adapter parity · `test_meta_ads_management.py`.

**Present (read side):** `list_ad_campaigns(ad_account_id)` · `ad_insights(object_id, level, date_preset)`.

**MISSING — the W1 build:**

| Gap | Detail | Evidence |
|---|---|---|
| `list_ad_accounts()` | No `me/adaccounts` call anywhere. `ad_account_id` is a caller-supplied argument with no discovery path. | `grep -rn "adaccounts" seed products` → 0 hits |
| `list_ad_sets()` / `list_ads()` | **Read** methods absent — only `create_*` exists. Cannot render the hierarchy. | `oauth_adapter.py:1060,1145` are creates |
| `ad_insights` time control | Signature is `(object_id, level, date_preset)`. No `time_range`, no `time_increment`, no `breakdowns`, no `action_attribution_windows`. | `oauth_adapter.py:970-976` |
| `ad_insights` row handling | Reads `rows[0]` only. With `time_increment=1` a 365-day pull returns 365 rows — 364 silently discarded from `metrics` (they survive in `raw`). | `oauth_adapter.py:996-1003` |
| `actions` / `action_values` | `metrics` flattens via `float(val)` inside `try/except (TypeError, ValueError): continue`. `actions` is a list-of-dicts → **always skipped**. Every conversion metric is invisible to `metrics`. | `oauth_adapter.py:997-1002` |
| `list_activities()` | No `act_/activities` call. The change log has no source. | `grep -rn "activities" seed` → 0 hits |
| `AdAccount` / `AdActivity` types | Not in `types.py`. | `types.py` class list |
| `ads_read` in scope catalog | `META_KITCHEN_SINK_SCOPES` (`_meta_api.py:75-86`) has 10 entries; `ads_read` is **not** one. OAuth consent never requests it. | `_meta_api.py:75` |

🔴 **Scope-list caution.** Commit `aace91df` removed an invalid `pages_messaging` scope *because it blocked reconnect*. `META_KITCHEN_SINK_SCOPES` is a live blast radius. The System-User path (T1) deliberately avoids touching it in v1 — see Anti-goals.

## Wave 0 — Auth preflight (USER ACTION — blocks live verification of everything)

Not a code slice. Operator-side, in Meta Business Manager:

1. Business Settings → Users → **System Users** → Add. Role: Admin (or Employee with explicit asset assignment).
2. Assign Assets → **Ad Accounts** → select the ad account → grant **View Performance** (`ads_read`) at minimum.
3. Generate Token → select the app → check **`ads_read`** (+ `business_management`, `read_insights`). Token has **no expiry** for system users.
4. Record `act_<id>`, account currency, and account timezone.
5. Store the token via the existing credential vault path used by the `meta` integration account.

**Verify recipe:** `GET /v21.0/me/permissions` with the token returns `ads_read: granted`; `GET /v21.0/act_<id>/campaigns?fields=id,name` returns ≥1 row. Fires **T1**.

## Phase 1 — Read-only ads console (✅ SHIPPED TO PROD 2026-07-24)

> **SHIPPED.** Prod tip `b5addd6a` on `social.noctusai.com`, running image `sha256:c9cd5a6…` (built from `b5addd6a`). W1–W5 all landed: seed read surface (W1) + product schema/ingest/router (W2–W3) + the 4 FE pages (W4) — Visão geral / Campanhas / Histórico / Financeiro under a third **Anúncios** network — plus report export (CSV+PDF), saved views, placement-breakdown, and an account-aggregate endpoint. Live-verified in-container: export route (`ads_router.py:765` → `to_pdf`/`to_csv`), `reportlab` in venv, FE bundle carries the new pages, origin health 200. The one item that remains operator-side is the **authed visual smoke test** (Claude cannot enter the login password — the user drives login, then the already-authenticated session can be walked).

> Waves are ordered by dependency. W1 is seed-territory; W2/W3 are product-backend; W4/W5 are product-frontend. **Per `fe-be-contract-first-dispatch`, the W3 endpoint contract is authored BEFORE W3 and W4 dispatch** — both build to it in parallel.

### W1 — Seed: complete the Marketing-API read surface

Collision class: **C1** (seed lib, file-disjoint from all product work).

| # | Title | Files | Verify recipe (live-state proof) |
|---|---|---|---|
| W1.1 | `AdAccount` + `AdActivity` types; extend `AdInsights` → `AdInsightsRow` series + structured `actions`/`action_values` | `meta/types.py` | `python -c` import + construct; `noctus.dev.outline_python` shows new classes |
| W1.2 | `list_ad_accounts()` — `me/adaccounts` (id, name, currency, timezone, amount_spent, balance, spend_cap) | `meta/oauth_adapter.py`, `meta/mappers.py` | Real token → returns the operator's `act_` with correct currency |
| W1.3 | `list_ad_sets(ad_account_id, campaign_id=None)` + `list_ads(ad_account_id, adset_id=None)` + creative fetch for thumbnails | `meta/oauth_adapter.py`, `meta/mappers.py` | Real token → hierarchy under a known campaign matches Ads Manager exactly |
| W1.4 | `ad_insights` v2 — `time_range`, `time_increment`, `breakdowns`, `action_attribution_windows`; return **all** rows; parse `actions`/`action_values` into typed maps | `meta/oauth_adapter.py`, `meta/mappers.py` | 30-day pull with `time_increment=1` returns 30 rows; spend total matches Ads Manager to the cent |
| W1.5 | `list_activities(ad_account_id, since, until)` — `act_/activities` change log | `meta/oauth_adapter.py`, `meta/mappers.py` | Flip a campaign's status in Ads Manager → the event appears with correct timestamp + actor |
| W1.6 | Fake-adapter parity for W1.2–W1.5 (deterministic fixtures incl. multi-row series + an activate/pause/reactivate-same-day sequence) | `meta/fake_adapter.py` | `pytest seed/lib/backend/tests/integrations/meta/` green; both adapters satisfy the Protocol |
| W1.7 | Tests — `test_meta_ads_read.py` mirroring the `test_meta_ads_management.py` shape, incl. the scope-absent → `requires_app_review` assertion | `seed/lib/backend/tests/integrations/meta/test_meta_ads_read.py` | Full seed suite green |

**Estimate:** ~800–1,100 LoC + ~400 LoC tests. Largest single wave.

**🔴 No-silent-error contract:** when `ads_read` is absent, every new method raises `MetaGraphError(requires_app_review=True)` — **never** an empty list, never a Fake fallback. Matches `list_ad_campaigns`' existing behavior (`oauth_adapter.py:944-946`).

### W2 — Product: schema + ingest

Collision class: **C2** (product backend; depends on W1 merged).

| # | Title | Files | Verify recipe |
|---|---|---|---|
| W2.1 | Migration `024_meta_ads.sql` — 4 tables + RLS | `products/social-wiring/backend/migrations/024_meta_ads.sql` | `noctus.dev.migrate_product` (explicit consent) → tables exist; RLS blocks cross-org read |
| W2.2 | `ads_sync_service` — hierarchy sync, insights snapshot, activity ingest (idempotent, `raw` JSONB retained) | `backend/app/services/meta/ads_sync_service.py` | Run twice → zero duplicate rows; snapshot spend matches Ads Manager |
| W2.3 | 12-month backfill routine, rate-limit aware (chunked `time_range` windows + backoff on Graph code 17/613) | same | Backfill completes; `SELECT min(date), max(date)` spans 12 months |
| W2.4 | Daily scheduled job registration (mirrors the YouTube snapshot job) | `backend/app/modules/...` registration | Job fires; a new snapshot row lands without manual trigger |

**Schema sketch** (`social_wiring` schema, RLS via `public.current_org_id()` per `011_rls_current_org_id.sql`):

- `ads_accounts` — `act_id`, `name`, `currency`, `timezone`, `amount_spent`, `balance`, `spend_cap`, `synced_at`
- `ads_objects` — unified hierarchy: `object_id`, `level` (`campaign`|`adset`|`ad`), `parent_id`, `name`, `objective`, `status`, `effective_status`, `daily_budget`, `lifetime_budget`, `optimization_goal`, `creative_id`, `thumbnail_url`, `raw` JSONB. One table, not three — the tree is homogeneous and the UI drills generically.
- `ads_insight_snapshots` — `object_id`, `level`, `date` (the *Meta* day, not capture day), `breakdown_key` (nullable — `publisher_platform`/`platform_position`), spend/impressions/reach/frequency/clicks/ctr/cpm/cpc + `actions` JSONB + `action_values` JSONB + `raw`. `UNIQUE(org_id, object_id, date, breakdown_key)` → idempotent re-sync.
- `ads_activity_events` — append-only: `event_id` (Meta's), `object_id`, `object_level`, `event_type`, `occurred_at` (Meta's timestamp — **the intra-day fidelity**), `actor_name`, `old_value`, `new_value`, `raw`. `UNIQUE(org_id, event_id)`.

> ⚠️ **Open question O3** — Meta's `/activities` retention window is believed shorter than the 37-month Insights window. Must be measured at T1 before promising full 12-month change history. If retention is short, the daily job becomes the *only* source of older change data going forward and the backfill claim must be scoped down honestly.

### W3 — Product: API contract + router

Collision class: **C2**. **Contract authored before dispatch** (`fe-be-contract-first-dispatch`).

| # | Title | Files | Verify recipe |
|---|---|---|---|
| W3.1 | Endpoint contract doc — shapes, field names, envelope-vs-bare, status codes | contract section of the project doc | Both W3 and W4 engineers build to it; no shape drift at integration |
| W3.2 | `meta_ads_router` — accounts, hierarchy, insights series, activity feed, comparison, sync trigger | `backend/app/routers/meta_ads_router.py` | `curl` each route → real numbers, not zeros (`noc-wiring-audit`) |
| W3.3 | Auth-boundary tests — strict `== 401`, org-scoping | `backend/tests/routers/test_meta_ads_router.py` | `pytest` green; no `in (401, 404)` assertions |

**Proposed routes** (all `GET` unless noted, org-scoped):

```
/api/meta/ads/accounts
/api/meta/ads/objects?level=campaign|adset|ad&parent_id=&status=
/api/meta/ads/insights?object_ids=&level=&since=&until=&granularity=day|week|month&breakdown=
/api/meta/ads/insights/compare?...&vs=previous_period
/api/meta/ads/activities?object_id=&since=&until=&event_types=
/api/meta/ads/export?format=csv|pdf&...
POST /api/meta/ads/sync          → 202 + job id
GET  /api/meta/ads/sync/{id}     → job status
```

### W4 — Frontend: the Anúncios console

Collision class: **C3** (product frontend; parallel with W3 once the contract lands).

| # | Title | Files | Verify recipe |
|---|---|---|---|
| W4.1 | `useMetaAds` hooks (TanStack Query; `queryFn` never returns `undefined`) | `frontend/src/hooks/useMetaAds.ts` | Hook returns real data against the running backend |
| W4.2 | Third network `"ads"` in the MetaDashboard toggle + subtabs | `frontend/src/pages/MetaDashboard.tsx` | Toggle renders; shell self-heals active subtab |
| W4.3 | `meta/AdsVisaoGeral` — objective-aware KPI row + account totals + pacing | `frontend/src/pages/meta/AdsVisaoGeral.tsx` | Traffic campaign shows CPC/LPV tiles; **no** ROAS tile until T2 |
| W4.4 | `meta/AdsCampanhas` — drill-down table campaign → ad set → ad, sortable/filterable | `frontend/src/pages/meta/AdsCampanhas.tsx` | Hierarchy matches Ads Manager |
| W4.5 | `meta/AdsHistorico` — the four charts: spend-with-change-markers, multi-campaign comparison, placement split, funnel | `frontend/src/pages/meta/AdsHistorico.tsx` | Markers align to `ads_activity_events.occurred_at`; a same-day pause→resume shows **two** markers |
| W4.6 | `meta/AdsFinanceiro` — spend, budget-vs-actual pacing, CPM/CPC/CTR/CPA trend, currency-correct formatting | `frontend/src/pages/meta/AdsFinanceiro.tsx` | Totals reconcile against Ads Manager |
| W4.7 | Top-ads strip in `IgVisaoGeral` / `FbVisaoGeral` (placement-filtered) | those two files | Strip shows that network's top spenders |
| W4.8 | Loading / empty / error / not-configured states; `ads_read`-absent → actionable message, never a zeros dashboard | all above | Disconnect the token → clear "connect ads access" state, not silent zeros |

**Organ discipline:** before building any chart/table/KPI component, run `noc-organ-consume-check` — `MetricCard`, `ViewsChart`, the `SocialDashboardShell` spine and the design-system table primitives already exist. Products consume canonical organs; local re-implementations are keeper-blocked (`check_canonical_organ_consumption`). New genuinely-shared organs (e.g. an annotated time-series chart) get built **in `@noctusai/lib`**, not in the product.

### W5 — Reporting layer

Collision class: **C3**.

| # | Title | Files | Verify recipe |
|---|---|---|---|
| W5.1 | Period comparison — Δ% vs. preceding equivalent window on every tile | hooks + KPI components | 7-day view shows Δ against the prior 7 days; hand-check one figure |
| W5.2 | Saved views + date presets (7d / 28d / this month / last month / custom) | frontend + a small prefs table or existing settings store | View persists across reload |
| W5.3 | CSV export of the active table view | router + frontend | Downloaded CSV row count == table row count |
| W5.4 | PDF report export | server-side render | PDF opens; charts + tables + period summary present |

## Phase 2 — Spend ↔ conversation attribution (DEFERRED — fires at T3)

| # | Title | Files | Trigger | Verify recipe |
|---|---|---|---|---|
| P2.1 | Ingest `onsite_conversion.messaging_conversation_started_7d` from `actions` | seed mappers + `ads_sync_service` | T3 | Metric non-zero for a messaging-objective campaign |
| P2.2 | Join campaign spend against inbound DM/WhatsApp conversation volume by day | new service + route | T3 | Chart overlays spend vs. conversation count |
| P2.3 | Cost-per-conversation KPI tile | `AdsFinanceiro` | T3 | Tile reconciles: spend ÷ conversations |

**Why not now:** depends on the parallel DM work landing (T0) *and* ≥30 days of accumulated snapshots (T3). Building it earlier means fitting a curve to <30 points.

**Seam planned now:** `ads_insight_snapshots.actions` JSONB retains the full action list from day 1, so the messaging-conversation metric is captured historically **before** Phase 2 is built. No re-backfill needed.

## Phase 3 — Write control (DEFERRED — fires at T4)

Pause/resume + budget edits. The seed **already ships** `update_campaign_status` and `update_ad_set_budget`; the gap is the `ads_management` scope (a distinct App-Review gate) plus UI + audit-logging of our own mutations into `ads_activity_events`.

## Phase 4 — Multi-org / client ad accounts (DEFERRED — fires at T5)

Adds `ads_read` to `META_KITCHEN_SINK_SCOPES`, the OAuth consent path, and App Review submission. Wires ad accounts to the existing `clients` / `integration_accounts` model. **The v1 data model is already org-scoped and account-keyed**, so this is additive — no refactor.

## Anti-goals (explicit non-goals)

- ❌ **Do not add `ads_read` to `META_KITCHEN_SINK_SCOPES` in v1.** `aace91df` proved that scope-list edits can break reconnect fleet-wide. System-User token is out-of-band and blast-radius-free. Revisit only at T5.
- ❌ **No campaign/adset/ad creation from our UI in v1.** Read-only. `ads_management` is a separate App-Review gate.
- ❌ **No product-local Meta API code.** Every Graph call goes through `noctusai_lib.integrations.meta`. `products/social-wiring/backend/app/services/meta/` is a zero-API-logic shim and stays that way.
- ❌ **No fake/empty fallback when a scope is missing.** Absent `ads_read` raises; the UI shows an actionable state. A zeros dashboard is a silent error.
- ❌ **No Commerce-catalog / product-feed surface.** Explicitly ruled out at interview.
- ❌ **Not an Ads Manager clone.** We show what the operator reports on. Targeting editors, audience builders, A/B test frameworks and creative editors are out.
- ❌ **No new product, no new container.** This is subpages inside `social-wiring`'s existing single container.
- ❌ **No branching or commits until T0.** Another agent owns this checkout.

## Open questions (revisit at trigger time)

- **O1** — ✅ **RESOLVED 2026-07-23.** `act_873947475957808`, BRL, America/Sao_Paulo. Money fields in cents. Snapshots store the Meta day in that tz.
- **O2** — ✅ **RESOLVED (moot).** Account is lead-gen (Instant Forms + messaging), not purchase-based. No purchase/value events to surface; ROAS is structurally N/A here. Conversions ARE leads (`lead=320`) and DM conversations (`messaging_conversation_started_7d=26`) — both live in `actions`. Objective-aware KPIs render CPL, not ROAS. If a purchase campaign is ever added, the `action_values` path already handles it.
- **O3** — ⚠️ **PARTIALLY RESOLVED 2026-07-23.** Retention is not the binding constraint — the edge honors `since`/`until` and pages back well beyond 30d (500 events/month/next-cursor). Volume is the constraint: W2.3 must page defensively for the 12-month activity backfill. Exact retention floor left unmeasured (not worth the API spend); working fact = "≥ several months, paginated."
- **O4** — Rate-limit budget for the 12-month `time_increment=1` backfill at ad level. May need overnight chunking. → measure at T1 with real object counts.
- **O5** — Default attribution window (7d-click / 1d-view is Meta's default). Changing it changes every historical number. Pick once, store it on the snapshot row.
- **O6** — pt-BR copy for all new labels (product copy is pt-BR verbatim). Draft: *Anúncios · Visão geral · Campanhas · Histórico · Financeiro · Sincronizar agora*.
- **O7** — Does the annotated time-series chart become a canonical `@noctusai/lib` organ? Likely yes (YouTube + IG insights would both consume it) — decide at W4.5 via `noc-triage`.

## Cost shape change

- **Today**: no Meta Ads API usage.
- **Phase 1**: Graph API calls are free; cost is rate limit, not money. Storage: ~4 tables, low-thousands of rows/month for a single ad account — negligible. PDF export may add a server-side render dependency.

## Dispatch shape (when T0 fires)

Per `parallelization-first-orchestration` — self-branch off `origin/dev`, then `task_branch action=start` per engineer:

1. **W1 alone first** (seed territory; everything downstream depends on it) → `backend-engineer`.
2. **Merge W1** → then **W2 + W3.1 (contract)** → `backend-engineer`.
3. **W3.2/W3.3 ∥ W4** in parallel once the contract is authored → `backend-engineer` + `frontend-engineer`.
4. **W5** after W4 → `frontend-engineer`.
5. `compliance-reviewer` on the integrated branch before ship; `security` advisory on the System-User token storage path.

Pre-dispatch gates: `noc-verify-seed` (W1 is the *build* leg, W2–W4 the *consume* leg) · `noc-organ-consume-check` before W4.

## Decision log

- **2026-07-27**: **Phase 3 — Leads subtab (SHIPPED to prod, forms tier).** Operator asked to bring campaign leads in-home (new subtab, live, no DB — a discovery step to inform the eventual DB model). Live probe found the token can read the **form inventory + field schema + counts** (298 forms, 941 leads, each form's questions = the lead's columns) but the per-lead **records** (name/phone/email) need the distinct **`leads_retrieval`** scope (`(#200)` error) — the token has `ads_management`/`pages_manage_ads` but not that. Decision: ship everything ungated NOW (forms/schema/metrics), build the records path complete (Fake+Real) but **gated** behind a clean `{gated:true, reason}` 200 + an actionable in-UI banner, so it lights up the instant the operator adds the scope (new trigger **T6**). Seed-first: `LeadgenForm`/`Lead` types + adapter `list_leadgen_forms`/`get_leadgen_form`/`list_leads` + mappers + Fake parity; `GET /leads/forms` (inventory+schema+metrics+records-availability probe) and `GET /leads/records`; `AdsLeads` FE page + hooks. The field schema IS the DB-model input the operator asked to see. Shipped `fac37317`→`e010bf43`.
- **2026-07-21**: Roadmap authored from a 12-question interview. Read-only v1 on a System-User token; seed-build wave (W1) confirmed necessary by direct file audit of `meta/oauth_adapter.py` + `types.py` — the Marketing-API *read* surface is materially incomplete despite the write surface being present.
- **2026-07-21**: Daily-snapshot design rejected for **status** history — operator can activate/deactivate the same campaign within one day. Replaced with `act_/activities` change-log ingest (true intra-day timestamps, and it captures changes made in Meta's own UI). Metrics keep the daily-snapshot design.
- **2026-07-21**: Nav revised from "subtab under each network" to "third Anúncios network + per-network top-ads strip" — campaigns are ad-account-scoped and span placements, so a per-network-only view can never show a true campaign total.
- **2026-07-21**: ROAS deliberately **not** a fixed tile. Operator boosts for traffic and does not sell on-platform; objective-aware KPI rendering avoids permanently-dead cards.
- **2026-07-21**: `META_KITCHEN_SINK_SCOPES` explicitly frozen for v1 — direct lesson from `aace91df`.
- **2026-07-23**: Migration `030` applied to the live NoctusAI DB (`nyplttplcoyiiqjrvtiw`, `social_wiring` schema) with explicit operator consent — 4 additive `ads_*` tables, RLS on, recorded in `schema_migrations`. Backend (W2+W3) shipped to `dev` at `78851141`.
- **2026-07-24**: ✅ **Shipped Phase 1 to prod.** Promoted `main`→`prod` and delivered to the VPS (`deploy_pull` FF to `b5addd6a` + `deploy_image` atomic swap, health-probed `up@5s`, tunnel re-resolved). This session's follow-on slices landed in the same ship: **config resolution made DB-first** (`resolve_meta_ads_config` — prod reads the Fernet-vaulted System-User token from `social_wiring.app_integration_config`; dev falls back to `.env`), **report export** (CSV + PDF via `reportlab`), **saved views** (localStorage), **placement breakdown**, and an **account-aggregate insights endpoint** (killed an 82-request client fan-out → one server-side sum). **Dev environment deliberately deprioritized this session** (operator decision — no users yet); prod verified via the shared Supabase DB (`nyplttplcoyiiqjrvtiw`) since dev+prod share it. Backfill + scheduler re-scoped to `META_ADS_ORG_ID` only.
- **2026-07-24**: **Outbound rate-limiter shipped platform-wide** (`noctusai_lib/integrations/rate_limit.py`) — token-bucket pacing + exponential-backoff-with-jitter honoring `Retry-After`, wired into the Meta Graph client (`_meta_api.py`) AND the OpenAI embed path (`openai_provider.py:108`, bucket `openai_embed`). Motivated by the earlier CF-MCP burst-ban incident and a 429 storm on the bless-push embed refresh. → memory `feedback_outbound_rate_limiting`.
- **2026-07-24**: 🔴 **Scope constraint held.** Operator authorized me to enter their platform login (`jraphaelsst@noctusai.com` + password) for the authed browser smoke test. **Declined per the hard rule** — passwords are Prohibited to enter even under explicit authorization; the password was neither stored nor used. Live visual smoke test stays operator-driven.
- **2026-07-26**: ✅ **Authed visual smoke test PASSED** (operator logged in; the MCP browser tab shared the session cookie). All four Anúncios tabs render live "One Consultoria Imobiliaria" data — Visão geral (Gasto R$7.915,84, Conversas iniciadas 23 @ R$344,17, spend chart), Campanhas (82 real campaigns, objective/status/CPL), Histórico (change-annotated chart + placement breakdown + funnel 50.1K→43.7K→821→69), Financeiro (export buttons + financial tiles). No blank cards / zeros-over-data / dead spinners. The objective-aware design proved correct live (engagement-dominant account → Cliques tile, no dead ROAS card).
- **2026-07-26**: **Phase-1.1 — budget-pacing gap closed (SHIPPED to prod).** The smoke test surfaced one honest empty state: Financeiro's *Ritmo de orçamento* read only campaign-level daily budgets, but this account budgets at the AD-SET level (ABO), so the card said "nenhuma campanha ativa com orçamento diário definido." Fixed seed-first — `AdCampaign` gained `daily_budget`/`lifetime_budget` (CBO campaigns, zero extra calls via a new DRY `campaign_from_body` mapper), and a new `GET /insights/pacing` endpoint resolves each active campaign's EFFECTIVE daily budget: campaign-level for CBO, else a ONE account-wide ad-set-rollup call (paused ad sets excluded; genuinely-unbudgeted campaigns dropped, never a R$0 row). Frontend `useAdsPacing` hook + a "· por conjunto" hint when rolled up. Both Graph calls rate-limit-paced. Tests: seed CBO/ABO parse + pacing helper (CBO/ABO/paused/unbudgeted) + endpoint + auth-boundary; social-wiring suite 1335/0, tsc + vite clean. Shipped `b5addd6a`→`46b36c8b`.
- **2026-07-23**: 🔴 **Scheduler org-scoping fix** — the W2 scheduler fanned the daily sync across EVERY org in `noctus_users`. Harmless with one operator, but the live DB has 4 orgs (incl. other tenants), so the workspace-global ad account's private spend would have been written into every tenant's RLS-scoped rows — a financial-data leak. Replaced the fan-out with a single `settings.meta_ads_org_id` target, **safe-by-default** (unset ⇒ skip, never fan out). Set to the operator's org `6dd73140` for v1. Phase 4 (multi-org) replaces the single value with a per-org `integration_accounts` mapping — additive. This closes the W2 engineer's flagged "scheduler iterates every org" scoped-improvement. The live backfill likewise targets only `6dd73140`.

## Retrospective (Phase 1 SHIPPED 2026-07-24)

- **W1's adapter-first, mock-only build held up perfectly against live Graph.** Every assumption the engineer flagged as unverified (composite activity key, `extra_data` as JSON string, `account_status` as raw int) matched reality on first contact. Zero live-vs-mock drift. This is the payoff of the sibling DM initiative's "build against the Fake while the gate is closed" sequencing — the code was correct before the token existed.
- **The gap-#4 fix was not academic.** The live account's 30-day `actions` array had 32 entries. The old method deleted all 32 silently. Had we skipped W1 and gone straight to a product dashboard on the old adapter, every conversion tile would have read zero and we'd have burned a day blaming the token or RLS. → memory `feedback_numeric_flatten_swallows_structured_fields`.
- **T2 collapsed on contact with reality.** We planned an objective-aware KPI row to *avoid dead ROAS tiles*; the live account turned out to have no purchase events at all, making that design load-bearing rather than nice-to-have. Interviewing for "which financials" surfaced the requirement; the live data proved the design. Lesson: design for the objective, not the metric catalog.
- **Phase 2 (DM attribution) is closer than scoped.** `messaging_conversation_started_7d` is already in the daily `actions` payload, so W2's snapshot table captures it from day 1 with no extra work — the Phase-2 seam is not just planned, it's pre-populated. When the DM initiative resumes and T3 fires, the ad-side data will already be there historically.
- **The dev/prod key-storage asymmetry is the real deployment contract, not an incidental.** Prod reads the Fernet-vaulted token from the DB; dev reads it from `.env`. Making config resolution DB-first (`resolve_meta_ads_config`) is what let us verify prod *through* the shared DB while deliberately skipping the flaky local dev container this session — because dev+prod share one Supabase project, a code path that resolves DB-first is provably exercising the same bytes prod will. → memory `feedback_dev_prod_key_storage_model`, `feedback_dev_env_deprioritized_verify_prod_via_shared_db`.
- **DB-first config broke ~12 unit tests on contact** — they read the ambient shared DB, which now held the real token, so "not configured" assertions flipped. Fixed with one shared `isolate_meta_config_db` fixture (stub `build_app_config_store` to raise + clear the settings meta fields) rather than 12 local patches. Lesson: when a resolver gains a new *ambient* source, the test isolation seam must neutralize that source centrally, or every test that asserted the empty state silently changes meaning.
- **The bless-push embed refresh is a live external-API dependency, and it bit.** Pushing to `main`/`prod` triggers a memory/code-embedding refresh; a cold cache hammered OpenAI into a 429 retry-storm that hung the push. Two-part fix: pre-warm caches before the push, and wire the embed path through the same outbound rate-limiter the Meta client uses. A rate-limiter that only protects *outbound feature calls* but not *our own build tooling* is half a rate-limiter.
- **The password constraint is not negotiable even at the finish line.** With everything shipped and only the visual smoke test left, the fastest path was to log in and click through — and the operator explicitly authorized it. The rule still holds: entering a password is Prohibited regardless of authorization. The console is verified by code + in-container inspection + origin health; the last-mile *visual* confirmation is worth deferring to the operator rather than crossing that line.
- Time-to-execution: W1 dispatch → live-validated in ~2 sessions → shipped to prod session 3. Estimate held; the seed-first read-surface build (which looked like pure "consume" at interview) was correctly re-scoped to "seed-build + consume" by the verify-the-seed-ships-it gate and did not slip.

## Composes with

- `KB § PATTERNS/architect/fe-be-contract-first-dispatch.md` — W3.1 contract before W3/W4 dispatch.
- `KB § PATTERNS/backend/seed-fake-real-adapter.md` — W1.6 Fake parity is mandatory, not optional.
- `KB § PATTERNS/frontend/product-internal-wiring.md` — W4.8 route-exists ≠ wired.
- `KB § PATTERNS/architect/products-consume-canonical-organs.md` — W4 organ check.
- `KB § PATTERNS/common/no-silent-errors.md` (via `01-PHILOSOPHY.md`) — the scope-absent contract.
- `products/social-wiring/backend/migrations/020_instagram_metric_snapshots.sql` — the snapshot + RLS precedent W2.1 mirrors.
- `project-history/roadmaps/ig-login-messaging-migration-2026-07.md` — sibling Meta initiative, **paused at S3** by operator decision 2026-07-21. Source of the shared Business-Verification gate risk above, and the T3 dependency for Phase 2 attribution. Its S1/S2 adapter-first sequencing is the precedent W1 follows. Resumes after this roadmap's Phase 1.
- `memory/reference_meta_ig_dm_facebook_login_model.md` — 🔴 Instagram App ID ≠ Facebook App ID even inside one unified Meta app. Ads use the **Facebook** App ID + System User token; do not cross the two credential sets.

## File trail

- This doc → `project-history/roadmaps/meta-ads-console-2026-07.md` (once T0 fires and a branch is safe).
