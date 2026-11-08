# SSO entry contract — central login at core (slice S3 builds core, slice S4 builds the seed)

> Source: `project-history/plans/sso-session-lifecycle-2026-11.md` sections D, E, F
> (design record on `origin/docs/sso-session-lifecycle-record`). Contract-first per
> `KB § PATTERNS/architect/fe-be-contract-first-dispatch.md`: both slices build to THIS file.
> Path: the design record's F section proposed `products/<core>/CONTRACTS/`, but the `.gitignore`
> PII rule `products/*/contracts/` matches it on a case-insensitive filesystem, so the contract
> lives here instead.
> Status: S3 implements the core side (dormant: nothing points at it until S4 deploys).

## 1. Core FE route `/login`

`CORE_URL/login?produto=<slug>&next=<path>&prompt=none|login`

| Param | Rule |
|---|---|
| `produto` | Catalog slug, **never a URL**. Absent = today's behaviour (login, then core `/`). Unknown or inactive slug = error shown ON CORE, no redirect, no bounce. |
| `next` | Post-entry path **in the product**. Path-only: starts with `/`, not `//`, no `\`, no scheme, no control chars; anything else is dropped (treated as absent). Only meaningful with `produto`. |
| `prompt` | `none` or `login`; anything else = `login`. Only meaningful with `produto`. |

Behaviour (with a valid `produto`):

| Core state | `prompt=none` | `prompt=login` / absent |
|---|---|---|
| Signed in at core | launch (below) | launch (below) |
| No core session | `location.replace(landing_url + '#sso=login_required')` — no UI | show the login form titled "Entrar no <nome>" |

**Launch** = ONE `POST /api/sso/token {product_slug}` (the same call `Dashboard.tsx` uses; same-origin so the P2.2
bind cookie is set), then `location.replace(redirect_url + '&next=' + encodeURIComponent(next))` when `next` is
present, else `location.replace(redirect_url)`. `redirect_url` is server-built and regime-aware
(strict `<base>/sso#token=<t>`, legacy `<base>/sso?token=<t>`); in both, `&next=` extends the token's own
parameter list, which is exactly what the seed `SSOCallback.readNextFromLocation` reads (`#next=` / `?next=`).

After password login, the MFA challenge, signup auto-login and an OAuth round trip, core **continues to the
product (launch)** instead of `/`. OAuth: `produto`/`next`/`prompt` are stashed in `sessionStorage` key
`noctus:sso-entry` (JSON `{produto, next, prompt, at}`, 10 min TTL) before leaving for the provider and consumed on
return (`oauth.py` fixes `redirect_to=/login`).

The P2.5 rule is unchanged: signing in as a different user ends the live core session first (strict global logout).

Core-side refusals (`403` no licence, `409` cross-site / no URL, `404` unknown product) render on **core** and never
bounce back to the product.

Password recovery: `CORE_URL/esqueci-senha?produto=&next=` -> email -> `CORE_URL/redefinir-senha?produto=&next=`
(GoTrue recovery hash) -> after the reset, sign in with the new password and launch (an MFA-enrolled user is sent to
`/login?produto=&next=` for the challenge: a recovery link never skips the second factor).
`CORE_URL/redefinir-senha` must be in Supabase Auth **Redirect URLs** (owner/devops config, not verifiable in code).

## 2. `GET /api/sso/produto/{slug}`

- Tier `public`, category `auth` (`@access_tier`). No auth header. Rate limited per visitor IP (`60/minute`).
- Reads ONLY catalog rows with `ativo = true`.

`200` — bare object, strict (no extra keys):

```json
{ "slug": "agents", "nome": "Agentes", "icone": "bot", "landing_url": "https://agents.example.com" }
```

| Field | Type | Notes |
|---|---|---|
| `slug` | string | the catalog slug |
| `nome` | string | display name |
| `icone` | string \| null | catalog icon key |
| `landing_url` | string | product base URL (no trailing slash), resolved server-side by `resolve_launch_base` and checked with `assert_launch_same_site`. This is the `prompt=none` bounce target: `landing_url + '#sso=login_required'`. |

Errors (house envelope `{"error": {"message": <pt-BR string>}}`, same as every core route):

| Status | Cause | Core FE |
|---|---|---|
| 404 | unknown slug OR inactive (indistinguishable on purpose) | error page on core, no redirect |
| 409 | no resolvable URL, or URL not same-site with core (the same guard `/api/sso/token` applies) | error on core, no redirect |
| 429 | per-IP rate limit | error with retry hint |

Side effects: none (pure read). Strictness: path param only; no body, no query params.

## 3. Bounce fragment

`landing_url + '#sso=login_required'` — core -> product when `prompt=none` finds no core session. The seed (S4)
reads it, sets marker `signed-out`, shows Landing, no error, and strips the fragment. Core never adds any other
`#sso=` value.

## 4. Marker (seed-owned, S4+; product-origin `localStorage` key `noctus:entry`)

Values: `active | left | signed-out`. Written by `SSOCallback` success -> `active`; `leaveProduct` -> `left`;
Sair/`goToProductLanding` -> `signed-out`; `#sso=login_required` -> `signed-out`. Core neither reads nor writes it;
it is part of this contract so the seed slices share one vocabulary. Decision table: design record section D.

## 5. Reserved: `403 {"code":"sessao_de_produto"}`

Reserved for S7/S8: a **product-minted** session calling a core route that is not declared product-callable. Not
emitted by S3. The FE must treat it as "this session belongs to a product; sign in at core" (never as a generic
error) once it ships. Registry columns: owned by S2 (`migrations/1xx_sso_product_sessions.sql`), out of S3 scope.

## 6. Deprecations / non-goals

- `GET /api/sso/launch/{slug}` stays untouched here (retired in S9). `routers/sso.py` is not edited by S3.
- Seed `/login` and `/forgot-password` redirect to core in S4; the per-product forms are removed in S6.
