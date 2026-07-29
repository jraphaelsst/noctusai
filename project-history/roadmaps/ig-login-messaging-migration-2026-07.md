# Roadmap — Instagram-Login messaging migration (social-wiring IG DMs)

> Durable multi-session plan. `projects/` is ephemeral; this survives `/clear`.
> Created 2026-07-21. Owner: social-wiring / seed Meta integration.

## Goal

Read (and later send) **Instagram Direct** messages for agency clients using the
**Instagram API with Instagram Login** model — `graph.instagram.com` + a per-client
**Instagram User access token** + `/me/conversations?platform=instagram` — instead of
the **Facebook-Login / Page-token** model currently in the seed adapter.

## Why (decision record)

The Facebook-Login model (`graph.facebook.com/{PAGE-ID}/conversations` + Page token)
was made to work at the code level this session (correct endpoint, `instagram_basic`
+ `instagram_manage_messages` + `pages_manage_metadata` granted, Page MESSAGING task
present). But it stayed blocked by **Meta-account gates** — Business Verification +
App Review Advanced Access — and it carries heavy **per-client friction**: every
client needs a Facebook Page linked to their IG account + a Page token.

Deep research (2026-07-21, official docs) recommends the **Instagram-Login** model for
agencies reading many clients' inboxes: no Facebook Page per client, one IG user token
per client, only `instagram_business_*` permissions. Meta has steered new messaging
integrations here since 2024-07-23. It does **not** dodge App Review (the Advanced-Access
gate is identical in both models), but it removes the Page-linkage friction per client.

Key facts (see memory `reference_meta_ig_dm_facebook_login_model`):
- Host: `graph.instagram.com` (NOT graph.facebook.com).
- Token: Instagram **User** access token (per client, via Instagram Business Login).
- Endpoint: `GET /me/conversations?platform=instagram` (+ `/{conversation-id}` for messages).
- Permissions: `instagram_business_basic` + `instagram_business_manage_messages`
  (NOT `instagram_manage_messages` — that's the Facebook-Login name; don't cross them).
- Gate for reading accounts you don't own: **App Review → Advanced Access → Business
  Verification** (unavoidable, both models). Dev Mode reads only role-holders/testers.

## Slices

| Slice | What | State |
|---|---|---|
| **S1** | Seed **read adapter** — `InstagramLoginAdapter` (graph.instagram.com): list conversations / list messages via IG user token. Fake+Real+tests. Pure code, fully unit-testable. | ✅ shipped (2026-07-21) |
| S2 | **Instagram Business Login OAuth** — authorize URL + callback + code→IG-user-token exchange (`api.instagram.com/oauth/access_token` short → `graph.instagram.com/access_token` long-lived), store as `provider="instagram"`. + manual token-paste fallback endpoint. Contract-first parallel dispatch (BE: seed exchange helpers + start/callback/token endpoints + settings + provider-CHECK migration `024`; FE: instagram connect row + token-paste UI). | ✅ shipped (2026-07-21) — 3 routes register, app boots; seed 2228 / product 1063 / meta 186 / FE 291 green. Live OAuth pending user's IG app config + token. |
| S3 | **Router wiring** — DMs router routes an IG-Login-model account to `InstagramLoginAdapter`; keep the Facebook-Login path for existing Page-linked connections. Model resolved from the stored account. | ✅ shipped (2026-07-29, `ceb1a0c0`) — `get_dm_adapter_for_account` dispatches on the stored `provider`; `FacebookLoginDmGateway` / `InstagramLoginDmGateway` behind one `DmGateway` protocol. The 9 pre-existing DM tests were re-pointed at the REAL FB gateway (not overridden away), so behaviour-identity is proven, not asserted. |
| S4 | **Send** path on the IG-Login adapter (`POST /me/messages`) + FE connect flow ("Conectar Instagram (mensagens diretas)"). | 🟡 backend shipped (2026-07-29, `ceb1a0c0`) — `send_instagram_message` on `graph.instagram.com` + Fake parity + `graph_post` gained the `base` seam. Shipped WITH S3 deliberately: a gateway whose `send` raised NotImplemented is the half-built shape the seed rules forbid. **FE connect-flow row still ⬜ — deliberately deferred with S5, not forgotten.** Audited 2026-07-29: S2's row claims "FE: instagram connect row + token-paste UI" shipped, but the tree says otherwise — `useSubmitInstagramToken` exists in `hooks/useIntegrationAccounts.ts` with **zero consumers**, there is no `useStartInstagramOAuth` hook at all, and `Conexoes.tsx` has only a YouTube connect affordance. So S2's FE leg is dead code, a route-exists-≠-wired instance. Building the affordance is ~1 FE slice (start-OAuth hook + an Instagram section mirroring the YouTube one + token-paste fallback + tests), but it is downstream of the SAME Advanced-Access gate as S5: an operator could connect an account and still read nothing. Sequence it WITH the App-Review submission so the whole chain can be live-verified in one pass, rather than shipping UI that cannot be exercised. |
| S5 | **App Review submission** — Advanced Access on `instagram_business_manage_messages` + Business Verification. USER/ops task, not code. Prereq for reading real client inboxes. | ⬜ user/ops |

## Decision log

- 2026-07-29 — **S3 dispatches on the stored `provider`, read once.** The first
  shape tried `get_meta_adapter_for_account` and caught its `ValueError` to fall
  through to the IG-Login factory. Replaced: exception-as-control-flow costs two
  lookups for every IG account and produces an error naming the last model tried
  rather than the actual provider. One read, one decision point.
- 2026-07-29 — **The gateway lives in the router layer** (`app/routers/_dm_gateway.py`),
  not `app/services/`. The Facebook-Login path needs `resolve_primary_ig_account` /
  `resolve_primary_ig_page_id`, which raise `HTTPException` — HTTP semantics stay on
  the router side of the line. Credential + model resolution proper stays in
  `app/services/meta.get_dm_adapter_for_account`.
- 2026-07-29 — **Product-local at N=1, flagged not pre-generalized.** The gateway maps
  a row in *this* product's `integration_accounts` to a seed adapter; that table is
  product-owned, so the mapping is too. If a second product grows per-client Meta
  messaging, this is the seam that moves to the seed
  (`KB § PATTERNS/common/accept-with-rationale.md`).
- 2026-07-29 — 🔴 **`status_pagina = 'desenvolvimento'` hides a page from EVERYONE,
  including owners.** Found while promoting the Meta pages: the table carries ONE RLS
  SELECT policy (`todos_veem_producao`, `status = 'producao'`) and the FE reads via the
  authenticated product client, so a dev-status row is returned to no one and
  `isPageVisible`'s dev/owner branch is unreachable dead code. Migration 035 promotes
  `meta` + `instagram_insights` to `producao`, which is what the operator wanted anyway.
  ✅ **The gate itself was then FIXED the same day** (`7368e3fe`): the stranded prior art
  on `feat/status-pagina-dev-visibility` (`351ecba6`) + `-fanout` (`aa806fd5`) — unmergeable
  because its migration was numbered `026`, since taken — was renumbered to social-wiring
  **036** and landed with the fan-out it had deferred (orbity 015, personal-finance 012,
  seed 005, template 005) plus the two live products that fan-out had missed (daily-life
  008, therapy 016). `dev_veem_desenvolvimento` is now live in 6 schemas, verified via
  `pg_policies`; erp already had its own equivalent. The role array ↔ `DEV_ROLES` parity
  contract is enforced by the new `check_status_pagina_role_parity` keeper.
  → `KB § PATTERNS/frontend/status-pagina-dev-visibility.md`
- 2026-07-21 — Chose Instagram-Login over Facebook-Login for the agency multi-tenant
  model (per-client friction + Meta's post-2024 direction). FB-Login path left intact
  for any already-connected Page-linked accounts (no forced migration).
- 2026-07-21 — S1 built adapter-first (testable without live Meta), because live
  verification is blocked on the user's Business Verification + App Review.
- 2026-07-21 — S2 verified the OAuth surface against Meta's live docs: authorize
  `www.instagram.com/oauth/authorize` (scopes `instagram_business_basic` +
  `instagram_business_manage_messages`), code→short `POST api.instagram.com/oauth/access_token`,
  short→long `GET graph.instagram.com/access_token?grant_type=ig_exchange_token`.
  Uses the **Instagram App ID/Secret** (distinct from the Facebook app id). Built as a
  contract-first parallel dispatch (BE + FE, file-disjoint) against the Fake adapter;
  user inserts a real token/logs in once App-side config is ready. Manual token-paste
  kept as fallback. Correction surfaced to user: the "Token de Cliente" (Client Token)
  is NOT the user access token and cannot read DMs.

## Retrospective (fill on completion)

- 🔴 **Instagram App ID ≠ Facebook App ID, even in ONE unified Meta app** (2026-07-21,
  proven live). A single Meta app exposes TWO distinct App IDs: the Facebook App ID (top
  of the dashboard) and a separate **Instagram App ID** (in Instagram → API setup with
  Instagram login → Business login settings, alongside the Instagram App Secret + the
  OAuth redirect URIs). Instagram Business Login's authorize step
  (`instagram.com/oauth/authorize`) accepts ONLY the Instagram App ID as `client_id`;
  sending the Facebook App ID yields Instagram's *"Esta página não está disponível"*
  (invalid platform app). So the Instagram-Login OAuth MUST resolve its own
  `instagram_app_id`/`instagram_app_secret` (Settings → Aplicativo Instagram /
  `resolve_instagram_app_creds`) — NOT the meta_app_id. A mid-session detour wired it to
  meta creds on a (mistaken) "one app = one cred" premise and it failed live; reverted.
  The redirect URI + App Secret also live in that Business login settings panel.
- OAuth-in-new-tab: `window.open(url, "_blank", "noopener")` returns `null` per spec →
  strands the blank tab AND falls back to redirecting the current page. Open WITHOUT
  noopener (sever `tab.opener` manually) to navigate only the new tab.

## Absorb-on-completion

Lessons → KB + memory `reference_meta_ig_dm_facebook_login_model` (extend with the
IG-Login model mechanics once S2/S3 prove out live).
