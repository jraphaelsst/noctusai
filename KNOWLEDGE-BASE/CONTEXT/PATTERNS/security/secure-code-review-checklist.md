# Secure code review checklist — stack-specific, keeper-mapped

> **What it is.** The one-page checklist the `security` agent (and any reviewer) walks for a diff on this
> stack: FastAPI + Pydantic, Supabase PostgREST/RLS/Storage, React SPA, WAHA/webhooks, LLM calls. Each
> line names the **keeper that already covers it** (a real `check_*` in
> `mcp/noctusai/tools/noctus/dev/compliance.py`) or says **manual** — manual lines are where review time
> goes. Born 2026-11-05 (agent-refinement W1-S2); owned by agent `security`.
>
> **Why.** "Review with the checklist, not memory." A keeper-covered line is already enforced at
> pre-commit — re-reviewing it by hand is waste; a manual line nobody walks is a hole. The mapping makes
> both visible. Method basis: OWASP Secure Code Review Cheat Sheet (review the diff in context, trace data
> from source to sink, verify controls rather than presence of code) and ASVS 5.0 chapter areas.
>
> **How to use it.** (1) Run the keepers first: `mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --validate`
> (or the pre-commit hook on the diff) — a red keeper is a finding already. (2) Walk only the sections the
> diff touches; tick or write a finding with file:line + severity vector
> (`KB § PATTERNS/security/appsec-craft-canon.md` §4). (3) Every **manual** finding proposes a proof test
> and, at N≥2 recurrence, a keeper candidate. Depth for each line: the canon section in brackets.

Legend: **K** = keeper-covered (pre-commit/CI) · **M** = manual · ASVS chapter in parentheses.

---

## 1 · FastAPI routes and dependencies (V4, V8) — canon §7

| # | Check | Covered by |
|---|---|---|
| 1.1 | Every non-public route authenticates via `Depends(get_current_user_org)` (factory `make_get_current_user_org`), not `ProductDependencies.get_org_id` | K `check_auth_dep_anti_pattern` |
| 1.2 | Intentionally public routes are enumerated and justified (webhook, health, public_ask) | M |
| 1.3 | Object id from path/body is re-scoped server-side: the query includes `.eq("org_id", <trusted org>)` (API1 BOLA) | M (the #1 manual line) |
| 1.4 | Org/role never read from `user_metadata` / `raw_user_meta_data` | K `check_no_metadata_authz` |
| 1.5 | Home-role helpers called with `org_id=` (multi-org users) | K `check_org_role_without_org_id` |
| 1.6 | Admin functions compose the seed admin gate (MFA/AAL2 step-up), never `role == "admin"` (API5 BFLA) | K `check_admin_gate_hand_rolled` |
| 1.7 | Admin endpoints using the service role target tables that have a service-role policy | K `check_admin_endpoint_service_role_bypass` |
| 1.8 | Customer-role members cannot reach staff routes | M (`KB § PATTERNS/backend/database-rls.md` § Customer roles) |
| 1.9 | Consent-gated AI routes carry `Depends(consent_required(<key>))` | M (`KB § PATTERNS/security/lgpd.md` §9) |
| 1.10 | Public / expensive routes rate-limited (`@limiter.limit`), no PEP 563 on the same file | K `check_slowapi_with_pep563`, `check_limiter_conftest_import` (test leak); limit presence M |
| 1.11 | Upload routes declare a body ceiling | K `check_upload_route_body_override` |
| 1.12 | Sync DB calls not inside `async def` handlers (event-loop DoS) | K `check_async_handler_sync_db` |

## 2 · Pydantic and data shaping (V2, V14) — canon §9

| # | Check | Covered by |
|---|---|---|
| 2.1 | Request models are `StrictHttpModel` (`extra="forbid"`) — no silent drop, no mass-assignment (API3 write) | M (`KB § PATTERNS/backend/pydantic-strict-http.md`) |
| 2.2 | Response models list fields explicitly; no credential/internal column leaves (API3 read) | M |
| 2.3 | Writes use `model_dump(mode="json")` | K `check_model_dump_json_mode` |
| 2.4 | String fields have `max_length`; numbers `ge`/`le`; enums are `Literal` | M |
| 2.5 | Errors never echo the offending value (PII) — public anonymous routes parse bodies themselves to avoid FastAPI's 422 `input` echo | M (reference `products/agents/backend/app/public_ask/router.py`) |
| 2.6 | No `except: pass`, no silent fallback on a security path | K `check_silent_errors`, `check_no_silent_ok_comment` |

## 3 · Supabase: PostgREST, RLS, SQL, Storage (V8, V13, V14) — canon §8

| # | Check | Covered by |
|---|---|---|
| 3.1 | New org table: RLS enabled + org-scoped policy | K `check_new_org_table_rls` (blocking), `check_table_has_rls` (advisory) |
| 3.2 | Policies do not subquery their own table (42P17) | K `check_rls_policy_self_reference` |
| 3.3 | INSERT/UPDATE policies carry `WITH CHECK` on the tenant column where `USING` alone would let a row move tenancy | M |
| 3.4 | New view: `WITH (security_invoker = true)` or no browser grant | M (keeper candidate) |
| 3.5 | SECURITY DEFINER: `SET search_path` pinned | K `check_function_search_path_pinned` |
| 3.6 | SECURITY DEFINER: `REVOKE EXECUTE ... FROM PUBLIC, anon, authenticated` same migration | K `check_secdef_migration_revokes_execute` |
| 3.7 | No schema-wide table grant naming `anon` | K `check_schema_wide_anon_grant` |
| 3.8 | agents content tables never `TO authenticated`/`anon` | K `check_no_authenticated_grant_on_content_tables` |
| 3.9 | Buckets never public (static + live) | K `check_storage_bucket_public` (no allowlist) + `noctus.dev.check_storage_no_public_buckets` in `predeploy_check` |
| 3.10 | Storage object keys generated server-side and free of personal data (names, CPF) | M |
| 3.11 | Schema exposure changes are deliberate (`noctus.dev.ensure_schema_exposure`) | M |
| 3.12 | `status_pagina` dev-visibility policy roles equal the FE `DEV_ROLES` | K `check_status_pagina_role_parity` |
| 3.13 | Shared org-identity SQL functions equal the canonical rendering | K `check_org_identity_function_parity` |
| 3.14 | Auth session never established on the shared service-role client | K `check_auth_session_mutation_on_shared_client` |
| 3.15 | PostgREST table names schema-relative; selects bounded | K `check_postgrest_schema_qualified_table`, `check_postgrest_unbounded_query` |
| 3.16 | Raw SQL with input uses `format('%I'/'%L')` / parameters, never f-strings; ILIKE input escaped + length-capped | M |
| 3.17 | GUC carve-out guards use the template, not hand-written | K `check_guc_carveout_guard_hand_written` |
| 3.18 | Exposure verdict from EFFECTIVE state: replay the whole migration chain or query live `role_table_grants` / `pg_policies` (never a partial read) | M (appsec canon §8 rules 10-11) |
| 3.19 | No `TO authenticated` policy with an org-membership-only check on a Platform-IP table; grants match the API tier | M + live query (appsec canon §8 rule 11) |
| 3.20 | Exposed schemas (`pgrst.db_schemas`) list only intended schemas; Data API / auto-expose settings reviewed | M (rule 13) |
| 3.21 | SECURITY DEFINER / any function in an exposed schema: EXECUTE granted only to intended roles (RPC door); `pg_graphql` exposure checked | M + K `check_secdef_migration_revokes_execute` (rule 14) |
| 3.22 | Supabase security advisors (`get_advisors`) run and triaged | M (rule 17) |
| 3.23 | Column privileges used only for secret columns that cannot move to a no-grant table | M (rule 15) |


## 4 · Webhooks and inbound integrations (V4, V13) — `KB § PATTERNS/security/webhook-signatures.md`

| # | Check | Covered by |
|---|---|---|
| 4.1 | Receiver uses `webhook_endpoint(...)` with the provider's real scheme (WAHA = `waha`, sha512 in `X-Webhook-Hmac`) | M (pin 1) |
| 4.2 | Secret resolved per request (no import-time capture) | M (pin 2) |
| 4.3 | Unset secret in prod refuses (fail-closed) — `bypass_when_unset=True` only in a dev context | M; live leg `predeploy_check` `audit_webhook_secret_present` |
| 4.4 | Rate limit on the receiver | M (pin 4) |
| 4.5 | Tests pin status codes (200/401) | K `check_test_status_assertion`, `check_auth_boundary_false_green` |
| 4.6 | Idempotency on the provider event/message id (WAHA double delivery) | M (pin 6 proposed) |
| 4.7 | Replay window enforced when the provider sends a timestamp | M |
| 4.8 | Body is treated as a hint where the scheme does not authenticate it (Basic shared secret) | M |
| 4.9 | Conftests never `setdefault` a credential env var | K `check_conftest_env_setdefault` |

## 5 · Outbound calls, SSRF, files (V5, V12) — canon §9

| # | Check | Covered by |
|---|---|---|
| 5.1 | Any server-side fetch whose URL input influences: host allow-list, redirects off, private/metadata IP refusal after DNS resolve | M |
| 5.2 | Third-party calls paced through `noctusai_lib.integrations.rate_limit`; timeouts set | M |
| 5.3 | Redis clients only via the seam (auth, TLS, prefixing) | K `check_redis_client_via_seam` |
| 5.4 | Upload content type verified by magic bytes; size streamed + capped | M |
| 5.5 | `*NotConfigured` exceptions carry the integration marker (an unconfigured integration is loud, typed) | K `check_not_configured_carries_marker` |

## 6 · React SPA (V3, V1) — canon §9

| # | Check | Covered by |
|---|---|---|
| 6.1 | No `dangerouslySetInnerHTML` with user/LLM content (DOMPurify or exemption) | M |
| 6.2 | `href`/`src` from data validated (no `javascript:`); redirects path-only like `SSOCallback.tsx` `readNextFromLocation` | M |
| 6.3 | No secret in a `VITE_` var (everything `VITE_` is public) | M; boot vars presence K `check_dockerfile_vite_supabase_args` |
| 6.4 | Org-admin UX via `useIsOrgAdmin()` / `isOrgAdmin(ctx)`, never hand-copied (UX only — the server still decides) | K `check_hand_copied_org_admin` |
| 6.5 | Consent routes seed-mounted, never shadowed | K `check_consent_routes_mounted` |
| 6.6 | A refusal is never silent (403/412/409 shown to the user) | K `check_silent_refusal` |
| 6.7 | Direct browser reads of Supabase tables rely on RLS that was reviewed (TB3b) | M |

## 7 · WAHA / WhatsApp channel — `KB § PATTERNS/security/ai-agent-threat-model.md` §3.2

| # | Check | Covered by |
|---|---|---|
| 7.1 | One WAHA per number, compose rendered from `deploy/fleet/waha-instances.yml` | K `check_waha_instances_render_sync` |
| 7.2 | WAHA internal-only (no tunnel hostname), API key + dashboard password set, version past known CVEs | M (ops) |
| 7.3 | `envelope.session` equals the connection's session; Status/broadcast/newsletter never routed to an agent | M |
| 7.4 | Staff classified by NUMBER before any AI call; `pushName` never trusted | M |

## 8 · LLM calls (product side) — `KB § PATTERNS/security/ai-agent-security-canon.md`

| # | Check | Covered by |
|---|---|---|
| 8.1 | No direct `anthropic`/`openai` SDK import — via `noctusai_lib.integrations.llm` (budget, ledger, consent) | K `check_no_direct_llm_sdk_import` |
| 8.2 | agents prompt text lives in DB rows, not code | K `check_agent_prompt_text_in_code` |
| 8.3 | AI feature wiring complete (router registered, prompt doc) | K `check_ai_feature_completeness` |
| 8.4 | User/tenant text reaching a prompt is fenced as data; tool args strict; org from token | M (agents-security lens) |
| 8.5 | LLM output rendered as text, never HTML; links allow-listed | M |
| 8.6 | Cost controls fail-closed when their store is down | M (canon §6) |

## 9 · Secrets, config, supply chain (V13, A03) — canon §10

| # | Check | Covered by |
|---|---|---|
| 9.1 | Every compose `${VAR}` in `deploy/fleet/env.fleet.keys`; secret-shaped vars never default empty | K `check_prod_compose_env_manifest_sync` |
| 9.2 | npm `overrides` are ranges; lockfile in sync; Dependabot coverage | K `check_override_is_range`, `check_product_lockfile_dep_sync`, `check_dependabot_product_coverage` |
| 9.3 | Python imports declared | K `check_seed_declared_imports`, `check_product_declared_imports` |
| 9.4 | Weak hashes only with `usedforsecurity=False` | K `check_hashlib_usedforsecurity` |
| 9.5 | No hooks bypass hardcoded in tracked files | K `check_git_hooks_bypass` |
| 9.6 | New/changed GitHub Action pinned to a full SHA | M — flag to the CI-redesign owner, never edit `.github/` here |
| 9.7 | Container hardening block for agents/academia byte-identical to the canonical constants | K `check_prod_compose_hardening_parity` |
| 9.8 | New prod exposure (compose/ingress slug) carries the owner's consent | K `check_prod_exposure_consent` |
| 9.9 | Seed defaults are the canonical answer, not consumer #1's | K `check_seed_canonical_default` (URL shapes); security defaults M |

## 10 · Logging, privacy, tests (V16, V14) — canon §12

| # | Check | Covered by |
|---|---|---|
| 10.1 | No token, secret, signature or raw PII in logs (shape/ids only); 401s log a reason code | M |
| 10.2 | No personal data in ledgers / history | K `check_ledger_pii` |
| 10.3 | `LGPD-WARNINGS.md` never loses an unresolved entry | K `check_lgpd_entry_removal` (+ range leg) |
| 10.4 | New personal-data column/egress ⇒ `noctus.dev.lgpd_flag` filed | M |
| 10.5 | Auth tests assert strict `== 401`/`== 403` | K `check_auth_boundary_false_green`, `check_test_status_assertion` |
| 10.6 | Tests never monkeypatch our own guard | K `check_no_self_monkeypatch` |
| 10.7 | Cross-tenant negative test exists for every new org-scoped route | M |
| 10.8 | Every new keeper ships its regression test | K `check_detector_has_regression_test` |
| 10.9 | Logs/Sentry: no tokens, session ids, connection strings, keys, prompt text or raw PII (removed, masked or hashed); Sentry server-side scrubbing on, SDK `before_send` scrubs prompts | M (OWASP Logging Cheat Sheet; AC-6.9: privileged reads are logged) |

---

## Coverage summary (2026-11-05)

Keeper-covered lines: 46 of 83 (a line whose primary check is manual counts as manual even when a
keeper covers a neighbouring leg). The manual lines that matter most, in order: **1.3** object-level scope on
service-role reads (API1) · **3.3/3.4** `WITH CHECK` and views (TB3b) · **4.3** webhook fail-closed ·
**5.1** SSRF · **2.1/2.2** property-level authz · **8.4/8.6** LLM fencing and fail-closed cost · **10.7**
cross-tenant tests. Keeper candidates at N≥2: 3.4 (view without `security_invoker` granted to a browser
role), 4.3 (`bypass_when_unset=True` outside a dev-gated expression), 6.1 (`dangerouslySetInnerHTML`
outside an allowlist).

## Sources

Accessed 2026-11-05.
- OWASP Secure Code Review Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html — method (audit-verified).
- OWASP ASVS 5.0.0 chapters — https://github.com/OWASP/ASVS/tree/master/5.0/en — chapter tags (fetched).
- OWASP API Security Top 10 2023 — https://api-security.owasp.org/editions/2023/en/0x11-t10/ — API1/3/5 labels (audit-verified).
- Keeper inventory — `mcp/noctusai/tools/noctus/dev/compliance.py` on `origin/dev` 0a6052430 (read 2026-11-05).
- Supabase Securing your API / column-level security / Storage access control; PostgREST schemas + auth; NIST 800-53 AC-3/AC-6; OWASP Logging Cheat Sheet — READ 2026-11-05, contributions listed in `appsec-craft-canon.md` §16 (rows 3.18-3.23, 10.9).

## Composes-with

`KB § PATTERNS/security/appsec-craft-canon.md` (method + severity) · `KB § PATTERNS/security/webhook-signatures.md` ·
`KB § PATTERNS/security/lgpd.md` · `KB § PATTERNS/security/ai-agent-security-canon.md` ·
`KB § PATTERNS/backend/database-rls.md` · agent `security` (owner) · agent `compliance-reviewer` (quality/methodology review — this is the security half).

> Access tiers (routes + tables declare platform/org/service/public; public is a closed allowlist; delta-stream + leak-fingerprint + effective-exposure gates): `KB § PATTERNS/security/access-tiers.md`.
