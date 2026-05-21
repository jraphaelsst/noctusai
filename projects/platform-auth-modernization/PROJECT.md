# platform-auth-modernization — Project Document

> Living doc. Scope: seed-level auth foundation that supports both human-user (cookie) and product/automation (api_token) trigger shapes via one resolver returning a unified `AuthContext`. Social-wiring is the pilot consumer (canonical reference for future per-product migrations).

- **Created:** 2026-05-20
- **Last updated:** 2026-05-20
- **Status:** ✅ Wave 1-3 shipped + live preflight green (`GET /api/auth/me` with `pk_*` ApiToken returns expected AuthContext). Fan-out + batch endpoints opted-in to unified dep. Deferred items: per-product migration of other 9 products' FEs (out of scope per user) + RedisSessionStore (FakeSessionStore at runtime today; cookie session survives one container life — fine for current scale, becomes a hardening item).
- **Owner / stakeholders:** rapha · seed maintainers
- **Related projects:** `products/social-wiring/projects/youtube-drive-folder-fanout/` (consumer of the new model in this push); `products/social-wiring/projects/social-wiring-vista-seed-lift/` (parallel seed lift, file-disjoint); `products/social-wiring/projects/social-wiring-settings-di-rewrite/`
- **Project slug:** `platform-auth-modernization`
- **Location:** `projects/platform-auth-modernization/` (cross-product / platform-infra)

---

## 1. Context & Purpose

Current platform auth is a Supabase JWT stored in browser `localStorage` by `@supabase/supabase-js`, sent on every API call as `Authorization: Bearer …`. Three problems compound:

1. **localStorage is XSS-exfiltratable** — best practice in 2026 is HttpOnly cookies for browser sessions.
2. **`org_id` lives as a JWT claim** injected by a Supabase JWT hook reading `noctus_users`. Any non-user credential (service tokens, automation tokens) has to fabricate the claim or bypass RLS — diverges from the user path.
3. **There is no first-class "non-user trigger" shape.** Today's UI endpoints assume "logged-in user clicks button." Real-world triggers (chatbot intake, n8n workflows, MCP tools, scheduled jobs, agent live-tests, internal cross-product calls) have no clean door — they impersonate users, or bypass auth via service-role hacks, or call private internals.

This project ships the unified model: **backend issues opaque tokens for every caller (sessions for FE, ApiTokens for products), resolves them to the same `AuthContext` value object, and Supabase JWT becomes a backend-internal detail used only during login validation.**

User explicit scope (2026-05-20): full modernization on **social-wiring backend + frontend**; other products' backends get the new seed dep available but NOT migrated in this push. Social-wiring is the canonical reference for future per-product migration projects.

---

## 2. Confirmed constraints

- **Scope** — full modernization on `social-wiring` only; other products' FEs stay on the legacy JWT path (dual-mode BE supports both for now). *(Bounds blast radius; one pilot consumer proves the model.)*
- **No localStorage JWT in social-wiring FE post-migration.** *(Removes the XSS exfiltration surface; cookies are HttpOnly Secure SameSite=Strict.)*
- **Backend dual-mode** — legacy Supabase JWT path stays operational alongside new opaque tokens. *(Lets non-social-wiring products keep working; lets us roll back social-wiring FE if needed.)*
- **One `AuthContext`** — `(org_id, caller_kind: "user"|"product", user_id: UUID|None, scopes: list[str], raw_token: str)` returned by the new dep regardless of credential shape. *(Handlers stay credential-agnostic.)*
- **ApiToken = opaque random string** (`pk_<hex32>`); never stored plaintext (hashed in DB). *(Server-to-server pattern; revocable per-row.)*
- **Sessions** = Redis-backed (server-side). Session cookie is `nai_session=<opaque>`; resolver looks up Redis. *(Logout = delete the key — token dies on demand, unlike a JWT that's valid until expiry.)*
- **CSRF** — `SameSite=Strict` cookie + double-submit pattern for cross-origin (n/a today; only relevant if we ever serve FE from a different origin). *(Default tight; loosen if needed later.)*
- **Vista seed lift runs in parallel** — file-disjoint from this project; both land before youtube-drive-folder-fanout live-tests. *(Maximizes parallel-engineer throughput.)*
- **Engineer dispatch in waves** — file-disjoint engineers in isolated worktrees per `KB §9a`. *(User explicit; methodology-canonical for this scope.)*

---

## 3. Design principles

1. **One credential resolver.** Sessions and ApiTokens are two issuance flows for the same downstream `AuthContext`. Handlers depend on `Depends(get_auth_context)`, never on credential shape.
2. **Supabase is a login provider, not a credential carrier.** FE never sees a Supabase JWT post-modernization. Backend exchanges credentials with Supabase server-side during login, stores the refresh_token in Redis, swaps in our opaque session cookie.
3. **Org_id comes from the resolver, not the credential.** Stored in the session row / api_token row at issuance time. Eliminates the JWT-hook dependency for non-user paths.
4. **Drop-in compat for backend handlers.** The new dep returns a structurally compatible tuple/object so existing handlers can swap with minimal diff.
5. **Pilot-first, propagate later.** Social-wiring is the canonical reference. Other products migrate in their own follow-up projects after we learn from the pilot.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES. Auth is platform-wide. Every product has the same need: identify caller → resolve org → authorize. Trigger-shape diversity is uniform across products.
2. **Data source product-specific?** NO. The session+api_token tables are platform-level (live in `core` schema or a shared `auth` schema — design decision in §5).
3. **Placement product-specific?** NO — seed-level module in `noctusai_lib.api.auth.session`. Products consume via dep.
4. **Visibility/permission rule same?** YES — the resolver returns the same shape; permission rules are consumer-specific (router-level).
5. **Seam in seed?** Partial. `noctusai_lib.api.auth` exists with `make_get_current_user_org`. This project extends it with `make_get_auth_context` (new dep factory) and the underlying session/api_token modules.
6. **Default-on or opt-in?** OPT-IN today — only social-wiring migrates. Future products opt-in by swapping the dep + applying their migration. Seed-level code defaults the dual-mode resolver so backwards compat is automatic when products consume.

**Litmus:** seed-level work = pure cross-product (correct). Per-product consumer migration code count = bounded (social-wiring only).

---

## 4. Scope

**In scope:**
- New seed module `noctusai_lib.api.auth.session`: `AuthContext` value object, session-cookie issuance + resolution, api_token issuance + resolution, `make_get_auth_context` dep factory.
- New DB tables (live alongside existing auth): `auth.api_tokens` (or `core.api_tokens`), Redis schema for sessions.
- New seed endpoints surfaced via `make_auth_router(...)`: `POST /api/auth/login` (email+password → cookie), `POST /api/auth/logout`, `GET /api/auth/me`.
- Social-wiring BE: swap auth dep on every router from `Depends(get_current_user_org)` to `Depends(get_auth_context)`; the legacy dep stays as a thin shim mapping the new context to the old tuple (drop-in).
- Social-wiring FE: rewrite `@noctusai/seed/infra` auth context as consumed by social-wiring — fetch `/api/auth/me` on boot, login via `/api/auth/login`, logout via `/api/auth/logout`. No more Supabase JS client in the auth path.
- ApiToken management surface: seed `make_api_tokens_router(...)` mounted by social-wiring at `/api/settings/api-tokens` (create/list/revoke).
- Tests at every layer: seed unit tests, social-wiring integration tests, end-to-end happy-path.

**Out of scope (for now — with reason):**
- Other products' FE migrations — filed as N=2+ follow-up projects after social-wiring pilot proves out.
- Removing the legacy JWT path entirely — dual-mode lives until every product migrates.
- SSO/OAuth provider login flows — Supabase's email/password is the v1; OAuth providers (Google/etc.) extend later via the same `POST /api/auth/login` endpoint shape (different body discriminator).
- Multi-org users / org switching — current model is one user → one org (JWT claim); we preserve that semantic. Multi-org becomes its own design.

---

## 5. Architecture / Data Model

### Tables (new)

```sql
-- Lives in social_wiring schema for the pilot (matches product-scoped today);
-- N=2 follow-up lifts to a shared `auth` schema or `core` schema.
CREATE TABLE social_wiring.api_tokens (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    label            TEXT NOT NULL,
    token_hash       TEXT NOT NULL UNIQUE,    -- sha256 hex of the secret
    token_prefix     TEXT NOT NULL,           -- first 8 chars of secret, for display
    scopes           TEXT[] NOT NULL DEFAULT '{}',  -- future-proof; v1 ignores
    created_by       UUID,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at     TIMESTAMPTZ,
    revoked_at       TIMESTAMPTZ
);

CREATE INDEX idx_sw_api_tokens_org ON social_wiring.api_tokens(org_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_sw_api_tokens_hash ON social_wiring.api_tokens(token_hash) WHERE revoked_at IS NULL;
-- RLS: per-org SELECT/INSERT/UPDATE for authenticated users with owner/admin role;
--      service_role full access. Detailed RLS in the migration.
```

### Redis schema (sessions)

```
KEY:    nai:session:<session_id>
VALUE:  JSON { user_id, org_id, supabase_refresh_token, expires_at, last_seen_at, caller_kind: "user" }
TTL:    24h sliding (refresh on access)
```

### `AuthContext`

```python
class AuthContext(NamedTuple):
    org_id: UUID
    caller_kind: Literal["user", "product"]
    user_id: UUID | None          # populated only when caller_kind=="user"
    scopes: list[str]              # ApiToken-scoped permissions; "user" gets ["*"]
    raw_token: str                 # for downstream supabase client wiring (user path)
    api_token_id: UUID | None      # populated only when caller_kind=="product" (for audit)
```

### Resolver dep

```python
make_get_auth_context(
    *,
    session_store: SessionStore,                # Redis-backed
    api_token_resolver: ApiTokenResolver,       # DB-backed
    legacy_jwt_resolver: JWTResolver | None = None,  # dual-mode bridge
) -> AsyncDependency[AuthContext]
```

Resolution priority:
1. `Cookie: nai_session=<id>` → SessionStore lookup → user `AuthContext`.
2. `Authorization: Bearer pk_<...>` → ApiTokenResolver lookup → product `AuthContext`.
3. `Authorization: Bearer <jwt>` AND `legacy_jwt_resolver` configured → existing path → user `AuthContext` (dual-mode bridge).
4. Else → 401.

### Login flow (FE → BE)

```
FE          POST /api/auth/login  { email, password }
BE          → supabase.auth.sign_in_with_password(email, password)
            → on success:
                session_id = secrets.token_urlsafe(32)
                redis.set(f"nai:session:{session_id}", {...}, ex=86400)
            → response:
                Set-Cookie: nai_session=<id>; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=86400
                Body: { user: {...}, org: {...} }   ← non-sensitive subset
```

### Bootstrap (FE)

```
FE  on app load → GET /api/auth/me
BE  → resolver reads cookie → returns AuthContext → handler returns user+org json
FE  → if 401, redirect to login
```

---

## 6. Implementation phases

### Phase 1 — Wave 1 dispatch (seed scaffolds, file-disjoint parallel engineers)
- [ ] **E-AUTH**: scaffold `noctusai_lib.api.auth.session` module (AuthContext + SessionStore Protocol + ApiTokenResolver Protocol + Fake + Real + make_get_auth_context factory). No DB / Redis wire-up yet — Fake-only implementations + tests.
- [ ] **E-MIGRATION**: write the `api_tokens` migration in-place edit of `001_social-wiring.sql` (one-001 rule); apply via Supabase MCP; regression test.

### Phase 2 — Wave 1 architect (salvage + integrate)
- [ ] Salvage each engineer's patch from `/tmp/*.patch`.
- [ ] Apply to main worktree, run full social-wiring + seed test suites.
- [ ] Commit-on-ship per merged engineer branch.

### Phase 3 — Wave 2 dispatch (consumer migration, file-disjoint parallel engineers)
- [ ] **E-SW-AUTH**: social-wiring BE consumes new auth dep. Add `auth_router` (`/api/auth/login` + `/me` + `/logout` + `/api-tokens`). Swap every product router's auth dep. Add legacy_jwt_resolver bridge so existing FE keeps working until Wave 3 ships.
- [ ] (Parallel to Wave 2 of vista-seed-lift, separate project.)

### Phase 4 — Wave 3 (FE migration — sequential, depends on Phase 3)
- [ ] Social-wiring FE rewrites auth context: fetch `/api/auth/me` on boot; login via `/api/auth/login`; logout via `/api/auth/logout`; remove direct `@supabase/supabase-js` usage from the auth path; ensure cookie credentials are sent on every API call.
- [ ] FE build + smoke test in container.

### Phase 5 — Validation + close
- [ ] Live smoke: login via curl + new endpoint; verify cookie issued + `/api/auth/me` resolves.
- [ ] Tests green at every layer.
- [ ] Update `social-wiring/MASTER-PROMPT.md` with the new auth model + the dual-mode note.
- [ ] Findings.md.

---

## 7. Open questions

1. **Where does the `api_tokens` table live — `core` schema, a new `auth` schema, or product-local?** — leaning product-local for v1 (matches the social-wiring-only scope) and lifts to a shared schema in the propagation projects. *Decided at Phase 1 dispatch time.*
2. **Should the session secret be HMAC-signed?** — opaque random + Redis lookup is sufficient; HMAC is only needed if we want stateless verification. We have Redis, so no.
3. **Refresh strategy for the underlying Supabase token?** — backend silently refreshes when expiring; if refresh fails, the session is invalidated and the user is forced to re-login. Plan as Phase 3 sub-task.

---

## 8. Dependencies & blockers

- **Redis must be reachable** by the social-wiring container (already today).
- **Supabase Auth must accept email+password** (already today).
- **Engineer worktree availability** — Wave 1 needs 2 file-disjoint worktrees.

---

## 9. Success criteria

- Social-wiring FE has zero `localStorage.getItem("sb-…-auth-token")` calls after migration.
- An ApiToken issued via `POST /api/settings/api-tokens` can drive `POST /api/videos/upload/drive-folder` end-to-end against real Vista + Drive + YT for `ONE10010`.
- Other products' BEs still work via legacy JWT (dual-mode proof).
- Test suite green at every layer.

---

## 11. Change Log

- **2026-05-20** — Project filed. Designed for two-trigger unified resolver; social-wiring pilot scope confirmed by user; Wave 1 dispatch ready.
- **2026-05-20** — Wave 1 ✅ E-AUTH (seed `noctusai_lib.api.auth.session` w/ AuthContext + Protocols + Fakes + dep factory; 18 tests) + E-MIGRATION (`social_wiring.api_tokens` table + RLS + 5 regression tests). Note: E-AUTH surfaced the `api/auth.py → api/auth/__init__.py` rename necessity (structural collision); engineer made the call, all 34 pre-existing auth tests still green.
- **2026-05-20** — Wave 2 ✅ E-SW-AUTH consumed seed dep + DB-backed SupabaseApiTokenResolver + `/api/auth/{login,me,logout}` + `/api/settings/api-tokens` router + dual-mode wiring in `dependencies.py`. 16 new tests; full suite 481/481.
- **2026-05-20** — Wave 3 ✅ E-SW-FE added `useSessionAuthInit`/`loginWithSession`/`logoutSession` additively to seed FE; LoginForm gained opt-in `useSessionAuth`. Social-wiring switched; other products untouched. 10 new vitest tests; vite build clean.
- **2026-05-20** — Wave 4 PRE-FLIGHT ✅. `get_current_user_org_unified` opt-in dep added to dependencies.py; fan-out + batch endpoints swapped. Inline fix: admin-client fallback for product callers (JWT-shape detection in `_build_upload_service`). Live verification: `GET /api/auth/me` with pre-minted `pk_7ca8bb983…` ApiToken returns `{user:null, org:{id:"6dd73140-..."}, caller_kind:"product", scopes:["*"]}` — the entire chain (token hash → DB lookup → AuthContext → dep → handler) is live. Container REDIS_URL fixed to `redis://noctus-redis:6379/0`. Live YT upload itself blocked on operator action (YOUTUBE_CLIENT_ID/SECRET in `.env` + per-org channel connection — see fanout `findings.md § Platform OAuth setup`).
