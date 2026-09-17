# community — modules 1–3 (2026-09)

> Product: `products/community/` — an online community management center for ONE paid
> women's community, client **Mônica Tangerino**. Single-tenant, pt-BR, responsive web.
> Managers run a back office (`admin` / `moderador`); members use their own portal.
> Ports 8017/8210, schema `community`.
>
> Planning decisions live in `products/community/MASTER-PROMPT.md` and
> `.scaffold-brief.md`. The per-module contracts (endpoint shapes, security amendments,
> product decisions) were authored per module and are the acceptance gates the engineers
> built against.

## Context

The user asked for the whole thing in ONE release (their explicit decision), so the modules
are sequenced by dependency rather than by shipping increment: members and tiers first,
because payments transition member status, and WhatsApp membership sync is derived from tier
entitlements. Development and the soft launch run on NoctusAI's own Stripe / Asaas / WhatsApp
accounts; swapping to Mônica's is configuration, not code.

## Milestones

| # | Milestone | Status |
|---|---|---|
| M1 | **Product scaffolded seed-first** — `create_product_app` / `createProductApp`, ports 8017/8210, schema `community`, catalog row, `status_pagina`. | ✅ 2026-09-16 (`ab6dbf43`, `a80e5f95`) — backend 50/50, vite build clean. Three scaffold-tool bugs found and fixed in-flight (port collision, duplicate icon import, comment over-substitution). |
| M2 | **Modules 1–2 complete and dev-validated** — members/CRM, manager-configured tiers, manager-authored application form with approve/reject, public checkout (Stripe card / Asaas Pix+boleto), signed webhooks driving `pendente→ativo→atrasado→pausado→cancelado`, subscriptions + payments views, Turnstile, LGPD-safe CPF pass-through. | ✅ 2026-09-17 — backend **218** tests, frontend **98** tests, `tsc`+`vite build` clean; migrations 001–008 applied to the live shared Supabase; anon privileges REVOKED across the schema and verified with live anon probes; BE↔FE cross-checked against the OpenAPI surface (no drift). Seven adversarial-review blockers fixed before dispatch, each pinned by a named test. |
| M3 | **community modules 1–2 exposed in prod** — consent recorded, fleet compose + tunnel ingress + build-scope registered, bless → promote → `deploy_image`, then `deploy_verify` + health + `spa_smoke`. | ✅ 2026-09-17 — **live at https://community.noctusai.com**. Ran the exact promoted revision (`2b1ffcd1`), `deploy_verify` verdict `ok` with `startup_hook_error: null`, `/api/health` 200 internally and through the edge, `spa_smoke` 7/7 (real 363 KB `application/javascript` bundle, `/login` deep link 200). Payment keys not yet set, so checkout fails closed until they are; members/tiers/applications are fully functional without them. Two gates read a STALE primary checkout during this release and each looked like a tool bug: `spa_smoke`'s default roster omitted community (roster derives from the local `build-scope.txt`) and `deploy_verify` reported `no port resolved` (it reads `expose:` from the local compose). One stale checkout, two false symptoms — re-verified after re-syncing. |
| M4 | **Module 3 (WhatsApp) built** — tier-driven group membership sync as manager-confirmed batches, broadcasts, forward-only ingest feeding engagement points, AI-flag hand-off. Seed reuse survey done: client/group-ops/mappers/webhook-router/dedup/engagement/jobs all CONSUMED; identity resolver PROMOTED out of social-wiring; three social-wiring services explicitly NOT reused (DM-inbox and multi-line domains). | ✅ built **and integrated to `dev`** 2026-09-17 — seed lift `6b9b831f` (28 seed tests + **4549** social-wiring tests, since the lift rewires the live consumer's identity service), backend `bad6f37e` (**354** tests), frontend `582b729a` (tsc clean, **83** tests, real `vite build`). Migration **009 applied**: 10 tables, RLS enabled on all, 4 policies each except `jobs`/`engajamento_pontos` (deliberately policy-less ⇒ deny-all), **0 `anon` grants** — verified by `pg_class`/`pg_policy` query, not by the migrate tool's own report. Integration caught a real defect the per-branch green had hidden: the roster fixture carried no `org_id`/`nome`, so `test_matches_participant_by_phone` was asserting the UNMATCHED path while claiming to prove a match; production code was correct (org-scoping that lookup is required — phone numbers are not org-unique), and `test_a_member_of_ANOTHER_org_is_never_matched_by_phone` now pins it. NOT RELEASED by decision: the seed lift widens the build scope fleet-wide, and the module cannot move a real participant until M5. |
| M5 | **WhatsApp operator prerequisites** — a second WhatsApp number, a `waha-community` container (WAHA pinned; the live instance is Core/single-session and its one session belongs to social-wiring), QR pairing by a human, an explicit `set_webhook` (the instance default points at n8n), and one real two-participant add to verify the `invite_required` mapping before any bulk operation. | ⏳ blocked on the user — physical device + number. Runbook written. |
| M6 | **Live payment run** — Stripe + Asaas test keys, Turnstile key pair, one tier with gateway references, one end-to-end paid checkout activating a member. | ⏳ blocked on the user — accounts and keys. |
| M7 | **Swap to the client's accounts** — Mônica's Stripe/Asaas/WhatsApp; configuration only, no code change. | ⏳ after M6. |

## Trigger conditions

- **T1 · module 3 to prod** — when M5 completes (number paired, webhook explicitly set). Ship
  the seed lift and module 3 together in their own release, deliberately separate from M3's, so
  a fleet-wide rebuild is never combined with community's first exposure.
- **T2 · `MODO_INGEST`** — defaults to `moderacao` (message text stored, required for AI
  flagging) and the member consent text ships with it. Flip to `metrica` (no text stored) if the
  client prefers; points keep working, AI moderation stops.
- **T3 · retention job** — `NOC-REMEDIATE[whatsapp-retention]` and
  `NOC-REMEDIATE[webhook-inbox-retention]` both wait for a scheduler in this product. Batch them
  into the first scheduler-enabled slice; until then deletion is manual.
- **T4 · modules 4–11** (feed, forum, chat, content library, events, engagement UI, moderation
  queue, manager dashboard) — the user's scope is all of them; sequence after M6 proves the
  money path.

## Open questions for the user

1. Community theme/niche is still undefined, so UI copy and branding stay neutral.
2. Tier names and prices are manager-configured; none exist yet.
3. Whether `community` should be licensed to a separate client org rather than the NoctusAI
   house org (currently the house org, matching "our accounts for the soft launch").
