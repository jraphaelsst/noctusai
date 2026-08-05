# META-LEADS-CHECKLIST.md — campaign-lead ingestion, end to end

> **Working tracker** for the Meta Lead-Ads ingestion initiative started 2026-08-03.
> Tick items as they land; every line names the file it touches so progress is auditable.
> Durable roadmap home: `project-history/roadmaps/meta-ads-console-2026-07.md` (Phase 3.2 —
> this checklist is its execution surface). Full rationale for every decision lives there and
> in the approved plan; this file is the *what shipped* view.

**Status:** 🚀 **DEPLOYED TO PRODUCTION** · 2026-08-04 · `dev = main = prod = 27c1522f`

Merged alongside the WhatsApp realtime inbox and Imóveis/Vista; all three green together.
Suites on the merged tip, **by exit code**: social-wiring **1671** · erp **2161** ·
seed lib **2662** · social-wiring FE **490** · seed FE **319** · tsc + vite build clean.
✅ Migrations `041` + `044` applied and schema-verified.

**What remains is not code.** Every open box below is one of: (a) a **live verification**
that needs a prod deploy, (b) an **operator step** in the Meta App Dashboard that no code
can perform, or (c) **Slice 7**, conditional on whether off-platform lead exports exist.

**Two defects found and fixed on 2026-08-04, both invisible to every existing gate:**

1. 🔴 **The fan-out was never wired.** `process_event` promised
   "enrich → upsert → normalize → notify" and did only the first two. Slice 3's
   `ingest_meta_lead` and Slice 4's `notify_new_lead` each shipped green and *uncalled* —
   so leads never reached `social_wiring.leads` and no alert ever fired. Both were explicit
   product decisions. Cause: file-disjoint parallel dispatch leaves the integration seam
   owned by nobody, and the receiver had **zero** service-level tests (only route tests
   against a fake service). Fixed + guarded at the service level, negative-controlled.

2. 🔴 **Migration `042` carried committed merge-conflict markers** (from the peer's
   040→042 renumber). The SQL body was intact and the shared DB had already applied a clean
   blob, so the live schema was correct and the test suite stayed green — it would only have
   surfaced on a fresh environment or a DR restore. Fixed, and gated by a new
   `check_conflict_markers` keeper.

## Slice 0 — Scheduled lead sync (the standalone fix) — ✅ code complete

- [x] `products/social-wiring/backend/app/modules/meta_ads/scheduler.py` — call
      `LeadsSyncService(...).sync_all(...)` inside `_sync_job_sync`, **last** in the try-block
- [x] Added a fifth DI seam `leads_service_factory=` (matches the module's Class-A convention,
      so the tests drive the real resolution instead of patching module globals)
- [x] Fold `forms_upserted` / `leads_upserted` / `records_gated` into the summary log line
- [x] Preserve `_target_org_id` safe-by-default gating (unset ⇒ skip, never fan out across tenants)
- [x] Test `test_daily_sync_calls_leads_sync_all` (the regression guard for this exact bug)
- [x] Test: unset org ⇒ leads service never constructed (fan-out guard covers the lead leg too)
- [x] Test: lead sync runs **after** the four ads calls (ordering is load-bearing)
- [x] Test: `records_gated` is visible in the summary log (no-silent-errors applies to logs)
- [x] Full `social-wiring` backend suite green — **1496 passed**, exit 0
- [x] Shipped as its own commit so it can be cherry-picked independently
- [ ] **Verify live:** `max(synced_at)` on `social_wiring.meta_ads_leads` advances after a run
      *(needs deploy + the 06:00 cron, or a manual job trigger)*

## Slice 1 — Seed: leadgen webhook capability (C1) — ✅ merged `10489508`

- [x] NEW `seed/lib/backend/noctusai_lib/integrations/meta/leadgen_webhook.py`
      — `LeadgenEvent` (:24), `parse_leadgen_webhook` (:74, all `entry[]`×`changes[]`),
      `leadgen_challenge_response` (:135, `hmac.compare_digest`)
- [x] `get_lead(leadgen_id, page_id=None)` — Protocol + Fake + Real; Fake **raises** on a miss
      (an empty `Lead` would silently upsert a PII-less row)
- [x] `subscribe_page_to_leadgen` — verified on the wire as `",".join(fields)`, the
      comma-joined STRING `graph_post`'s form encoding needs, not a JSON list
- [x] `list_page_subscribed_apps` + `PageSubscription` type + `page_subscription_from_body`
- [x] `unsubscribe_page_from_leadgen` — reused the pre-existing `graph_delete`, no new helper
- [x] Exports in `meta/__init__.py.__all__`
- [x] Tests: parser table-tests + adapter coverage; **280** meta tests, full seed suite **2545**
- [x] KB `INTEGRATIONS/meta.md` §5 flipped to shipped; engineer also backfilled the
      previously-undocumented lead-ads READ surface while in the same tables
- [x] **Merge gate satisfied** — Slice 2 consumes it, so no orphan factory

> Engineer correctly overrode one brief instruction: `MetaAdapter` is a plain `Protocol`, not
> `@runtime_checkable`, so `isinstance()` would `TypeError` at collection. They followed the
> repo's existing structural-conformance precedent instead. My brief was wrong; the code is right.

## Slice 2 — Product: receiver + inbox (C2) — ✅ code complete (local)

- [x] Migration `044_meta_webhook_events.sql` + 11 structural tests
- [x] `meta_webhook_verify_token` config + `resolve_meta_webhook_verify_token()` vault key
- [x] `services/leadgen_webhook_service.py` — `record_event` / `resolve_org` / `resolve_form`
      (with cold-form fallback) / `process_event` / `claim` / `drain_pending` / `purge_processed`
- [x] `routers/leadgen_router.py` — 6 routes; HMAC via **App Secret**, `bypass_when_unset=False`;
      handshake echoes the challenge as a STRING (the erp `int()` bug)
- [x] `get_leadgen_service` as a named `Depends` seam so tests exercise the real route
- [x] Registered in `meta_ads/__init__.py`; `_upsert_lead` → public `upsert_lead`
      (no back-compat alias — grep proved zero other call sites, so an alias would be dead code)
- [x] `meta_leadgen_retry` job (`*/15`) + 90-day LGPD purge wired into `configure()`
- [x] Redis SETNX dedup — first production consumer of `get_webhook_dedup()`; fails SAFE
      (unreachable Redis ⇒ proceed, since layers 2+3 still guarantee idempotency)
- [x] 18 status-pinned receiver tests + 6 auth-boundary tests. Full suite **1565 passed**
- [x] `.env.example` `META_*` block; webhook-signatures adopter list corrected
- [x] `META-APP-VERIFICATION.md` §10 rewritten as the configuration runbook (was "optional / later")
- [ ] **Verify live:** Lead Ads Testing Tool → inbox `processed` + lead row + one funnel card

## Slice 3 — Unified leads base (C2) — ✅ integrated `ce985fdd`

- [x] Canonical `lead_sources` row `slug='meta-lead-ads'`, `categoria='social'`
      (`seed_data.py:64-89`, appended not interleaved so existing chart legends don't reorder)
- [x] NEW `modules/leads/services/meta_ingest_service.py` — pure mapping + `ingest_meta_lead`
      (single, idempotent, called by the receiver) + `backfill_meta_ads_leads` (paged, explicit)
- [x] Migration `041_leads_meta_lead_id.sql` — nullable `meta_lead_id` + partial
      `UNIQUE (org_id, meta_lead_id) WHERE meta_lead_id IS NOT NULL`. No new policy needed:
      `leads`' existing RLS from 025 covers new columns
- [x] `POST /api/leads/meta-ingest/backfill` as the explicit human-triggered entry point
- [x] 27 new tests; full suite **1523 passed**
- [x] 🔍 **Gap I caught on review:** the new backfill route was added without an entry in the
      parametrized auth-boundary list. The route IS protected (verified 401), so this was a
      test gap not a hole — but that list only works if every new route joins it. Fixed (`6a3d1b72`)
- [ ] Run the backfill for the 958 stored leads (deliberate, post-deploy — not auto-run)
      *(migration 041 is now applied, so `leads.meta_lead_id` exists and the backfill is unblocked)*
- [ ] **Verify live:** test lead visible in `/api/leads` with origem "Meta Lead Ads"

> Engineer flagged two judgement calls worth knowing: re-ingesting an already-ingested lead
> returns the existing row unchanged (safe — a submitted Instant Form lead is immutable on
> Meta's side), and the `corretor_id` resolution path is currently dead in practice because no
> live form asks which corretor. Both left in place and surfaced rather than silently dropped.

## Slice 4 — Notification fan-out (C2) — ✅ integrated `3aced8ac`

- [x] Generalized `notification_service.py` — `_dispatch(...)` core extracted from `notify_upload`
      (`notification_service.py:174`); `notify_upload` behaviour unchanged
- [x] `notify_new_lead(*, org_id, lead)` (`:138`) — takes the lead dict the caller already holds,
      never re-queries Meta or Postgres; pt-BR copy (`_build_lead_message:405`)
- [x] `whatsapp_client_factory` DI seam added so tests drive real resolution
- [x] Per-recipient failures are logged, never raised — the webhook must never return non-2xx
      because SMTP was slow (Meta retries non-2xx and can disable the subscription)
- [x] 6 new tests; full suite 1502 passed, independently re-run and verified by exit code
- [x] 🐛 **Real bug fixed in passing:** `_log` did `str(job_id)` unconditionally, so a non-upload
      caller would have written the literal string `"None"` into the nullable `upload_job_id`
      UUID column. Now conditional.
- [x] **Recipients configured 2026-08-05** — João Raphael (joaoraphaelsst@gmail.com
      / +5511974693365), org-wide tier. Two real leads arrived on 2026-08-04 and
      alerted nobody because the roster was empty; that state is now both fixed
      and *visible* (WARNING log + amber banner on the webhook health card).
- [x] **Per-client recipients (migration 045)** — recipients scope to a client
      with an org-wide fallback, so "One Consultoria" and "João Raphael" can have
      different people alerted. Meta Page → client attribution lives on
      `meta_ads_lead_forms.client_id`; unattributed forms route to the org tier.
- [x] In-app channel: `notificacoes` router IS mounted in social-wiring
      (`app/main.py:245` `standard_routers=[..., "notificacoes", ...]`) — confirmed 2026-08-04
- [ ] **Verify live:** test lead triggers a real WhatsApp message + email

**Recipients decision (engineer, explicit):** there is no per-lead recipient subset analogous to
`upload_jobs.notify_recipients[]`, so `notify_new_lead` fans out to *every active row* in the
org's existing `notification_recipients` table — the same table and filter `notify_upload`
already trusts, minus the per-job narrowing. Not a hardcoded address, not an invented table.
A future "leads but not uploads" toggle is a `notify_on` column, not something this method invents.

**Surfaced → logged** (`auto-improvement.ndjson`, s1): `notification_log` is upload-shaped and
cannot trace a lead-triggered row back to its `meta_ads_leads.id`. Needs a generic
`source_kind`/`source_id` pair. N=2 ⇒ triage now, mandatory at the third notification source.

## Slice 5a — Webhook UI + ordering (C3) — ✅ merged `b301aa3d`

- [x] NEW `frontend/src/hooks/useMetaLeadgen.ts` (new file — keeps C3 disjoint from `useMetaAds.ts`)
- [x] Subscription-management card in `pages/meta/AdsLeads.tsx`:
      per-Page subscribed/not-subscribed badges · "Assinar páginas" · "Cancelar" ·
      callback URL with copy · `verify_token_configured` warning · scope-missing banner
- [x] Webhook health panel — `last_received_at === null` renders an explicit pt-BR diagnostic
      ("Meta has never called us"), not a bare 0 — the single most useful signal in the feature
- [x] Newest-first: default was already `data_entrada desc`, but that is a DATE — added a
      `created_at desc` tiebreaker so same-day leads order by real recency, not UUID
- [x] `loading` gated on `isPending || isFetching`, never `isLoading` (verified in the diff)
- [x] Complete loading / empty / error / gated / not-configured states; partial bulk-subscribe
      failure rendered per-page, never collapsed. 483 FE tests, tsc + vite build clean

## Slice 5b — Live push (C3) · ✅ **BUILT 2026-08-04** (un-suspended)

> Blocked by design, not by effort. The peer branch `feat/whatsapp-realtime-inbox` is building
> `seed/lib/backend/noctusai_lib/realtime` (SSE + Redis bus) for the WhatsApp/WAHA inbox. That is a
> **different live session** from this one (Meta Ads leads), but both would sit on the same seed
> realtime primitive, and shipping a second one (Supabase Realtime) would fork the seed.
> **Decision 2026-08-03 (operator):** finish all non-conflicting work first; once the peer lands,
> evaluate their transport together and decide how to touch that seed. Nothing here gets built
> until that assessment happens.

- [x] Evaluated the peer's `noctusai_lib.realtime` (SSE + Redis Stream). **Adopted it**;
      the originally-planned Supabase Realtime was dropped — a second transport would have
      forked the platform into two reconnect models and two auth models
- [x] `app/services/meta_leads_realtime.py` — per-org scope, `lead.new`, PII-narrowed
      wire projection (never `answers`/`raw` — free-text the list doesn't render)
- [x] SSE mount `/api/meta/leadgen/stream`; org from the AUTHENTICATED CALLER, never a param
- [x] `useLiveLeads` prepends via `setQueryData`; **never** invalidates the lead list
- [x] Visible `ao vivo / reconectando` badge — a dropped stream must not look like "no leads"
- [x] Seed fix: `REALTIME_EVENT_NAMES` was a hardcoded WhatsApp vocabulary every new
      surface would have had to edit — now a per-consumer `events` option
- [x] 7 hook tests + 11 service tests; FE 490, tsc + vite build clean
- [ ] **Verify live:** lead appears with no refresh, no loading flash *(needs deploy)*

## Slice 6 — erp-imobiliario consolidation (C2) — ⚖️ security half shipped, rest scoped out

- [x] **Fixed the HMAC-secret defect** — `_resolve_meta_secret` returned the *verify token*
      as the signing secret. Both branches were wrong: no matching `meta_config` row ⇒
      `secret=None` + `bypass_when_unset=True` **accepted unverified traffic into a write
      path**; a matching row ⇒ genuine Meta deliveries 401'd. Now the App Secret,
      `bypass_when_unset=False`. 8 status-pinned tests
      (`tests/routers/test_meta_webhook_signature.py`)
- [x] Replaced the hand-rolled `parse_lead_webhook` (read `entry[0].changes[0]` only,
      silently dropping every batched delivery) with the seed's all-entries parser
- [x] GET handshake returns the challenge as a **string** — the old `int(challenge)` raised
      on Meta's opaque non-numeric challenge, and that is the ONE synchronous call deciding
      whether the subscription saves at all
- [ ] ⏸ Migrate the router fully onto the seed capability / delete the hand-rolled Graph
      client — **deliberately not done.** erp is a testing ground still being refined, its
      Meta receiver is inert (0 config rows, 0 leads ever), and **the canon is
      social-wiring's `leadgen_router.py`**. The remaining erp code is drift against that
      canon, and rewriting a dead receiver is not worth carrying into a prod promotion.
      The *dangerous* half — a receiver that accepted unsigned writes — is closed.

## Slice 7 — CSV recovery importer (conditional)

- [ ] **Operator:** confirm whether pre-2026-04-28 exports / Meta notification emails exist
- [ ] If yes — add a Meta lead-export shape to `modules/leads/importer/shape_detector.py`
- [ ] If no — record "forward-only, history unrecoverable" in the roadmap decision log

---

## 🚀 Deployment — DONE 2026-08-04

| | |
|---|---|
| **prod** | `27c1522f` (was `4db0c4bc`) — 104 commits |
| **Rollback pointer** | `prod-backup` = `4db0c4bc`; VPS tag `backup/predeploy-20260804-181402` + tar |
| **Images** | social-wiring + erp-imobiliario rebuilt from `27c1522f`, health-probed, tunnel re-resolved |
| **Fleet** | 14 healthy / 0 unhealthy |

**Verified in the PRODUCTION shape** (not just dev-green), inside `noctus-social-wiring`
and again over the public URL:

| Check | Result |
|---|---|
| `GET /stream` unauthenticated | **401** |
| Handshake, wrong verify token | **403** |
| Handshake, real token, non-numeric challenge | **200**, echoed as a STRING |
| Unsigned `POST` | **401** (no bypass) |
| **Signed POST over the public URL, Meta's own User-Agent** | **200** |
| Replay of the same delivery | **200 `duplicate`** — not reprocessed |
| Tampered body | refused |

🔴 **Cloudflare 1010 — read this before debugging a "dead" webhook.** The public `POST`
is rejected with CF error **1010** for a `Python-urllib` User-Agent, but returns **200** for
Meta's real UA (`facebookplatform/1.0 (+http://developers.facebook.com)`) and for a browser
UA. So Meta's deliveries pass — but **any hand-rolled probe with a default client UA will
look like a hard failure when nothing is wrong.** Always probe with Meta's UA.

Smoke rows were deleted afterwards; the inbox is empty and the 958 stored leads are untouched.

## Operator steps (cannot be done in code)

Permissions, App Review, Live mode and OAuth callbacks are **already done**. Remaining, at
`developers.facebook.com`, and **only after Slice 2 is deployed to prod**:

- [ ] Products → Webhooks → **Page** object
- [ ] Callback URL `https://social.noctusai.com/api/meta/leadgen/webhook`
- [ ] Verify Token = `zGjmbt-Rk2q_DHOmug8_i-R8Ic5HToYWgpc-4b_ShZY`
      *(generated + stored Fernet-encrypted in `social_wiring.app_integration_config`
      under `meta_webhook_verify_token`; prod resolves Meta config from the vault, NOT
      `.env` — the VPS `.env` carries no `META_*` keys at all. Verified live above.)*
- [ ] **Verify and Save** (Meta GETs the endpoint synchronously — it must be live first)
- [ ] Tick the **`leadgen`** field → Subscribe *(app-level)*
- [ ] Run our bootstrap `POST /api/meta/leadgen/subscriptions` *(per-Page level)*

> ⚠️ App-level and per-Page subscription are **both** required. Either one alone delivers
> nothing, silently — the most common lead-ads misconfiguration.

---

## Gates before ship

- [x] Gates re-run on the **merged tip** (per-branch green ≠ integration green) — 2026-08-04
- [x] Merge-integrity audit: prod/main are strict ancestors of dev; all 11 branches
      contained; every branch file accounted for. Found + fixed ONE real casualty —
      conflict markers committed into migration `042` by the renumber
- [ ] `compliance-reviewer` on the diff
- [ ] `security` advisory on the public receiver
- [ ] `noctus_vps_logs` — `meta-leadgen-webhook: secret unset` must be **absent**

---

## Decision log

| Date | Decision |
|---|---|
| 2026-08-03 | Leads land in `meta_ads_leads` (raw ledger) **and** normalize into `social_wiring.leads` (unified base) |
| 2026-08-03 | Arrival fans out to in-app + WhatsApp + email; list updates live via Supabase Realtime, no polling, newest-first |
| 2026-08-03 | History: Meta deletes leads after 90 days, unrecoverable by any means — forward-only unless off-platform exports exist |
| 2026-08-03 | erp-imobiliario consolidates onto the seed capability (verified dead: 0 config rows, 0 leads) |
| 2026-08-03 | No seed router factory — pure functions in seed, HTTP router in product (the orphaned `create_whatsapp_webhook_router` is the precedent against it) |
