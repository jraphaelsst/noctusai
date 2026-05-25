# social-wiring-followups — Project Document

> The 4 follow-ups surfaced (but unfiled) at the 2026-05-24 social-wiring delivery
> ([[project_social_wiring_delivery_followups]]). Branched 4 parallel engineers off
> `origin/dev`, integrated by the architect (peer-of-its-own-task, self-branching mode).

- **Created:** 2026-05-25
- **Status:** ✅ **SHIPPED** — all 4 follow-ups delivered + integrated to `dev`. E1 seed-meta token-bundle · E2 `_has_oauth_credential` N=3 DRY → `app/utils.py` · E3 seed `make_get_settings` factory salvage · E4 media_creation render DI seam (6 RED → green).
- **Owner:** rapha · architect
- **Slug:** `social-wiring-followups`

## 3a. Seed-first analysis

2 of 4 are seed-level (E1 `noctusai_lib.integrations.meta`, E3 `noctusai_seed.config`) — cross-product by construction, per-product code count = 0. E2 (`has_oauth_credential`) is a product-local N=3 DRY collapse (3 services → 1 helper). E4 is a product-local DI seam (no seed change). Seed work proven on social-wiring (the canonical pilot).

## 6. What shipped

| # | Layer | Change | Verify |
|---|---|---|---|
| E1 | seed/lib | `exchange_*_bundle` + `TokenBundle` (preserve `expires_in`/`token_type`); string fns delegate, back-compat | 113 meta tests ✓ |
| E2 | SW product | `app/utils.has_oauth_credential(store, org_id, provider, *, require_token)` ; 3 service dupes removed | `test_utils` 6 ✓ |
| E3 | seed/framework | `make_get_settings` DI-seam factory (Class-A) salvaged from `eng/sw-settings-di-rewrite@1b3e45d0` | 3 config tests ✓ |
| E4 | SW product | `get_generation_service`/`get_post_service` DI seams; render path no longer builds a real Supabase client | media_creation 6 RED→green |

Full SW backend suite: **497 passed**. Cross-cutting docs applied serially by the integration owner: `KB § INTEGRATIONS/meta.md` (bundle rows) · `KB § PATTERNS/di-test-seam.md` (Class-A section).

## 7. Open follow-ups (surfaced, not in this batch)

1. **`seed-config-di-consume`** — social-wiring still wires a **product-local** `get_settings` + `build_credential_store(client, *, encryption_key=…)`; migrate to consume the now-shipped seed `make_get_settings` (verify-the-seed-ships-it → consume-it). erp/core/daily-life inherit at N≥3.
2. **`seed-meta-exchange-bundle` consume** — no consumer reads `expires_in` yet; wire when a refresh-deadline workflow needs it.

## 11. Change log

- **2026-05-25** — 4 engineers dispatched off `origin/dev` (1 message). E2 correctly STOPPED on a stale fork base (harness based its worktree off `origin/main`, not `dev` — the `db482e5c` Meta-fork retirement was invisible). Architect integrated E1/E3/E4 patches via `git apply --3way` (E1+E4 context-collisions from dev's video-publish + `get_publish_service`, resolved keep-both) + did E2 inline against dev's correct files. All green; FF-pushed to `dev`.
