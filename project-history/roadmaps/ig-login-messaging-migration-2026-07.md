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
| S3 | **Router wiring** — DMs router routes an IG-Login-model account to `InstagramLoginAdapter`; keep the Facebook-Login path for existing Page-linked connections. Model resolved from the stored account. | ⬜ planned |
| S4 | **Send** path on the IG-Login adapter (`POST /me/messages`) + FE connect flow ("Conectar Instagram (mensagens diretas)"). | ⬜ planned |
| S5 | **App Review submission** — Advanced Access on `instagram_business_manage_messages` + Business Verification. USER/ops task, not code. Prereq for reading real client inboxes. | ⬜ user/ops |

## Decision log

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
