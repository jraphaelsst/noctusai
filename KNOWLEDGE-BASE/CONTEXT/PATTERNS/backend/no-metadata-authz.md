# No metadata authz — `noctus_users` is the only trusted org/role source

> Formalized 2026-10-06 (security hotfix, a real external customer org now
> exists). Self-contained.

## The rule

**`user_metadata` / `raw_user_meta_data` is USER-WRITABLE** (`supabase.auth.updateUser({data})`).
Any `org_id` / `role` / `org_role` read from it is attacker-controlled. The ONLY
trusted source is `public.noctus_users` (`org_id`, `org_role`) — the row RLS's
`current_org_id()` reads. It may never scope a query or gate an action; display
reads (`org_name`) are fine.

## The incident class

- social-wiring `email_marketing` / `media_creation` routers paired `get_org_id(user)`
  (metadata) with the service-role client — any user could name another org and
  read/write its contacts/campaigns/brand kits. The trusted `org_id` was already
  unpacked from `get_current_user_org` and ignored.
- Three hand-rolled `_legacy_jwt_resolver` bridges (social-wiring, agents, academia)
  built `AuthContext.org_id` from metadata, feeding `get_auth_context`,
  `get_current_user_org_unified`, `/api/auth/*` token minting and `require_scopes`.

## By construction (use these, never re-derive)

| Need | Use |
|---|---|
| org in a route | `user, token, org_id = auth` from `make_get_current_user_org` (trusted row; 403/503) |
| org without the tuple | `ProductDependencies.get_org_id(user)` — now a BOUND method that reads the trusted row (403 no row, 503 DB error); prefer the tuple |
| `AuthContext` from a legacy JWT | `make_trusted_legacy_jwt_resolver(get_current_user, get_core_client)` (`noctusai_lib.api.auth.session`) — 403 no row / customer role, 503 DB error, `None` on a bad JWT |
| role / org for a user context | `resolve_org_membership` / `resolve_org_role`; `require_scopes` 403s `org_mismatch` when `ctx.org_id` ≠ trusted org |
| cookie session / API-token mint | `/api/auth/login` writes the TRUSTED org; mint/revoke pin `ctx.org_id` to the trusted org |

`make_get_current_user_org(…, get_org_id_fn, …)` — the positional slot is retired
(pass `lambda u: None`); it is never consulted.

## Gate

Keeper `check_no_metadata_authz` (`--check-no-metadata-authz`, pre-commit 6g2,
blocking): AST scan of `seed/**` + active products' `backend/**` (tests excluded)
for `<…metadata…>.get("org_id"|"role"|"org_role"|"noctus_role"|"erp_role"|"org")`
or `[...]`. Escape: `metadata-authz-ok: <why>` comment, or an entry in
`_NO_METADATA_AUTHZ_ALLOWLIST` (path + function + rationale).

## Known follow-ups (asleep products, not scanned)

adconnect / erp-imobiliario / therapy-platform still read metadata role/org/clinic_id/
distributor_id; fix before waking any of them.
