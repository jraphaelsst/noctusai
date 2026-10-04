# platform-admin-mfa — Project Document

- **Created:** 2026-10-04
- **Last updated:** 2026-10-04
- **Status:** Design locked (architect review 2026-10-04) → Phase 1 ready · 🅿️ two owner decisions open (§7)
- **Owner / stakeholders:** João (owner) · first consumer: Nós no Limiar editorial admin (spec §11 "MFA obrigatório para administradores")
- **Related docs:** `projects/seed-editorial-workflow/PROJECT.md` (sibling, same go-ahead) · `projects/platform-auth-modernization/PROJECT.md` (sessions/tokens — shipped, no MFA) · `KB § PATTERNS/compliance/auth-boundary-false-green.md` · `KB § PATTERNS/backend/seed-fake-real-adapter.md` · `KB § PATTERNS/devops/prod-deploy-safety-gates.md`
- **Project slug:** `platform-admin-mfa` (cross-product: seed auth + core UI ⇒ `projects/`)

---

## 1. Context & Purpose

Admins of any NoctusAI product can change settings, content and people with a single factor (password or
magic link). The first consumer that REQUIRES a second factor is the Nós no Limiar editorial admin (its spec
§11). Goal: a fleet-wide, seed-shaped admin MFA (TOTP via Supabase Auth) that ships OFF, can be enforced per
product, and cannot lock the owner out.

## 2. Confirmed constraints

- Owner go-ahead, 2026-10-04: "go ahead" on "editorial workflow in the seed + admin MFA in core SSO
  (platform-wide)" (Decision Board `nnl-f1-admin-mfa`).
- 🔴 Prod-only fleet (dev fleet dormant): every slice is first exercised in prod ⇒ ships `off` by default, flips
  by a DB row, never by a deploy.
- Never lock the owner out: break-glass is the policy row / Supabase dashboard, never an env var or a code path.
- Auth tests assert strict codes (`== 401`, `== 403` + code) — never `in (...)`.
- A peer session works on `products/social-wiring`: no slice edits it; seed slices run the fleet gate sweep, so
  integrate timing is coordinated with that session.

## 3. Design principles

Seed-first (every product inherits by construction, no per-product MFA code) · default `off` (shipping changes
nothing) · Fake+Real+factory for every IO seam · enforce at the existing admin gate factories so no product can
forget it · instant, out-of-band off-switch.

## 3a. Seed-first analysis

The gate lives INSIDE the four seed admin factories (`require_platform_admin`, `require_org_admin`,
`require_scopes`/`require_org_admin_role`, `make_require_role`); the MFA client, policy and router are seed
modules; core only mounts UI organs. No product-local re-implementation (keeper below).

## 4. Scope

In: aal reading, policy (fleet default + per-product override; `off|warn|enforce`), MFA client, step-up router,
FE organs (enroll panel, challenge dialog, `api.ts` interceptor), core login challenge + Segurança page, recovery
(2 factors, admin reset, break-glass), keeper for hand-rolled admin checks, rollout. Out: SMS/WebAuthn factors;
MFA for non-admin members.

## 4a. Dispatch routing

| Slice | Lens | Files (collision zone) | Parallel with | Prod risk |
|---|---|---|---|---|
| M1 aal reader + `MfaPolicy` + `MfaClient` (Protocol/Fake/Real/factory) + tests | backend-engineer | `seed/lib/backend/noctusai_lib/api/auth/mfa/*` | E1, E2 | none |
| M2 gate inside the 4 admin factories | backend-engineer | `api/auth/platform.py`, `api/auth/session/scopes.py`, `api/auth/__init__.py` | E* | medium (fleet-wide; default off) |
| M3 `mfa` router in `standard_routers` + `public.mfa_policy` migration | backend-engineer | `seed/framework/backend/noctusai_seed/routers*`, new router, core migration | M4 | low |
| M4 FE organs + `api.ts` interceptor | frontend-engineer | `seed/lib/frontend/src/components/mfa/`, `api.ts` | M3 | low |
| M5 core login challenge + Segurança page | frontend+backend | `products/core/*` | E* | **high** (login path) |

## 5. Architecture (architect review 2026-10-04 — findings + design)

**Findings.** No MFA code anywhere (grep `mfa|totp|aal2|2fa`). Core login is server-side
(`products/core/backend/app/routers/auth.py:176-217`, `sign_in_with_password`). Product sessions are minted by
core's SSO bridge (`products/core/backend/app/routers/sso.py:297-370`: `admin.generate_link("magiclink")` +
`verify_otp`, cached 5 min) ⇒ **always aal1** ⇒ a factor checked in core never reaches a product token.
`validate_bearer_token` (`seed/lib/backend/noctusai_lib/api/auth/__init__.py:192`) uses `auth.get_user` (no
claims) ⇒ `aal` is read nowhere. Agents uses cookie sessions (`session/token_exchange.py`) ⇒ step-up must go
through the backend.

**Design.**
1. `noctusai_lib/api/auth/mfa/`: `read_aal(access_token)` decodes claims only after `get_user` accepted the
   token; `AuthContext.aal` filled on cookie / legacy-JWT / Bearer paths; `pk_*` tokens `aal=None`; minting an
   admin-scoped token requires an aal2 caller.
2. `MfaPolicy` Protocol + Fake + Real + `make_mfa_policy` over `public.mfa_policy` (fleet default + per-product
   override; `off|warn|enforce`; default `off`).
3. `require_admin_assurance` composed inside the four admin factories: `enforce` + aal1 ⇒
   `403 {"code":"mfa_required","enrolled":bool}`; `warn` ⇒ passes + response header + audit row.
4. `MfaClient` Protocol + `FakeMfaClient` + `SupabaseMfaClient` (list/enroll/challenge/verify, admin
   `delete_factor`) + factory.
5. `"mfa"` entry in `standard_routers` (`noctusai_seed/app.py:70`): `GET /api/auth/mfa/status`, `POST enroll`,
   `POST verify` (upgrades the session to aal2 — Bearer SPAs get new tokens; cookie sessions get their stored
   tokens rewritten; Supabase keeps aal2 across refresh), `POST admin/reset/{user_id}`.
6. FE organs `seed/lib/frontend/src/components/mfa/`: `MfaEnrollPanel` (QR + confirm), `MfaChallengeDialog`
   raised by the central `api.ts` on `mfa_required` ⇒ step-up in every SPA with no per-product code. Core mounts
   the enroll panel on a Segurança page; core `/login` returns `mfa_required` when the user has factors.
7. Recovery: every admin enrolls TWO TOTP factors; an aal2 platform admin can reset another user's factors
   (audited in `core.audit_logs`); break-glass = flip the policy row by SQL/dashboard or delete the factor in the
   Supabase dashboard; setting `enforce` is refused unless the caller is aal2.
8. Gates: strict tests (`== 401` no token; `== 403`+`mfa_required` aal1 admin under enforce; 200 at aal2; 200
   aal1 member; 200+header under warn) with injected Fakes (no monkeypatch); keeper
   `check_admin_gate_hand_rolled` (flags `role in ("admin"…)` outside the seed factories);
   `verify_db_guards` probe: `mfa_policy` is service-role-write-only.

**Rollout (cannot lock the owner out).** R0 confirm TOTP enabled in the Supabase project; João + a second admin
enroll two devices each · R1 fleet `warn` ~1 week, read the audit rows of admins who would have been blocked ·
R2 `enforce` on pilot `agents` only (manual step-up on a live session + `spa_smoke`) · R3 pilots `core`, `igig`,
then fleet default `enforce`. Each deploy: `predeploy_check` + `deploy_image` (auto-rollback); the policy row is
the off-switch — it takes effect within **≤30 s** (the gate caches the resolved mode per product, per process, for 30 s; the read runs off the event loop).

## 6. Implementation phases

### Phase 0 — Audit ✅
- [x] Re-read the files in §5 at the current tip; confirm Supabase TOTP availability on the project; confirm the four factory call sites.
**Improvements:** (1) The cookie-session `AuthContext` is built by `SessionStore.lookup` from a stored record and never sees a token per request, so `aal` must ride the record: `write_tokens(..., aal=)` is written by the token exchanger from the provider-issued refresh token (M1 did this). (2) Seed ships NO `AuthContext` construction on the legacy-JWT path — the products' `legacy_jwt_resolver`s (and core `trusted_auth.get_trusted_auth`, which builds `AuthContext` from `get_current_user` + `noctus_users`) fill it; M1 ships `validate_bearer_token_with_aal`, M2/M5 must adopt it there (core included). (3) Supabase TOTP availability on the project is NOT verifiable from the repo — stays an R0 manual check (Dashboard → Auth → MFA). (4) The four admin factories were re-read in `platform.py` / `session/scopes.py`; call sites for M2 unchanged.

### Phase 1 — M1 (seed mfa module, default off) ✅
- [x] `read_aal`, `AuthContext.aal`, `MfaPolicy`, `MfaClient` (Protocol/Fake/Real/factory) + tests.
**Improvements:** `read_aal` is shaped against misuse: it requires the `validated_user` from `auth.get_user` and binds on `sub`; `read_aal_issued` is the provider-issued-token variant. `SupabaseMfaClient` is raw GoTrue REST over httpx (no shared supabase-py client to poison, MockTransport seam). `MfaPolicy` table contract is a docstring + `MFA_POLICY_TABLE`; migration is M3. Gap for M2: `warn` mode needs the audit-row writer chosen (core.audit_logs vs `request.state`).

### Phase 2 — M2 + M3 (gate in factories; router + policy migration)
- [ ] Gate composed in the four factories + strict tests; router + `public.mfa_policy` migration + guard probe.
  - [x] **M2** gate composed in the four factories + strict tests + keeper `check_admin_gate_hand_rolled` (branch `feat/admin-mfa-m2`).
  - [ ] **M3** `mfa` router. DONE early (review of M2): `public.mfa_policy` migration `products/core/backend/migrations/060_mfa_policy.sql` (scope PK, mode CHECK, RLS on, anon/authenticated REVOKEd, seed `fleet='off'`; NOT applied — applied at release) + `verify_db_guards` probes `mfa_policy.*` (CHECK refuses unknown mode; authenticated/anon cannot write).
**Improvements (M2):** (1) The gate reads its config from `app.state.mfa_gate` (`MfaGateConfig`: product slug = `create_product_app`'s `app_name`, `MfaPolicy`, `MfaClient`, the app's audit sink) set by `create_product_app` step 8a and read at REQUEST time via the dependency's `Request`; no config ⇒ no-op, so `off` is byte-for-byte the old behaviour (full seed suite + every product suite identical to baseline). Under pytest the config is the Fake policy (all `off`), so no product test reads `public.mfa_policy`; gate tests assign their own `MfaGateConfig` (DI seam, no patching). (2) Every factory dependency gained TRAILING optional `request`/`response` params (positional order of existing direct-call tests preserved); `erp-imobiliario/tests/test_dependencies_factory.py` pinned `require_role`'s exact signature and was updated. (3) `warn` writes one `AuditEntry(method="MFA_WARN", status=0)` through the app's sink when audit is enabled, else a WARNING log (route + actor id) — the audit middleware itself only records mutating requests and carries no "why" field, so a dedicated row was needed; no `audit_logs` schema change. (4) Decisions: pk_ product tokens (`caller_kind="product"`, aal None) are NOT challenged (§5 point 1: capability minted by an aal2 caller; minting-side aal2 requirement is M3/M5 work at the token-mint route). A USER whose `aal` is None (resolver not yet filling it) is treated as aal1 — under `enforce` an unconverted resolver fails closed. `enrolled` comes from `MfaClient.list_factors` of the caller's BEARER token; cookie sessions (tokens held server-side) report `enrolled: null` — the SPA reads `/api/auth/mfa/status` (M3). (5) Admin tier for caller-defined role sets (`require_scopes` user branch, `make_require_role`) = `ADMIN_TIER_ROLES` = {admin, owner, platform_admin}. (6) The sync imperative `require_org_admin_role(core_client, user_id, ctx)` has no request/aal and cannot await the policy: unchanged; the async twin `require_org_admin_role_assured(..., request=, aal=)` is the gated form — call sites must migrate (follow-up). `make_require_org_admin` (legacy tuple) IS gated via the bearer token.
**Follow-ups (M2) — legacy `AuthContext` builders:** switched (mechanical `aal=read_aal(token, validated_user=user)` after the product's own validation): `academia-de-reciclagem`, `agents`. Left: `core` `trusted_auth.get_trusted_auth` (drops the token in `get_session_user`; also the login path ⇒ M5), `erp-imobiliario` (cookie-only, aal already rides the session record), `social-wiring` (peer session — edit later: its `_legacy_jwt_resolver` needs the same one-line `aal=`). `check_admin_gate_hand_rolled` (observe-first, warning, `--check-admin-gate-hand-rolled`, in the aggregate sweep, not a pre-commit block) found **64 hand-rolled admin checks** in: adconnect (7: distributors, financial, products, rewards x2, sellout, orders_service), agents (1: admin_credentials_router), community (2: dependencies), core (10: dependencies x2, admin_cache, admin_llm_usage, credentials, organizations, team, users, permissions, trusted_auth), erp-imobiliario (2: dependencies, negociacoes), therapy-platform (42: dependencies, admin*, appointments, crisis, invitations, lgpd, patients, recurring, refunds, reviews, rooms, scheduling, session_journal, sessions, support, therapy_matching, transactions, whatsapp_therapy, appointment/auth/messaging services). Re-run the keeper for exact lines; each is a migration to a seed factory (or an `# admin-gate-ok:` with reason where it is not an authorization gate).

### Phase 3 — M4 + M5 (FE organs; core login + Segurança page) 🅿️ §7 Q1
- [ ] Organs + interceptor; core login challenge; enroll page.
**Improvements:** NOC-FILL-IMPROVEMENTS

### Phase 4 — Rollout R0–R3
- [ ] R0 enrolment · R1 warn week · R2 agents enforce · R3 fleet.
**Improvements:** NOC-FILL-IMPROVEMENTS

## 7. Open questions (Decision Board)

1. `plat-mfa-stepup` — step-up once per product session (native; **recommended**) vs core-written assurance
   ledger carried to products (fewer prompts, custom trust code).
2. `plat-mfa-who` — platform admins + org owners/admins (**recommended**) vs platform admins only vs + managers.

## 8. Dependencies & blockers

Supabase TOTP enabled on the project (R0). Phase 3+ waits on §7 Q1. Seed slices: coordinate integrate timing with
the social-wiring session (fleet gate sweep).

## 9. Success criteria

Policy `enforce` on a product ⇒ an aal1 admin gets `403 mfa_required`, completes step-up in the SPA, and the
same call succeeds; members unaffected; flipping the row to `off` restores access instantly; no product has
hand-rolled admin checks (keeper green).

## 10. How to use this plan

Phases in order; each slice dispatched via `noctus.dev.task_branch` off `origin/dev` with its own pointer
(project `platform-admin-mfa`). Gates per slice: seed lib pytest, the touched products' suites, MCP tests,
`gate_sweep` before integrate.

## 11. Change log

- 2026-10-04 — Filed from the architect design review (owner go-ahead 2026-10-04). Note: `task_branch start`
  stamped the planning branch with a peer's project via pointer inheritance through `dev`; fixed at the root in
  `branch_pointer._inherit_project` (cbe9b81e3).
- 2026-10-04 — M1 landed on `feat/admin-mfa-m1`: `noctusai_lib/api/auth/mfa/` (aal, policy, client), `AuthContext.aal`, `validate_bearer_token_with_aal`, store/exchanger `aal` plumbing. No gate, no router; runtime unchanged. Phase 0 finding: legacy-JWT + core `trusted_auth` `AuthContext` construction lives in products/core, so M2/M5 must adopt `validate_bearer_token_with_aal` there.
- 2026-10-04 — M2 landed on `feat/admin-mfa-m2`: `mfa/gate.py` (`require_admin_assurance`, `MfaGateConfig`, `build_mfa_gate_config`) composed inside the four seed admin factories; wired by `create_product_app` (default `off`); academia + agents legacy resolvers fill `aal`; keeper `check_admin_gate_hand_rolled` (64 existing hits listed in Phase 2 improvements). Phase 2 stays open for M3.
- 2026-10-04 — M2 review fixes: policy read runs in `asyncio.to_thread` (no event-loop stall), gate cache 5 s → 30 s (off-switch ≤30 s), read-failure log WARNING once per distinct error then DEBUG, `060_mfa_policy.sql` + guard probes (the migration half of M3; not applied).
