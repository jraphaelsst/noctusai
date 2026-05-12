# YouTube Crawler — MASTER-PROMPT

> Authoritative development guide for the YouTube Crawler product.

## Purpose

YouTube Data API v3 + Drive + WAHA + SMTP — quota-aware uploads with Fernet-encrypted refresh tokens. Operators authenticate against Google (YouTube + Drive), the product polls source-material drops in Drive, transcodes/uploads to YouTube with daily-quota awareness, and notifies operators of progress / failures via WhatsApp (WAHA) and email (SMTP) digests.

## Architecture

- Schema: `youtube_crawler`
- Backend port: 8008 | Frontend port: 8150
- Tenant key: `org_id`
- Auth: SSO via seed's `make_get_current_user` factory; Google refresh tokens stored Fernet-encrypted in `youtube_crawler.google_credentials` (table introduced by domain implementation).
- Backend path: `products/youtube-crawler/backend/app/`
- Frontend path: `products/youtube-crawler/frontend/src/`

## Current state (2026-05-11)

**Scaffolded only.** Backend ships seed wiring (`create_product_app` + `create_database_module` + `create_dependencies` + `create_product_limiter`) with `0` routers / `0` services. Frontend ships seed pages (Dashboard, Equipe, Landing, Login, AcceptInvite, ForgotPassword, NotFound) with no domain UI. Migration `001_youtube_crawler.sql` provisions schema + `status_pagina` + `invitations` only — zero domain tables.

Tests: 31 framework-suite tests (FrameworkEndpoints / TeamFlow / NotificationFlow / AuthBoundary / TeamRouter*) inherited from `noctusai_lib.testing` — all pass.

Domain implementation tracked in `projects/youtube-crawler-domain-implementation/` (filed 2026-05-11). The project resolves: Google OAuth flow + Fernet vault, Drive polling + drop-folder convention, YouTube upload pipeline + quota tracking, WAHA notification channel, SMTP digest, operator UI.

## Key Domains (planned)

### Auth & credentials
- **google_oauth** — Google sign-in for YouTube + Drive scopes; refresh-token storage via Fernet-encrypted column; SSO context binds to operator's org_id.
- **credentials_router** — operator-facing endpoint for "connect Google" / "disconnect" / "rotate"; admin-only management.

### Upload pipeline
- **drive_watcher** — periodic poll of Drive drop folders (per-org convention); enqueues source files for upload.
- **upload_worker** — YouTube Data API v3 resumable-upload client; backoff on quota / transient failure; persists state in `youtube_crawler.upload_jobs`.
- **quota_tracker** — daily-quota accounting against YouTube Data API limits (cost-per-call tabulated server-side); pauses jobs at threshold.

### Notifications
- **waha_notifier** — pushes upload progress / failure summaries to operator WhatsApp via the seed's `noctusai_lib.integrations.whatsapp` adapter.
- **smtp_digest** — daily / weekly digest email; piggybacks on the seed's `BaseDigestService` (`KB § PATTERNS/digest-seed.md`).

### Operator UI
- **upload_dashboard** — live job list, quota usage gauge, retry / pause / cancel controls.
- **credentials_page** — connect / disconnect Google; show scope grants.
- **digest_preferences** — opt-in channels (WAHA / SMTP), digest cadence.

## Rules

- Seed framework non-negotiable — domain routers attach through `create_product_app()`'s `standard_routers=[...]` seam. ¬ re-wire CORS, exception handlers, ∨ middleware locally.
- Single `001_youtube_crawler.sql` is the fresh-start migration. Schema changes edit 001 in-place during the implementation project ∧ ship additive `002+` patches for live DBs (single-001 convention; → `KB § PATTERNS/database-rls.md`).
- Auth via the canonical factory: `Depends(get_current_user_org)` wired in `app/dependencies.py` via `make_get_current_user_org`. ¬ wire `ProductDependencies.{get_org_id,get_user_role,get_user_client}` through `Depends(...)` — positional args become required query params (→ `KB § PATTERNS/backend.md § Auth — canonical pattern`).
- LGPD-first: operator PII (Google email, refresh token, channel handle) flagged at every write site via `noctus.dev.lgpd_flag`. Fernet column is LGPD-sensitive — masked in audit logs.
- Refresh-token encryption uses the seed's vault primitive (`noctusai_lib.integrations.<vault>` if it ships at adoption time; otherwise file the seed real-adapter project per "Verify the seed ships it" rule).
- Rate-limit policies: prefer named imports from `noctusai_lib.api.rate_limit_policies` (`DEFAULT_AI_RL` / `DEFAULT_AUTH_RL` / `DEFAULT_WEBHOOK_RL` / `DEFAULT_PORTAL_RL`) over inline `"30/minute"` literals.
- Webhook receivers (if Google Pub/Sub adopted for Drive change notification) follow the 5-pin compliance contract (→ `KB § PATTERNS/webhook-signatures.md`); seed ships the canonical receiver shape at `products/seed/backend/app/routers/webhook_router.py`.
- Doc-code coherence: tool/script/MCP-tool Δ referenced here ⇒ update this MASTER-PROMPT in the same commit — discover drift via `grep -rn "<tool-name>" products/youtube-crawler/`. (CLAUDE.md §1 — doc-code coherence rule.)

## Testing

```bash
cd products/youtube-crawler/backend && pytest
cd products/youtube-crawler/frontend && npx vite build
```

Framework-test suites inherit from `noctusai_lib.testing` (FrameworkEndpointsSuite / TeamFlowSuite / NotificationFlowSuite / AuthBoundarySuite / TeamRouter*Suite). The current scaffold ships only these inherited suites; domain tests land alongside their routers/services in the implementation project.

Seed mocks: `MockSupabaseClient` (2026-05-11) deep-copies caller inputs at storage time so UPDATE/DELETE write-propagation doesn't mutate module-level fixture dicts; `_eval_is` now handles PostgREST IS-NULL semantics; `_FilterMixin.not_` actually negates.

## Common commands

- Compliance review (LGPD / webhook-pins / status-assertion / 10 new detectors added 2026-05-11): `noctus.dev.review --product youtube-crawler`. New detectors: `check_doc_tool_reference_drift` (this doc), `check_no_silent_ok_comment`, `check_auth_dep_anti_pattern`, `check_mcp_path_via_settings`, `check_mcp_write_tool_worktree_arg`, `check_pipefail_grep_q`, `check_archive_staleness`, `check_dispatcher_staleness`, `check_branch_orphan`, `check_gitignore_drift`.
- Cleanup triage (cross-product / cross-tool / intra-file hygiene): `noctus.hound.scan`.
- Storage triage (artifacts / environments / stale worktrees): `bash scripts/mole.sh scan`.
- Fresh-clone bootstrap auto-hydrates every `products/*/backend/requirements.txt` into the shared venv (`scripts/bootstrap-worktree.sh` + `scripts/setup.sh`, 2026-05-11) — no per-product `pip install -r` step needed.

## Deploy

```bash
./start.sh                  # full stack (Docker, with youtube-crawler from PRODUCTS registry)
./start.sh tunnel youtube-crawler   # cloudflare quick-tunnel for OAuth / WAHA online testing
./stop.sh                   # graceful tear-down
```

Backend container port: 8008 (canonical, matches `start.sh` PRODUCTS registry + LANDSCAPE table). Frontend: 8150.

## Dependencies

- Backend: `noctusai_lib` (code library) + `noctusai_seed` (framework) + `google-api-python-client` + `google-auth` + `cryptography` (Fernet) + `httpx` (WAHA) — added when domain routers land.
- Frontend: `@noctusai/lib` (code library) + `@noctusai/seed` (framework)
