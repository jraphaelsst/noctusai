# 10 — Deep-Dive: Meta / Facebook Ads Integration (knowledge capture)

> Faithful capture of the agency's core differentiator (paid-traffic management). 11 `facebook-*` edge functions + `process-lead-qualification` + 10 migrations + FE traffic/CRM. All `agency_id`-scoped, RLS via `is_agency_admin`/`user_belongs_to_agency`.

## 1. Architecture

**OAuth flow (the standout trick).** `facebook-auth` serves initiate + callback + token CRUD. **Stateless JWT round-trip through OAuth `state`:**
- `initiate_auth` (authed): `state = btoa(JSON.stringify({supabase_jwt: token}))`; scope `ads_management,ads_read,business_management`; returns `…/v19.0/dialog/oauth?…&state=…`.
- **callback** (GET, **unauthenticated** — Meta calls directly): exchange `code`→`access_token`, then **reconstruct identity from `state`** (`atob`→parse→`supabase_jwt`→build a Supabase client with that bearer→`auth.getUser()`+`rpc('get_user_agency_id')`) so the public callback persists the token **under live RLS, no service-role bypass**. Also `/me?fields=id,name` → `facebook_user_id`.
- `getRedirectUri` normalizes to canonical `<ref>.functions.supabase.co/facebook-auth` (Meta exact-match redirect never breaks on host variants).
- **Triple-redundant confirmation** (FE `FacebookConnectionDialog`): callback HTML `postMessage`s token to opener + `window.close()`; FE listens AND polls `verify_connection` every 1.5s with a lock AND falls back to `save_token` if postMessage arrives `saved=false`. Three paths to a confirmed connection (defensive vs popup/COOP loss).

**Token storage:** `facebook_connections.access_token` **plaintext** (no encryption), upsert on `(agency_id, facebook_user_id)`. Other functions re-read the **agency-scoped active connection** (not per-user) → any gestor operates through the admin's one connection.

**Function topology (11+1):** `facebook-auth` (OAuth), `facebook-accounts` (list ad accounts/pixels), `facebook-account-summary` (balance/budget/campaign cache), `facebook-balance`, `facebook-campaigns` (campaigns+insights+adsets), `facebook-analysis` (4-week trend), `facebook-sync` (metrics→`ad_account_metrics`), `facebook-sync-cron` (8h spend/balance cache), `facebook-heartbeat` (4h token-health+API-diversification→`facebook_api_audit`), `facebook-leads` (dual webhook+app-API), `process-lead-qualification` (scoring+CAPI). The agency-resolution + connection-fetch preamble is **copy-pasted ~40-100 lines per function** (the dup a seed-adapter collapses).

## 2. Data model (all `agency_id`-scoped, RLS)

- **`facebook_connections`** — one OAuth conn/agency-FB-user: `access_token`, `token_expires_at`, `business_id/name`, `is_active`. `UNIQUE(agency_id, facebook_user_id)`.
- **`selected_ad_accounts`** — chosen accounts + **denormalized live cache** (written by summary/cron): `ad_account_id/name`, `currency`, `timezone` + cache cols added across 4 migrations: `is_prepaid`, `spend_cap`, `amount_spent`, `active_campaigns_count`, `total_daily_budget`, `last_7d_spend`, `balance`, `current_month_spend`, `cached_at`. FE's fast read path (no live Graph call on load). `UNIQUE(agency_id, ad_account_id)`.
- **`ad_account_metrics`** — historical daily time-series: `date_start/end`, `spend`, `impressions/clicks/conversions`, `cpm/cpc/ctr/conversion_rate`, `account_balance`, `raw_data jsonb`. `UNIQUE(ad_account_id, date_start, date_end)` (upsert-on-resync idempotency).
- **`ad_account_balance_settings`** — `min_threshold` low-balance alert (default 100).
- **`facebook_pixels`** — `pixel_id/name`, `is_selected`, `test_event_code`. `UNIQUE(agency_id, pixel_id)` + **partial unique `WHERE is_selected=true`** (exactly one active pixel/agency = the CAPI destination).
- **`facebook_lead_integrations`** — (page, form)→CRM routing: `page_id/name`, `form_id/name`, `sync_method (webhook|polling)`, `default_status/priority/source`, `field_mapping jsonb`, `pixel_id`, `is_active`, `last_sync_at`.
- **`facebook_lead_sync_log`** — dedup ledger + raw archive: `facebook_lead_id`, `lead_id`, `lead_data jsonb`. `UNIQUE(integration_id, facebook_lead_id)`. Also the `form_id` recovery source for qualification.
- **`facebook_api_audit`** — every heartbeat call: `endpoint/method/status/response_data/error_message/response_time_ms`.
- **`meta_conversion_events`** — CAPI dispatch ledger/dedup: `event_name`, `pixel_id`, `status (sent|failed|skipped)`, `response_data`. **`UNIQUE(lead_id, event_name)`** (dedup key).
- **`lead_scoring_rules`** — `(agency_id, form_id, question, answer)` → `score INT CHECK(-2..2)`, `is_blocker`. **`lead_scoring_results`** — `score_total`, `qualification`, `answers_detail jsonb`.
- **`agencies.crm_ad_account_id`** → the primary account the cron syncs / CRM reads.

**Spine:** `agencies → facebook_connections → selected_ad_accounts (cache) + facebook_lead_integrations → facebook_lead_sync_log → leads → lead_scoring_results + meta_conversion_events`; `facebook_pixels` = CAPI sink via `get_meta_pixel_config(agency_id)`.

## 3. Lead-Ads ingestion (`facebook-leads`, 901 ln — webhook + app-API on one URL)

Dispatch by shape: `GET` → webhook **verify** (`hub.verify_token===FACEBOOK_VERIFY_TOKEN`, echo `hub.challenge`); `POST`+`action` → authed app-API (`list_pages/list_forms/list_form_questions/save_integration/get_integrations/delete_integration/sync_leads/subscribe_webhook`); `POST` no `action` → webhook receive.

**Official page-token walk** (`list_forms`): user token can't read `leadgen_forms`; so agency token → `/me/accounts?fields=id,name,access_token` (paginated) → find page → extract **page access token** → `/{page_id}/leadgen_forms` with page token → filter `ACTIVE`. If page absent from `/me/accounts` → user lacks admin → surfaced as readable error.

**Auto-subscribe on save:** `save_integration` → `setupWebhookSubscription` → `POST /{page_id}/subscribed_apps {subscribed_fields:['leadgen']}` (best-effort; failure logged, doesn't fail save; `subscribe_webhook` retries).

**Webhook ingestion (`handleWebhook`):**
1. Guard `object==='page'`; iterate `entry[].changes[]`, skip `field!=='leadgen'`.
2. Pull `leadgen_id` + `form_id`.
3. **Integration resolution 3-tier ladder:** exact `(page_id, form_id, active)` → `(page_id, form_id='all', active)` wildcard → any active integration for the page.
4. **Auto-create-form-integration-on-first-hit:** when matched via wildcard/fallback, **insert a concrete per-form integration** (real name from `/{form_id}?fields=name`), inheriting parent config; `23505` benign. ⇒ one `'all'` integration and every new form self-registers.
5. **Dedup** via `facebook_lead_sync_log` by `facebook_lead_id`.
6. **Enrich** `/{leadgen_id}` → `field_data[]` → `fieldData[name]=values[0]`.
7. **Map to `leads`:** `full_name||first_name`→name, email, `phone_number`→phone, `company_name`→company; legacy status `'new'`→`'leads'`; temperature `low/medium/high`→`cold/warm/hot`; `source='facebook_leads'`; `custom_fields=fieldData` (full map preserved).
8. **Log** to sync_log (full payload, `sync_method:'webhook'`).
9. **Fan-out two side-effects:** `process-lead-qualification` (scoring+CAPI) + `triggerWhatsAppAutomationFlows`→`automation-trigger` (`lead_created`, `capture_channel:'meta_ads'`). ⇒ a Meta lead instantly becomes CRM row → scored → CAPI event → WhatsApp automation.

`sync_leads` (polling/backfill) mirrors mapping over `/{form_id}/leads`, dedup per `(integration_id, facebook_lead_id)`, same qualification trigger.

## 4. Conversions API feedback loop (the genuine moat)

`process-lead-qualification` dual-mode:

**Mode 2 — qualification scoring** (every new lead): empty custom_fields → `unconfigured`, score 0. `resolveFormId` priority chain (custom_fields.form_id → sync_log.lead_data.form_id → `inferFormId` best key-overlap vs rules, each gated by `hasRules`). **Accent-fold `normalize()`** (lowercase→NFD→strip marks→`_`→space→compact) on **both** question and answer, both sides (so Meta `full_name` ↔ rule `"full name"`, `Não`↔`nao`). Sum matched `score`; any `is_blocker` → `-10`/cold. Classify `≥5 hot / ≥2 warm / else cold`. Upsert `lead_scoring_results` + update `leads.temperature/qualification_score`.

**CAPI dispatch:** resolve pixel+token via `get_meta_pixel_config(agency_id)` RPC (SECURITY DEFINER, joins selected pixel + active connection token), legacy fallback `facebook_lead_integrations.pixel_id`. Fire per tier: **hot → Lead+QualifiedLead; cold → Lead+ColdLead; warm → Lead.**

**Mode 1 — pipeline events** (fire-and-forget on CRM stage change, FE `metaPipelineEvents.ts`): `scheduled→Schedule`, `proposal→SubmitApplication`, `won→Purchase`. ⇒ Meta learns **downstream sales outcomes**, not just form fills — the optimizer trains on real revenue signal.

**`sendMetaEvent` mechanics:** dedup `eventId=lead.id_eventName` + DB `UNIQUE(lead_id,event_name)` + Meta-side `event_id`. **PII hashing** SHA-256 (`crypto.subtle`) over `value.toLowerCase().trim()` hex: `ph`, `em`, `fn`, `ln`, `external_id=SHA256(lead.id)`. POST `/v19.0/{pixel_id}/events` with `{event_name, event_time, event_id, action_source:'system_generated', user_data, custom_data:{lead_score, qualification, value?, currency:'BRL'}}`. `test_event_code` appended when set. No token → `status:'skipped'` logged (not silently dropped). Every outcome → `meta_conversion_events`.

## 5. Sync + health cadence
- **`facebook-sync-cron` `0 */8 * * *`** — agencies with `crm_ad_account_id`: current-month spend, last-7d spend, account info (`balance/amount_spent/spend_cap/currency/funding_source_details`), active-campaign count → **writes the live cache** into `selected_ad_accounts`. Dashboard never blocks on Graph.
- **`facebook-heartbeat` `0 */4 * * *`** — every active conn × account hits **7 diversified endpoints** (account/campaigns/adsets/ads/7d/30d insights/audiences) @300ms throttle. Purpose: (a) token keep-warm, (b) **deliberate API-usage diversification** ("Facebook requires diversified real usage" — App-Review activity signal). Each logged to `facebook_api_audit` with timing.
- **`facebook-sync sync_metrics`** — `/insights?time_increment=1` per account, conversions from `actions[]`, upsert daily `(ad_account_id, date_start, date_end)`.

## 6. Clever techniques worth learning
1. **Stateless JWT in OAuth `state`** → public callback persists token under live RLS, no service-role.
2. **Triple-redundant connection confirmation** (postMessage + poll + save_token fallback).
3. **One endpoint, three protocols** (webhook-verify GET / app-API POST+action / webhook-receive POST).
4. **Auto-subscribe + auto-create-form-on-first-hit** (zero-touch form onboarding).
5. **Accent-folded `normalize()` both sides** (the single most reusable helper for pt-BR forms).
6. **`form_id` 3-source resolution with `hasRules` gating.**
7. **Quality-graded CAPI incl. pipeline outcomes** (QualifiedLead/ColdLead + Schedule/SubmitApplication/Purchase) — the moat.
8. **Deterministic CAPI dedup + Meta-spec PII hashing.**
9. **`facebook_api_audit` + diversified heartbeat** (App-Review signal + observability).
10. **Denormalized live cache** in `selected_ad_accounts` + `get_meta_pixel_config` one-shot RPC.
11. **Prepaid/postpaid BRL balance extraction** — regex `R$ x.xxx,yy` out of `funding_source_details.display_string` (no clean API field), tiered fallback. Hard-won BR Meta-billing knowledge.
12. **Hierarchical budget validation** — count an adset's `daily_budget` only if adset ACTIVE **and parent campaign active** (avoids over-counting under paused campaigns); CBO fallback; batched ×5.

## 7. Sophistication assessment (neutral)
**Well above a commodity CRM-FB integration** on three axes: Lead-Ads fully productized (page-token walk, auto-subscribe, wildcard+auto-create, dedup, raw archive, instant fan-out); the **CAPI feedback loop is the rare/hard part** (graded quality + pipeline outcomes back to Meta, correct hashing/dedup, pixel RPC, full ledger) — directly improves clients' ad performance = the product; operational maturity (4h heartbeat doubling as App-Review signal, 8h spend cache, prepaid-BRL extraction, hierarchical budget, batched parallelism, multi-agency-safe auth).

**Weaknesses / don't copy:** (a) **plaintext tokens**; (b) **`Math.random()` mock-data fallbacks** in `facebook-sync get_metrics/generate_report` + `facebook-analysis` when Graph fails — can silently show fabricated numbers (correctness/trust hazard); (c) **no webhook HMAC** (`X-Hub-Signature-256`) — receiver trusts any caller (dedup limits damage); (d) heavy per-function dup; (e) **no token-refresh** (long-lived assumed; heartbeat keeps warm but nothing re-auths on expiry).

**The hard-won core to learn:** the Lead-Ads → qualification → graded-CAPI → pipeline-outcome loop, prepaid-BRL balance extraction, the stateless-JWT OAuth callback.

## 8. Open questions
Token encryption/refresh (plaintext, no long-lived exchange — noc's bytea-credential+hex-read parity learning applies); webhook HMAC intentional or gap; the `FACEBOOK_ACCESS_TOKEN` env fallback in `sendMetaEvent` (single app-level CAPI token — multi-tenant correctness?); whether mock-data fallbacks are reachable in prod or vestigial; **API version drift v18 (8 fns) vs v19 (auth/accounts/qualification)** — v18 near-deprecation; whether `field_mapping jsonb` is applied (mapping is hardcoded); PDF report mechanism not located in traffic components.
