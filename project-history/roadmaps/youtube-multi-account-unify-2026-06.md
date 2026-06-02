# Roadmap · YouTube multi-account + unified Conexões — 2026-06

**Slug:** `youtube-multi-account-unify` · **Branch:** `feat/youtube-multi-account-unify` (off `origin/dev` @ 2faf841c) · **Product:** social-wiring (`:8011`, prod `social-wiring.noctusai.com`)

## Goal
Make YouTube a first-class **multi-account** integration (connect / detach / set-active / swap), mirroring the WAHA multi-connection model, with a **single unified "Conexões" page** presenting WhatsApp + YouTube + other providers as cards. Fix the OAuth `redirect_uri_mismatch`.

## Why (user, 2026-06-01)
User clicked "Connect YouTube" on `/configuracoes` → Google `redirect_uri_mismatch`. Wants to attach/detach/swap multiple YouTube accounts like the existing multiple WAHA setups, with cards listing connected accounts for both WAHA and YouTube.

## Decisions (user-ratified 2026-06-01)
1. **UI:** ONE unified "Conexões" page — card sections for WhatsApp + YouTube + other providers. Retire the single-account YouTube tab in Configurações.
2. **Legacy flow:** multi-account = single source of truth. Auto-migrate the existing single-account credential → `integration_accounts`; retire/redirect the legacy connect button; pipeline resolves the chosen/default account.
3. **OAuth envs:** register redirect URIs for localhost **and** production (`social-wiring.noctusai.com`).

## Findings (verified against live tree + running container)
- Multi-account backend **already built**: `integration_accounts_router` (CRUD + YouTube OAuth start/callback), `integration_account_service` (Fernet, multi-row), `integration_providers` registry. FE `Integrations.tsx` + `useIntegrationAccounts` + `AddAccountModal` exist.
- 🔴 Migration `005_integration_accounts.sql` **never applied** to live Supabase (PGRST205 — table missing). Multi-account dead in prod.
- 🔴 **Consumption gap:** every YouTubeService build site (`upload.py`, `videos.py`, `chat_router.py`, `whatsapp_router.py`, `settings.py`) uses the SINGLE-account `CredentialStore`. `integration_accounts` rows are never read → "swap" has no effect.
- 1 legacy single-account youtube credential row exists in `social_wiring.credentials` (the auto-migration source).
- Redirect URIs the app sends: `…/api/youtube/oauth/callback` (legacy) + `…/api/integrations/accounts/youtube/oauth/callback` (multi).
- WAHA multi-account lives on `/conexao` (rows, full manage/QR). Integrations on `/integrations`. Both in nav; `integrations` status_pagina row seeded by migration 005 (so currently ungated/hidden until applied).

## Slices
- [ ] **S0 · DB** — apply migration 005 to Supabase (additive/idempotent). Verify table + RLS + status_pagina row.
- [ ] **S1 · Backend wire** — YouTube account-resolver (default/chosen integration_account → decrypt → creds); thread optional `account_id` through upload/videos/chatbot; one-time auto-migration of legacy single-account cred → integration_accounts(is_default); retire legacy connect endpoint (keep callback for in-flight). Tests.
- [ ] **S2 · Frontend** — unified "Conexões" page: card sections WhatsApp + YouTube + providers; connect/detach/set-active; channel labels+badges; retire single-account YouTube tab (redirect). Tests.
- [ ] **S3 · Ops/prod** — GCC redirect URIs (user); set `OAUTH_REDIRECT_BASE_URL=https://social-wiring.noctusai.com` in prod; deploy; verify SSO + connect round-trip in prod shape.

## Phase 2 — clients + channel objects + card-template organ + live switching + consent keeper (2026-06-01)

**Branch:** `feat/social-multiaccount-clients` (off `origin/dev` @ ab9f8e5e). **Why:** Phase-1 connected the account but the UI doesn't reflect it (no add-account, raw creds exposed, no real channel data, no client grouping). User is an agency tracking several **downstream clients'** social medias and wants per-client grouping + few-click data switching + a mandated reusable provider-card.

**User-ratified decisions (2026-06-01):**
1. `clients` is the canonical top entity; a **brand owner IS a client**, its branding lives inside the client → fold `mc_brand_owners` → `clients` (1:1, same UUIDs; branding re-points; old table → `security_invoker` compat view).
2. Creds grouped by **(org_id, provider, client_id)** — `integration_accounts.client_id` (nullable = org-level).
3. Each account = a **channel object**: cached `channel_info` JSONB (title/avatar/subs/videos/views) + `status` (wiring/validating/validated/error/disconnected) + `last_synced_at`.
4. **Build live account/client data-switching NOW** (not deferred) — re-points dashboards/videos/analytics in the same view.
5. The provider card is a **`@noctusai/lib` organ** (`IntegrationCard`, config-driven per provider) — a MANDATE; WAHA/Meta/etc. reuse it. Click→modal; edit-icon→inline-editable.
6. **Consent routes become keeper-enforced** (`check_consent_routes_mounted`) — every product inherits identical seed consent.

### FE↔BE Contract (authored first; both sides build to it — bare arrays/objects, no envelope, matching existing convention)
- `GET /api/clients` → `Client[]` · `POST /api/clients {slug,name,kind?,notes?}` → `Client` · `PATCH /api/clients/{id} {name?,slug?,kind?,notes?}` → `Client` · `DELETE /api/clients/{id}` → 204.
  - `Client = {id, org_id, slug, name, kind, notes, created_at, updated_at}`.
- `GET /api/integrations/accounts?provider=&client_id=` → `IntegrationAccount[]` (extends existing shape with `client_id, status, channel_info, last_synced_at`).
- `IntegrationAccount = {id, org_id, provider, account_label, client_id|null, status, channel_info, metadata, is_default, last_synced_at|null, created_at, updated_at}`.
  - `channel_info` (youtube) = `{channel_id, title, thumbnail_url, subscriber_count, video_count, view_count}`.
  - `status ∈ {wiring, validating, validated, error, disconnected}`.
- `POST /api/integrations/accounts {provider, account_label, credential, metadata, is_default, client_id?}` → `IntegrationAccount`.
- `PATCH /api/integrations/accounts/{id} {account_label?, metadata?, is_default?, client_id?, status?}` → `IntegrationAccount`.
- `POST /api/integrations/accounts/{id}/sync` → `IntegrationAccount` (live channel-info refresh → status validated/error).
- YT data surfaces accept `?account_id=<uuid>` (omitted → org default): `GET /api/youtube/dashboard…`, `/api/videos…`. Shapes unchanged, account-scoped.

### Phase-2 slices — ALL SHIPPED (prod `06118329`, 2026-06-02)
- [x] **P2-BE** (`17484c93`+`d19b4602`) — migrations 007/008; clients_service+router; account channel-object columns + `update_channel_info`; `account_credentials` switching seam (`account_id`) + `sync_channel_info`; `ChannelInfo.thumbnail_url`; OAuth callback writes channel_info/status; dashboard/videos `account_id`. 638 tests green.
- [x] **P2-FE-lib** (`70efce67`) — `IntegrationCard`+`IntegrationCardModal`+`PROVIDER_CARD_CONFIG` (YT+WAHA) in `@noctusai/lib`; lib export; 70 tests; dual-React harness confirmed resolved.
- [x] **P2-FE-app** (`1e27a6d7`+`f8448461`) — `Conexoes.tsx` cards grouped by client; `ClientManagementModal` (inline, no nav route); `useClients`+`useSyncAccount`; `AccountSwitcher`+`ConnectedAccountSwitcher` mounted on YouTube+Dashboard; YT data hooks default to the active-account store. **Wiring-audit caught built-but-not-wired switcher → fixed.** 46 tests.
- [x] **P2-KEEPER** (`86298341`) — `check_consent_routes_mounted` + `--check-consent-routes` + 11 tests + KB `consent-routes-mandate.md` + CLAUDE.md §1 + memory.
- [x] **P2-DEPLOY** (`06118329`) — migrations applied (PG17 `security_invoker` ✓, RLS-clean) → dev gate (smoke 10/10 + predeploy READY) → bless main → promote prod (backup `ab9f8e5e`) → CI ✓ → deploy social-wiring+core → **edge-verified** (`/api/clients`=401, `/conexoes`=200). Tunnel restart needed post-recreate (logged).
- [x] **P2-SEED-FIXES** (`f8448461`+`241827d6`) — seed vitest localStorage setup (kills per-file polyfills) + local-watch supervised-watcher/no-empty-dist (dev SPA 503 resilience).

## Decision log
- 2026-06-01 — roadmap created; branch isolated; S0 next.
- 2026-06-01 — S0 applied (migration 005 live). S1 shipped: consumption resolver + 4 build-sites.
- 2026-06-01 (user directives) — (a) **Absorb** the N=4 `build_store + YouTubeService` recurrence → one canonical `build_youtube_service_for_org()`. (b) **No legacy backfill** — replace the silent GET-side backfill + resolver lazy-migrate with an EXPLICIT, provider-general `legacy_adoption.adopt_legacy_account()` (YouTube = pilot #1; calendar/gmail/meta inherit the SAME path) + `POST /accounts/{provider}/adopt-legacy`; the unified page triggers it on load. Legacy = canonical first account / reference for the seed of the multi-account framework. Both shipped + green (189 backend tests).

## Open questions
- Per-upload account picker vs. always-default? (Default-account v1; per-upload picker = follow-up unless user asks.)
- `social.noctusai.com` alias — register too? (Canonical = `social-wiring.noctusai.com`; alias optional.)

## Retrospective (Phase 2 close — 2026-06-02)

**Shipped:** the full multi-account/per-client vertical, live on prod. Canonical `clients` entity (brand-owners folded in 1:1, branding re-pointed, `mc_brand_owners` → security_invoker compat view). Per-account channel objects (status + cached `channel_info` + `last_synced_at`). The mandated config-driven `IntegrationCard` `@noctusai/lib` organ (scales to N providers via `PROVIDER_CARD_CONFIG`). Live account/client data-switching wired into YouTube+Dashboard. Consent-routes keeper. Two seed dev-infra root-fixes.

**What worked:** contract-first dispatch (3 file-disjoint Wave-1 slices in parallel, zero merge conflicts on real code); PG-version + live-data de-risk BEFORE writing migrations (0 brand-owners → fold-in was structural, trivial); the dev-validation gate + edge-verify caught real issues pre/at-deploy.

**Friction → fixes (all logged):**
1. **Built-but-not-wired** in dispatched FE (switcher created, mounted nowhere, hook param nobody passed) — caught by an integrate-time wiring-audit, fixed inline. → memory `feedback_dispatch_review_wiring_audit`.
2. **JSONB double-encode parity bug** (service `json.dumps` into JSONB → string on real PG, masked by read-path decode + the SQLite test Fake) — non-breaking, queued as a parity-tested root-fix slice. → ledger.
3. **vitest jsdom lacks localStorage** — root-fixed at the seed factory (shared setup), per-file polyfills removed.
4. **local-watch dev SPA 503** — watcher emptied dist then died unsupervised → root-fixed (supervised + emptyOutDir:false).
5. **`task_branch` integrate false-conflict** (hook stdout + ledger ndjson churn misread as dirty) ×2 — logged.
6. **noc-graph full-rebuild on every graph-touching commit** (no incremental) — 1-2 min/commit drag — logged.
7. **`cloudflared` stale origin after `deploy_image` recreate** — social hostname edge-timeout despite healthy container; `noctus-tunnel` restart fixed it — logged (deploy_image should re-signal the tunnel + edge-check).

**Open follow-ups (deferred):** JSONB double-encode root-fix slice · WAHA full card treatment (multi-account/QR via the organ) · drop `mc_brand_owners_legacy`+`brand_owner_id`+old index once consumers confirmed off them · Insta/Meta provider config blocks · the 7 logged tool/infra improvements (codification pipeline) · initial channel_info auto-populate on connect (folds into the JSONB slice).

## Phase 3 — real YouTube data + first-class "our own YouTube API" + daily time-series snapshots (2026-06-02)

**Why (user, screenshots):** connected channel "João Raphael Souza" shows ZERO data everywhere (Dashboard 0/0/0, YouTube page Vídeos(0)/Shorts(0), Conexões subs/views="—") despite 4 real videos (private/unlisted). User asked to (a) wire real channel+video data into DB + UI; (b) build "our own YouTube API" mapped against the real Data API, documented for easy tool-call (lib funcs AND `noctus.youtube.*` MCP tools — "option 2, both"); (c) daily snapshot of channel + per-video data; (d) separate videos vs shorts tables; (e) copy the YouTube Studio "Conteúdo do canal" layout in-house; (f) a powerful capability-discovery tool.

**Live root-cause (confirmed vs prod Supabase `nyplttplcoyiiqjrvtiw`, not theorized):** `video_cache` 0 rows + `last_synced_at` set ⇒ sync ran, got zero. Cause: seed listed via `search.list?forMine` which does NOT reliably return **private/unlisted** for the owner — and all 4 videos are private/unlisted. Fix = uploads-playlist path (`channels.list?mine&part=contentDetails` → `relatedPlaylists.uploads` → `playlistItems.list` → `videos.list` hydrate), ~3 units, returns private for the OAuth owner. Plus: `channel_info`/`metadata` stored as JSON **strings** in JSONB (`jsonb_typeof='string'`) via `json.dumps()` into supabase-py → SQL-side `->>'channel_id'`=NULL.

**User-ratified decisions:** (1) catalog tables SEPARATE (`youtube_videos`+`youtube_shorts`, real divergence) but snapshot fact-table UNIFIED (`youtube_video_snapshots` + `kind` discriminator); (2) snapshots key on `account_id` (org too coarse, one org → many channels), `org_id` denormalized for RLS, `snapshot_date DATE` in São Paulo, ON CONFLICT idempotent; (3) dual surface = documented seed adapter + `noctus.youtube.*` MCP tools; (4) shorts inferred (no API field) — hashtag→high, ≤60s→high, 61–180s→ambiguous (needs_probe, default not-short), HTTP probe deferred `NOC-REMEDIATE[yt-shorts-probe]`.

### Phase-3 slices — ALL SHIPPED + INTEGRATED (dev/main/prod `3243aab9`, 2026-06-02)
- [x] **P3-SEED** (`7741a627`) — seed `list_owned_videos_via_uploads` (Protocol/Real/Fake) returning private/unlisted via uploads playlist; `classify_short` 3-tier pure helper; `SHORTS_MAX_DURATION_SECONDS=180`; **corrected the false "uploads playlist is public-only" protocol docstring** (canonical "our own API" reference). 101 lib tests.
- [x] **P3-DB** (`44c558dd`) — migration 009: 5 tables (youtube_videos/youtube_shorts catalog, youtube_channel_snapshots, unified youtube_video_snapshots, snapshot_runs guard) + RLS (video_cache shape) + indexes; folded into canonical 001.
- [x] **P3-JSONB** (`f0861ea8`, bg engineer) — dropped `json.dumps` on JSONB writes (dicts to supabase-py) + read-path guard + `sqlite_client._to_db_value` dict/list fallback (dev/prod parity) + migration 010 un-double-encode + real-PG parity test.
- [x] **P3-SVC** (`8587e6a3`) — `SnapshotService.run_for_account` (claim-row guard, channel-stats, classify+route to catalog, unified video snapshots, lazy backfill); `scheduler.py` cron `0 5 * * *` (`youtube_daily_snapshot`, confirmed registered); endpoints `POST /api/youtube/snapshot/run`, `GET /channel/trend`, `GET /videos/{id}/trend`, repointed `/api/videos/sync` + dashboard onto split tables; `kind` filter.
- [x] **P3-MCP** (`24e2d948`) — `noctus.youtube.*` family: channel_stats/list_videos/list_shorts/report(days,top_n)/snapshot_run (sync stub `NOC-REMEDIATE[yt-mcp-sync-auth]`). 25 tests.
- [x] **P3-CAPTOOL** (`a03e5ec2`) — `noctus.seed.search_capabilities(query,mode,surface,layer,kind,namespace)` unified over lib(650)+mcp(218) — the "if not doc'd we won't know its capabilities" ask. 29 tests.
- [x] **P3-FE** (`3243aab9`) — full tabbed YouTube page (Visão geral / Vídeos / Shorts / Upload); in-house Studio "Conteúdo do canal" `ChannelContentTable` (thumbnail+duration | visibilidade | data | views | comments | likes — honest columns, no fake dislikes); `VideoDetailModal` + per-video trend; `VisaoGeralPanel`; trend hooks; real dashboard. Wiring-audit confirmed switcher→store→hooks→URL. 28 tests.
- [x] **P3-FOOTER** (`8d6d7079`) — Core landing `LandingFooter` (Central de Privacidade/Política/Termos → seed `/consent/*`) + minimalist "Entrar" text-link; product-local per directive.
- [x] **P3-ROUTE** (`68970efc`) — unauth `/` → Landing, `/landing` → `/` redirect; seed `unauthRedirect` default → `/`.

### Deploy + live migration (2026-06-02)
- Migrations 009 + 010 applied to live Supabase `nyplttplcoyiiqjrvtiw` (social_wiring): 5 tables present, RLS on, policy counts correct (snapshot_runs=1 service-role, others=2); **security advisors clean for the new tables** (126 pre-existing WARN untouched). Double-encode fixed: `channel_info`/`metadata` `jsonb_typeof='object'`, `->>'channel_id'` = `UCujIprsfXDrygCTxZVQP9Vg`.
- Dev gate: social-wiring **686/686** + core **572/572** green (20 fleet-wide failures are PRE-EXISTING `tests/realdb/` env failures in adconnect/erp/personal-finance — untouched products); smoke 10/10 backends; container restart mounted new routes + registered `youtube_daily_snapshot`; predeploy READY. Service ran end-to-end on dev to the credential-decrypt boundary.
- **dev↔prod Fernet-key parity boundary surfaced:** the dev container CANNOT decrypt the prod-key-encrypted OAuth credential (channel was connected on the live prod site) → `CredentialDecryptError`. The real-4-videos empirical proof therefore runs on **prod post-deploy** (only place the credential decrypts). This validated the entire service wiring up to decrypt; it is NOT a bug.
- bless main → promote prod (`3243aab9`, prod-backup `06118329`) → `deploy_pull` FF VPS (backup `backup/predeploy-20260602-035447` + tar) → CI "Build + push fleet images" → `deploy_image` core+social-wiring (GHCR C2 atomic+rollback).
- **Empirical sync (prod, 2026-06-02 04:42) — SUCCESS.** After the bytea-decode fix (`e74b73a7`) deployed to prod, `SnapshotService.run_for_account` against the live channel `UCujIprsfXDrygCTxZVQP9Vg` returned `videos_upserted=4, shorts_upserted=1, video_snapshots_upserted=5, backfilled=True, needs_probe_count=3`. DB verified: youtube_videos=4, youtube_shorts=1, youtube_video_snapshots=5, youtube_channel_snapshots=1. Real listings ("ONE10010 — Casa…", "ONE9967 — Casa…", real privacy/duration/views). Classifier validated on real data: 122s+#Shorts → short(hashtag/high); 196s → video(>180); 3×106s no-hashtag → video + needs_probe (61–180s band). Channel public stats 0/0/0 is CORRECT (all videos private/unlisted → public videoCount/viewCount=0). Edge-verified: social.noctusai.com / + /youtube + /conexoes = 200, /api/youtube/channel/trend = 401, noctusai.com/consent* = 200.

### P3-CRED-BYTEA (`e74b73a7`) — the deeper root cause
The uploads-playlist fix was necessary but NOT sufficient: `integration_accounts.encrypted_credential` is a `bytea` column (migration 005), and PostgREST returns bytea as a `\x`-hex string. `_decrypt` did `str.encode('utf-8')` on that hex TEXT instead of `bytes.fromhex` → Fernet `InvalidToken` masquerading as "key mismatch" → EVERY sync failed to authenticate (the real zero-data root cause). Confirmed against prod (`\x6741414141…` = valid `gAAAA…` token); SQLite Fake (TEXT/BLOB) hid it — same dev/prod-parity blind spot as the JSONB double-encode. Fix: hex-decode the `\x` prefix on read + 3 real-PG-shape parity tests. Memory `feedback_bytea_credential_hex_read_parity`.

### Decision log (Phase 3)
- 2026-06-02 — unified-snapshot+kind-flag, account_id keying, dual surface, shorts-inference tiers all user-ratified. uploads-playlist confirmed as the private-video fix against live data BEFORE writing code.
- 2026-06-02 — organ-knowledge build-learn layer for the youtube integration deferred: integration not in the canonical-organ manifest (`register_organ` → bundle-not-found). Canonical "documented for easy tool-call" reference is the seed adapter docstrings (done). **Follow-up: register `noctusai_lib.integrations.youtube` as a canonical organ** so its journey is queryable by `find_reusable_component`.

### Open follow-ups (Phase 3)
- Shorts HTTP probe for the 61–180s ambiguous band (`NOC-REMEDIATE[yt-shorts-probe]`).
- MCP `noctus.youtube.sync` auth wiring (`NOC-REMEDIATE[yt-mcp-sync-auth]`).
- Register youtube integration as canonical organ (build-learn cache layer).
- Pre-commit `NOCTUSAI_HOME` export for linked worktrees (worktree cache-path quirk surfaced by P3-FE; worked around with explicit env at commit).
- email_marketing scheduler `Broken pipe`/`ConnectionTerminated` errors observed in social-wiring logs (pre-existing, unrelated to YT) — investigate separately.
