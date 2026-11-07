# core-host-retirement-2026-11 — retire core.noctusai.com; apex serves website + core SPA

> **Durable record** (per `KB § PATTERNS/common/roadmap-tracking.md`).
> Origin: owner decision 2026-11 to retire the hostname `core.noctusai.com`.
> Decision: **P0 ships dormant (core host keeps working, nothing removed); P1/P3 need owner confirmation.**

## Origin

The owner is retiring `core.noctusai.com`. Target layout: `noctusai.com` serves the website (`/`, `/en*`, `/produtos /solucoes /precos /contato /lista-de-espera /sobre /404`, `sitemap.xml`, `robots.txt`, `llms.txt`) AND the core SPA (`/login`, `/painel`, `/admin/*`, `/team`, `/settings`, `/billing`, `/checkout/*`, `/onboarding`, ...). `/api/*`, `/consent/*`, `/invite/*`, `/_*` stay as they are. Nothing below is live until its phase ships.

## Trigger conditions (the "when")

| # | Trigger | Detection signal | Why it tips the balance |
|---|---|---|---|
| T1 | P0 slices merged to `dev` | R1/R2/R3/R6 branches in the merge queue log | P1 flips real config; code must be dormant-ready first |
| T2 | Owner confirms P1 | explicit owner message | P1 touches third-party dashboards + prod env |
| T3 | `legacy_core_host_redirect` on >= 30 days with per-host telemetry showing ~0 core-host traffic | telemetry rows per `Host` | proves nobody still depends on the old host |
| T4 | Owner confirms P3 AND `feat/nosnolimiar-rename` landed | owner message + branch merged | ingress/DNS removal is irreversible-ish; rename touches the same hostnames |

**Today's status**: none fired; P0 in flight.

## Phase 0 — dormant code + tooling (core host keeps working)

| # | Title | Files | Status | Verify recipe |
|---|---|---|---|---|
| R1 | backend flags (`legacy_core_host_redirect`, `core_app_origin` handling) | core backend config | in flight (other slice) | flag off => behaviour byte-identical; flag on in test => redirect |
| R2 | `/painel` route in core SPA | `products/core/frontend/src/main.tsx` | in flight (other slice) | route renders real data on today's host |
| R3 | `CORE_APP_HOME` | core FE/BE | in flight (other slice) | login lands on configured home |
| R6 | tooling + fitness + docs (this slice) | `sso_smoke.py` (`host`/`core_url` param, env `NOCTUS_CORE_APP_URL`), `transcription/client.py`, `test_core_website_route_disjoint.py`, `route_paths_scan.mjs`, `.env.example`, KB docs | **shipped** | `sso_smoke(host="noctusai.com")` resolves apex; disjoint test green |

**Behavior guarantee**: defaults unchanged (`https://core.noctusai.com`).

Lead-form track (parallel, independent of host): **L1** seed LeadForm/Turnstile organ; **L2** Turnstile fail-closed; **L3** CORS/Turnstile hostnames for the agents + SW origins.

## Phase 1 — switch to apex (DEFERRED — fires on T1 + T2, owner confirms)

| # | Title | Scope | Verify recipe |
|---|---|---|---|
| R5 | integrations | add the apex to Supabase Auth URLs (site URL + redirects), Stripe (redirect/webhook/portal), Google consent (origins + redirect URIs), Meta App Review URLs, Turnstile hostnames | each dashboard shows the apex; Google sign-in + Stripe test checkout succeed |
| R4 | devops | VPS env `PRODUCT_URL_CORE`, `APP_BASE_URL`, `CORS_ORIGINS`; `products.url_base` row; flag on; workflow `VITE_CORE_URL` (+ `VITE_CORE_API_URL`) set to the apex; fleet rebuild in a window agreed with steward noctusai-51 AFTER the unsigned-webhook rollout | `sso_smoke(host=apex)` pass; `sso_cors_smoke` pass; login; SSO hand-off to a product; test checkout; Google sign-in |

Note: `.github/workflows/build-and-push.yml:89-90` bakes the core host today (existing drift vs the apex documented in `.env.example`); changed here, not earlier.

**Rollback (P1)**: revert VPS env + `url_base` row, flag off, rebuild images with the old `VITE_CORE_URL`; third-party dashboards keep BOTH hosts registered until P3 so rollback needs no dashboard edits.

## Phase 2 — redirect soak (DEFERRED — fires after P1 verified)

`legacy_core_host_redirect` on for >= 30 days; per-host telemetry (requests by `Host`, referrers, API-key/webhook callers).
**Exit**: T3. **Rollback (P2)**: flag off (core host serves directly again).

## Phase 3 — removal (DEFERRED — fires on T3 + T4, owner confirms)

Tunnel ingress removal (after `feat/nosnolimiar-rename` lands) -> DNS deletion -> remove flags, `core_app_origin`, the `/` alias (and its exception in the disjoint test), `pages/Landing.tsx` and `LandingFooter` -> add a keeper banning the `core.noctusai.com` literal (also drops `DEFAULT_CORE_URL` in `sso_smoke.py`). Consider deriving `_WEBSITE_PATH_STEMS` at build time (`NOC-REMEDIATE[website-app-path-derivation]`; guarded meanwhile by the fitness test).
**Rollback (P3)**: re-add ingress + DNS record (kept in a recorded snapshot before deletion); code removal is a revert.

## Anti-goals

- No removal of anything in P0; no workflow change before P1.
- No dev-container gate (fleet dormant; prod-only).

## Open questions (unknowns to verify before P1)

- **Q1**: actual VPS `.env` values (`PRODUCT_URL_CORE`, `APP_BASE_URL`, `CORS_ORIGINS`) — repo only documents them.
- **Q2**: external dashboards (Supabase, Stripe, Google, Meta, Turnstile, Cloudflare) — current registered hostnames unknown from the repo.
- **Q3**: admin email / WhatsApp templates stored in the DB that embed the core host (not greppable in the tree).

## Decision log

- **2026-11-07**: roadmap authored; P0 ships dormant; `_WEBSITE_PATH_STEMS` kept hand-maintained with an AST drift test rather than a build-time export (needs a node step; deferred to P3).

## Retrospective (filled at first trigger fire)

*To be filled at P1.*

## Composes with

- `KB § PATTERNS/frontend/core-url-routing.md`, `KB § GUIDES/production-deploy.md`, `KB § PATTERNS/backend/boundary-contract-tests.md`.

## File trail

- `mcp/noctusai/tests/test_core_website_route_disjoint.py`, `mcp/noctusai/node/route_paths_scan.mjs`
- This doc.
