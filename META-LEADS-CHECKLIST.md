# META-LEADS-CHECKLIST.md — campaign-lead ingestion, end to end

> **Working tracker** for the Meta Lead-Ads ingestion initiative started 2026-08-03.
> Tick items as they land; every line names the file it touches so progress is auditable.
> Durable roadmap home: `project-history/roadmaps/meta-ads-console-2026-07.md` (Phase 3.2 —
> this checklist is its execution surface). Full rationale for every decision lives there and
> in the approved plan; this file is the *what shipped* view.

**Status:** 🟢 **integrated to `origin/dev` @ `7f1495db`** · 2026-08-04

Merged alongside the WhatsApp realtime inbox and Imóveis/Vista; all three green together.
Gates on the pushed tip: social-wiring **1658** · erp **2161** · seed **2662** — exit 0.
✅ Migrations `041` + `044` **applied and schema-verified** 2026-08-04.
**Blocking prod:** operator held the deploy (dev-only for now) + the Meta dashboard steps.
See `META-LEADS-HANDOFF.md`.

**What remains is not code.** Every open box below is one of: (a) a **live verification** that
needs a prod deploy, (b) an **operator step** in the Meta App Dashboard that no code can perform,
(c) **Slice 5b**, suspended by design until the peer's seed realtime work is assessed, or
(d) **Slice 7**, conditional on whether off-platform lead exports exist.

**Suite state at the tip:** social-wiring **1565** · erp-imobiliario **2161** · seed lib **2545** ·
frontend **483** — all by exit code, all on the merged tip (per-branch green ≠ integration green).

**Prod posture (operator, 2026-08-03):** ❌ **no prod deploy until everything is built and
validated.** Slice 0 is on `dev` only. One promotion at the end, not a trickle.

**Build order right now:** Slices 1 · 2 · 3 · 4 · 5a · 6 (all independent of the peer branch) →
then pause. Slice 5b (live push) stays suspended until the peer's seed realtime work is assessed.

**Migration numbers:** `044` (webhook inbox, this branch) · `041` (leads.meta_lead_id, Slice 3).
🔴 **040 was NOT free** — peer branch `feat/wa-inbox-schema` (commit `b524b097`) already holds
`040_whatsapp_inbox_realtime_schema.sql` on an **unpushed local branch**. Neither
`ls migrations/` (shows 039 as highest) nor `git log origin/dev` reveals it. The only check that
works is `git diff --name-only origin/dev...<branch>` across **every local branch**, not just
remote ones. Re-run that immediately before writing any migration here.

---

## Why (one paragraph)

Campaign leads stopped arriving because nothing drives the pull path: the daily cron
(`meta_ads/scheduler.py`) syncs accounts/hierarchy/insights/activities but **never** calls
`LeadsSyncService`, so leads only moved when someone pressed "Sincronizar leads" — last done
2026-07-29. There is also no push path at all (no webhook, no Page subscription), and Meta
**permanently deletes** lead data after 90 days, so the un-synced tail expires silently. Fix =
a webhook for freshness + a scheduled sync for correctness, both landing in one idempotent
upsert keyed on Meta's own lead id.

---

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
- [ ] In-app channel: `notificacoes` router mounting still to confirm (email + WhatsApp shipped)
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

## Slice 5b — Live push (C3) · 🔴 **SUSPENDED — do not build**

> Blocked by design, not by effort. The peer branch `feat/whatsapp-realtime-inbox` is building
> `seed/lib/backend/noctusai_lib/realtime` (SSE + Redis bus) for the WhatsApp/WAHA inbox. That is a
> **different live session** from this one (Meta Ads leads), but both would sit on the same seed
> realtime primitive, and shipping a second one (Supabase Realtime) would fork the seed.
> **Decision 2026-08-03 (operator):** finish all non-conflicting work first; once the peer lands,
> evaluate their transport together and decide how to touch that seed. Nothing here gets built
> until that assessment happens.

- [ ] ⏸ Evaluate the peer's landed `noctusai_lib/realtime` transport
- [ ] ⏸ Decide the Meta-leads live-session shape on top of it
- [ ] ⏸ Live lead list prepends via `queryClient.setQueryData` — no refetch, no polling
- [ ] ⏸ **Verify live:** lead appears with no refresh, no loading flash

## Slice 6 — erp-imobiliario consolidation (C2)

- [ ] Migrate `products/erp-imobiliario/backend/app/routers/meta_api.py` onto the seed capability
- [ ] Fix the HMAC-secret defect (was using `webhook_verify_token`; must be the **App Secret**)
- [ ] Delete the hand-rolled Graph client `app/services/meta_api_service.py`
- [ ] Replace `parse_lead_webhook` (drops batched deliveries) with the seed parser

## Slice 7 — CSV recovery importer (conditional)

- [ ] **Operator:** confirm whether pre-2026-04-28 exports / Meta notification emails exist
- [ ] If yes — add a Meta lead-export shape to `modules/leads/importer/shape_detector.py`
- [ ] If no — record "forward-only, history unrecoverable" in the roadmap decision log

---

## Operator steps (cannot be done in code)

Permissions, App Review, Live mode and OAuth callbacks are **already done**. Remaining, at
`developers.facebook.com`, and **only after Slice 2 is deployed to prod**:

- [ ] Products → Webhooks → **Page** object
- [ ] Callback URL `https://social.noctusai.com/api/meta/leadgen/webhook`
- [ ] Verify Token = the exact `META_WEBHOOK_VERIFY_TOKEN`
- [ ] **Verify and Save** (Meta GETs the endpoint synchronously — it must be live first)
- [ ] Tick the **`leadgen`** field → Subscribe *(app-level)*
- [ ] Run our bootstrap `POST /api/meta/leadgen/subscriptions` *(per-Page level)*

> ⚠️ App-level and per-Page subscription are **both** required. Either one alone delivers
> nothing, silently — the most common lead-ads misconfiguration.

---

## Gates before ship

- [ ] `noctus.dev.validate` on the integrated branch
- [ ] `compliance-reviewer` on the diff
- [ ] `security` advisory on the public receiver
- [ ] Gates re-run on the **merged tip** (per-branch green ≠ integration green)
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
