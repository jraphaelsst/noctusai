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

## Decision log
- 2026-06-01 — roadmap created; branch isolated; S0 next.

## Open questions
- Per-upload account picker vs. always-default? (Default-account v1; per-upload picker = follow-up unless user asks.)
- `social.noctusai.com` alias — register too? (Canonical = `social-wiring.noctusai.com`; alias optional.)

## Retrospective
_(on close)_
