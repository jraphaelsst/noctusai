# Platform grants and M2M API tokens

> Origin: Julia-line project (`products/social-wiring/projects/julia-line/CONTRACT.md` D1-D6), slice S1. **Statement.** A control plane (agents) wires itself to a product by MINTING a credential and DELIVERING it over an authenticated one-shot call; nobody pastes a token. The seed ships the token primitives, the sender (`GrantDelivery`) and the receiver router.

## Token primitives (`noctusai_lib.api.auth.session`)

| Piece | Rule |
|---|---|
| `mint_token_secret()` | `noc_` + `token_hex(32)`; display prefix is the first 12 chars. Never mint `pk_`. |
| Acceptance | Resolver, `make_get_auth_context` and `token_shape` accept `noc_` AND legacy `pk_` (`has_api_token_prefix`). Each `pk_` site carries `NOC-REMEDIATE[pk-prefix-cutoff]`; the cutoff ships last, after every live token is reissued. Stripe `pk_` keys are unrelated. |
| Scope allow-list | `TokenScopeAllowList`; products `register(...)` their scopes; `ProductTokenAdmin.mint` and the seed mint route (`create_auth_router(scope_allow_list=)`) refuse others (`UnknownTokenScopeError` / 422). The process-global `TOKEN_SCOPES` is permissive until a product calls `.enforce()` (`NOC-REMEDIATE[scope-allowlist-strict]`). |
| No expiry | `expires_at=None` on `ProductTokenAdmin.mint`; on the seed route `no_expiry=true` (exactly one of `expires_at` / `no_expiry`). Revocation and `last_used_at` still apply. |
| Rotate | `rotate_token(admin, schema, old_id, org_id=...)`: mint a same-shape replacement, return it, revoke the old; a failed revoke revokes the new one and raises. |
| Resolver factory | `make_api_token_resolver(admin_client, schema=)` returns the Real; with neither it returns the Fake outside deploy and RAISES in a deploy context. `create_auth_router` uses it (no silent Fake fallback). |
| MFA seam | `MintPolicy(require_mfa=callable(ctx)->bool)`; default NOT required. The seed mint route enforces it (403 `mfa_required` unless `ctx.aal == "aal2"`). Core wires the callable to a platform setting. |

| Token routes (`create_auth_router`) | `POST/GET /api/settings/api-tokens`, `GET /scopes` (the allow-list, for a mint UI), `POST /{id}/rotate`, `DELETE /{id}`. List carries `expires_at` and (when `service_account_check=` is wired) `service_account_id`. `include_session_routes=False` mounts ONLY these (a product that owns `/api/auth/login|me|logout`); `get_auth_context=` makes the routes use the product's single dependency. |
| Service accounts | `ApiTokenCreateRequest.service_account_id` + `build_api_token_row(service_account_id=)`; only a product whose `api_tokens` has the column wires `service_account_check`, else a mint naming one is 422 `service_accounts_unsupported`. |

## Core wiring (`products/core`, migration 099)

- `service_accounts` ("noc-agent") + nullable `api_tokens.service_account_id`; RLS like `api_tokens` (service role only).
- `app/auth_context.py`: the ONE `get_auth_context` (cookie, `noc_`/legacy `pk_` bearer, trusted JWT); the transcription API and the token routes use it; `ApiTokenAuditMiddleware` writes `api_token_audit`. Token management is platform admins only (`get_token_admin_context`) because core scopes (`reminders:write`) are platform-level.
- **MFA to mint is a platform setting, default OFF**: `platform_settings.exigir_mfa_para_tokens` (`'false'`), toggled by `PUT /api/admin/tokens/settings` (platform admins) and read per request into `MintPolicy`. Off: no MFA. On: an unmet `aal2` is the named refusal 403 `mfa_required` (mint and rotate). Row absent = off; unparseable value = ON (fail closed).
- Allow-list: `app/services/api_tokens.py::CORE_TOKEN_SCOPES` (`transcription:read|write`, `reminders:read|write`). Register a new scope there.
- UI: `/admin/tokens` (`AdminTokens`) = the MFA switch + the shared `ApiTokensPanel` / `createApiTokensHooks` from `@noctusai/lib/components` (masked prefix first 4 + last 4 of the stored 12-char prefix, scopes from the server list, secret shown once).

Still deferred: the `CallerKind` `service` principal in `AuthContext` (the FK is stored; the resolver still reports `product`), and the `pk_` cutoff (`NOC-REMEDIATE[pk-prefix-cutoff]`, last step).

## Grant delivery (`noctusai_lib.api.auth.grants`)

`GrantDelivery` Protocol (`deliver(product_slug, issuer, GrantPayload, delivery_token=)` raises `GrantDeliveryError`; `revoke(...)` is best-effort, returns bool) + `FakeGrantDelivery` (records `calls`) + `HttpGrantDelivery` (URL via `resolve_product_url`, bearer = the delivery token) + `make_grant_delivery(real=True)`; the factory refuses the Fake in a deploy context.

## Receiver (`noctusai_seed.platform_grants_router`)

`create_platform_grants_router(get_auth_context=, on_grant=, on_revoke=, issuer="agents")` mounts `PUT/DELETE /api/platform/grants/{issuer}`.

- The org comes from the delivery token (`ctx.org_id`); the body forbids extra fields, so a body `org_id` is 422.
- No token: strict 401. Wrong scope (`platform:grant-receive`), wrong token issuer, other path issuer, or a user session: 403.
- The sink gets `GrantReceived(org_id, issuer, credential, agent_id, metadata, delivery_token_id)`; the credential is a secret (encrypt at rest, never log).

## Orchestration (control-plane side, per contract D2/D4)

Mint channel token, mint product tools token, mint one-shot delivery token (5 min, scope `GRANT_RECEIVE_SCOPE`), `deliver`, revoke the delivery token. Any failure revokes every token of the attempt. Rotate = deliver the new pair, then revoke the old. Revoke = revoke both, then best-effort `revoke` delivery.

## One token per (agent, product, org) -- a token never reaches another agent (owner 2026-11-05)

A grant row (`agents.agent_product_grants`) is the unit of authority: one `(org_id, agent_key, product)` with its OWN personal channel token (`principal_agent_id` = that org's instance of that agent) and its own product tools token. Several agents, products and orgs = several grants, each token minted separately; an agent's token never opens another agent's routes (e.g. Julia's SW token cannot address Bia, even in the same org), and a tools token / stored secret belongs to one agent (`GrantProduct` allows exactly one agent key; a second agent gets its own scope + secret entry).

Enforced at request time, not only at mint: the channel gate (`_require_channel` -> `assert_channel_grant_live`) looks the token's grant up (`GrantStore.find_by_channel_token`) and refuses (403 `grant_inativo`) unless it is `ativo` and not expired, and (403 `agent_not_allowed`) unless it names this very `(org, agent)`; routes that address an agent/thread/hand-off additionally require `principal_agent_id` to match. A revoked or expired grant therefore stops the agent's turns AND spec edits at once. The grant also names who edits the org's specs (`especificacoes_editor`: `plataforma` = NoctusAI staff from Studio via `PUT /api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/specs`, needs a LIVE grant AND the platform-admin login; `org` is reserved, not built). The product (SW) stays read-only for specs.

**Lifecycle is recorded (EOA, agents migration 083).** Every grant change appends one row to `agents.agent_product_grant_eventos` in the same transaction, written by a trigger on `agent_product_grants` so no writer can skip it: `grant_criado` / `grant_ativado` / `grant_falhou` / `grant_revogado` (actor = `revoked_by`) / `grant_tokens_rotacionados` (status unchanged, a token id swapped); pre-083 grants carry one `estado_importado` row. The table is append-only, service-role only and `tier:platform` (so is `agent_product_grants`); `dados` holds token IDS, never a secret. `get_grant_store` refuses its in-memory Fake in a deploy context (no service-role key there is an error, not an empty ledger).

**A token never crosses products.** Tokens live in each product's own `api_tokens`, so an agents channel token presented to social-wiring is unknown there: strict `401` (unauthenticated for that product), never `403`. `403` is the answer for a KNOWN token outside its grant (`grant_inativo`, `agent_not_allowed`, `issuer_not_allowed`, `scope_missing`).
