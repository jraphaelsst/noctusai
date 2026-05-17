# OAuth integration patterns — synthesized for noc-side adoption

> **Date:** 2026-05-13
> **Context:** Lessons distilled across the Drive, Calendar, Maps,
> Meta, and Google-scope-discovery sessions in
> `noctusai-youtube-crawler`. Reads as a "what should noc's
> `noctusai_lib.integrations.oauth/` package shape look like when
> we promote?" document.
>
> **Reference scope:** future / lift-into-noc planning. Pairs
> with the per-provider session notes:
> - `SESSION-NOTES_drive-api-2026-05-13.md`
> - `SESSION-NOTES_google-integrations-2026-05-12.md`
> - `SESSION-NOTES_google-scope-discovery-2026-05-13.md`
> - `SESSION-NOTES_meta-integration-2026-05-13.md`

---

## Why this doc exists

Across 4 OAuth integrations (YouTube, Google Calendar+Drive+Maps,
Meta Facebook+Instagram), we converged on the same architectural
shape but rediscovered the same gotchas independently each time.
This is a synthesizing index — when promoting OAuth code to noc,
read this **before** designing the noc-side abstraction.

The takeaways below are de-duplicated and cross-referenced;
provider-specific detail lives in the per-session notes.

## Layer model — what every OAuth integration needs

```
┌────────────────────────────────────────────────────────────────┐
│ Layer 4: Tool surface (chatbot tools, MCP handlers, REST endpoints) │
├────────────────────────────────────────────────────────────────┤
│ Layer 3: Adapter (Protocol + Fake + Real impls + factory)      │
├────────────────────────────────────────────────────────────────┤
│ Layer 2: Auth abstraction                                       │
│         - Token resolution (env-var OR credential store)        │
│         - Refresh / rotation                                    │
│         - auth_mode discriminator                               │
├────────────────────────────────────────────────────────────────┤
│ Layer 1: Scope catalog + introspection                          │
│         - Kitchen-sink list (code, not env)                     │
│         - Resolver: "auto" | explicit                           │
│         - Post-consent ground truth probe                       │
├────────────────────────────────────────────────────────────────┤
│ Layer 0: Credential persistence                                 │
│         - CredentialStore (Fernet at rest, per-org rows)        │
└────────────────────────────────────────────────────────────────┘
```

Each layer should be a separate module so consumers can swap or
extend. Today in `noctusai-youtube-crawler`, layers blur into
`app/services/<provider>/` packages — when promoting to noc,
factor them out.

## Pattern 1 — Scope auto-discovery (`auto` mode)

**Problem:** Per-workspace `.env` files drift as scope lists
evolve. Operators hand-edit, forget to update one workspace,
production diverges from dev.

**Pattern:** Each provider exposes a `resolve_scopes()` helper
that consults the env var:

```python
def resolve_scopes(*, configured: str, **provider_kwargs) -> list[str]:
    raw = (configured or "").strip()
    if raw and raw.lower() != "auto":
        return parse_explicit(raw)
    return discover_or_fallback(**provider_kwargs)
```

When env is `"auto"` or empty:
- **Meta:** call `GET /{app-id}/permissions` with App Access Token
- **Google:** no discovery endpoint; fall back to kitchen-sink
- **Generic shape:** `discover_app_scopes(app_id, app_secret) -> list[str] | None`,
  where `None` signals "no discovery, use kitchen-sink"

**Default value in code:** `<PROVIDER>_OAUTH_SCOPES=auto` in
`.env.example`. The kitchen-sink list lives in code where it's
versioned with the adapter.

**Operator-facing endpoint:** `/api/<provider>/scopes` exposing
four layers: configured / discovered / kitchen-sink-fallback /
granted-after-consent. Lets the operator audit "did the
provider give us everything we asked for?".

**For noc:** Define a `ScopeResolver` Protocol in
`noctusai_lib.integrations.oauth.scopes` with a default
implementation per provider. Document the kitchen-sink vs.
discovery posture per provider in a Situation→Tool table.

## Pattern 2 — Dual auth backends (System User + User OAuth)

**Problem (Meta specifically, but generalizable):** Customer-
facing OAuth flows are designed for end-user apps where each
user consents to their own data. Server-to-server automation
against business assets needs a different auth model.

**Symptoms when you use the wrong one:** Pages are silently
filtered from `/me/accounts` despite all scopes being granted.
Operator thinks "I administer this Page!" but Graph says
otherwise. No error, just empty data.

**Pattern:** Adapter accepts EITHER a long-lived service-style
token (System User Token in Meta, Service Account Key in Google)
OR a stored OAuth credential. Resolution priority is
**service-style first, fallback to user OAuth**.

```python
@property
def auth_mode(self) -> str:
    return "system_user" if self._system_token else "user_oauth"

def _token(self) -> str:
    if self._system_token:
        return self._system_token
    stored = self._credential_store.get(...)
    return stored.tokens["access_token"]
```

**Where each mode applies:**

| Customer profile | Recommended auth |
|---|---|
| Personal account, manages own data directly | UserOAuth |
| Business uses provider's "Workspace" / "Business Suite" / "Portfolio" | **Service-style** (System User Token / Service Account) |
| Server-to-server automation, no human in the loop | **Service-style** |
| White-label SaaS, each tenant connects their own account | UserOAuth per tenant |

**For noc:** every adapter ships both modes by default. Status
endpoint surfaces `auth_mode`. Setup guides explicitly recommend
the service-style path for business customers — making it the
default avoids the silent failure mode of "consent works but
data is empty".

## Pattern 3 — Single-consent multi-scope bundling

**Problem (Google specifically):** Calendar, Drive, Userinfo
scopes each require their own consent step naively. Doing 3
separate consent flows is hostile UX.

**Pattern:** Bundle related scopes into one consent flow. The
adapter for each integration reads from the **same** credential
row (`provider = "google_calendar"`) but with the bundled scopes
covering all consumers.

In code: scope list at consent time is the **union of every
consuming adapter's needs**. Each adapter then reads its own
slice at API call time.

**For noc:** define per-provider scope bundles in
`noctusai_lib.integrations.<provider>.bundles`:

```python
GOOGLE_BUNDLE_PRODUCTIVITY = [...]  # Drive + Docs + Sheets
GOOGLE_BUNDLE_COMMUNICATIONS = [...]  # Gmail + Calendar
META_BUNDLE_READ_ONLY = [...]  # pages_read + ig_basic + insights
META_BUNDLE_FULL_SOCIAL = [...]  # read + publishing
```

Consumers opt into a bundle by name in their product config.

## Pattern 4 — Post-consent introspection

**Problem:** Operator can't tell from logs/UI which scopes a user
actually granted vs. declined. "Pages count: 0" is ambiguous —
is it because the user denied `pages_show_list`, because they
don't manage any Pages, because of a BM-gating issue, or because
the adapter is broken?

**Pattern:** Every provider exposes a "what did the user
actually grant?" endpoint:
- **Meta:** `GET /me/permissions` → `[{permission, status}]`
- **Google:** `GET https://www.googleapis.com/oauth2/v3/tokeninfo?access_token=<token>` → `{scope, expires_in, email, ...}`

Surface this in `/api/<provider>/scopes`:

```json
{
  "configured": [<requested>],
  "granted_to_user": [<actually approved>],
  "declined_by_user": [<requested - granted>],
  "coverage_pct": 75.0
}
```

If `coverage_pct < 100`, the operator immediately knows to nudge
the user back through consent OR add scopes to the consent
screen config (Google) OR check Use Case asset connections
(Meta).

**For noc:** make this a required component of every OAuth
integration's status surface. A debug endpoint that surfaces only
configured-vs-discovered (no user data leak) is a maintainability
must-have.

## Pattern 5 — CredentialStore (Fernet at rest)

Already in `noctusai-youtube-crawler/products/youtube-crawler/backend/app/services/credential_store.py`. Reuse mechanics:
- One row per `(org_id, provider)` tuple
- Token bundle is JSON-serialized + Fernet-encrypted with
  `ENCRYPTION_KEY` from env
- UPSERT semantics on re-consent
- Decrypt-on-read, fail loudly on key mismatch

**For noc:** lift into `noctusai_lib.security.token_store` as the
canonical persistence layer. Any OAuth-using product imports it.
The current `credential_store.py` is a single-product copy; the
N=2 trigger to formalize fires the moment a second product
adopts.

## Gotchas catalog (real bugs we hit + lifted fixes)

### G1 — Bash `source .env` chokes on unquoted spaces
Setup scripts using `source .env` will silently abort when an
env value contains spaces (Google scope lists are the canonical
offender). **Fix:** ship `.env.example` with documentation +
default values quoted. Better: switch to python-dotenv via
subprocess for parsing. See Meta session note §A.2.1.

### G2 — Docker Compose `environment:` block must list every var
`docker compose up -d --force-recreate` does NOT pipe `.env`
wholesale into the container. Each env var the container needs
must appear in the compose service's `environment:` block (with
`${VAR:-default}` interpolation). Adding a new env var is a
**two-file change**: `.env.example` + `docker-compose.yml`.
See Meta session note §A.2.2.

### G3 — `docker compose restart` doesn't reload env
Env vars are loaded at container **creation**, not at start.
`restart` keeps the same env. For env changes, use
`docker compose up -d --force-recreate <service>`.

### G4 — Tunnel-refresh scripts must update OAuth redirect URIs
Every OAuth redirect URI in `.env` that points at the tunnel
needs to be updated when the tunnel URL rotates. Generic seed
script should parameterize: products declare their redirect env
vars, script iterates. See Meta session note §A.2.3.

### G5 — `FRONTEND_BASE_URL` in the seed's tunnel-refresh script
The current logic preserves non-localhost values (treating them
as explicit overrides). This breaks when the previous value was
itself a stale tunnel URL. **Fix:** detect `*.trycloudflare.com`
hosts as ephemeral and override them too. Track which env vars
are tunnel-bound at workspace-init time.

### G6 — Provider-specific App-Domain validation
Meta won't accept `localhost` in the App Domains field
(requires a TLD). Google has different per-scope verification
requirements. **Fix:** setup docs ship a tunnel-first instruction
(use cloudflared from the start, register the tunnel host).
Localhost is a non-starter for any provider whose dashboard
requires a TLD.

## Cross-provider Setup-Guide template

Every provider's `SETUP_<PROVIDER>.md` should follow the same
structure for operator predictability:

1. **Create developer app** in provider dashboard (link to exact URL)
2. **Add products/use cases** to the app (provider-specific catalog)
3. **Register redirect URIs** — explicit string match including
   port + path. List both localhost and tunnel forms.
4. **Copy ID + Secret** into `.env` (named variables)
5. **Add operator as Admin/Tester/Developer** for dev-mode access
6. **For business customers: configure service-style auth** (System
   User Token for Meta, Service Account for Google) — make this
   the **default recommendation**, not the carve-out
7. **Trigger consent flow** at `/api/<provider>/oauth/start`
8. **Verify with `/api/<provider>/status` + `/api/<provider>/scopes`**
   — must show `configured: true, auth_mode: <expected>, coverage_pct: 100`
9. **Smoke-test through chatbot** with a realistic query

Each step has a verifiable terminal state. No "you should now
see...". Either it works or it doesn't.

## Files in `noctusai-youtube-crawler` that exemplify each pattern

| Pattern | Reference file |
|---|---|
| Scope auto-discovery | `app/services/meta/_meta_api.py` (`resolve_oauth_scopes`) + `app/services/google_scopes.py` |
| Dual auth backends | `app/services/meta/oauth_adapter.py` (`_user_token` + `auth_mode`) |
| Single-consent multi-scope | `app/services/calendar/oauth_adapter.py` + `app/services/drive_api/oauth_adapter.py` (same credential row, scope union) |
| Post-consent introspection | `app/routers/meta_router.py` (`/api/meta/scopes`) + `app/routers/google_router.py` (`/api/google/scopes`) |
| CredentialStore | `app/services/credential_store.py` |

## Open questions for noc-side design

- Should `noctusai_lib.integrations.oauth` define a single
  `OAuthProvider` Protocol both Meta and Google implement, with
  provider-specific subclasses for their quirks? Or per-provider
  packages with a shared `oauth.common` module for the
  CredentialStore + resolver primitives?
- How does the Use-Case-style "asset connection" abstraction
  generalize across providers? (Meta has it, Google has GCP
  Console scope config, TikTok will have its own.)
- Should the kitchen-sink scope lists be per-product
  (each product owns its needs) or per-noc-lib-bundle (shared
  catalog with named subsets)?
- What's the right testing posture for OAuth — mocked-only
  (current), recorded-fixtures, or live "dev-only" smoke against
  a sentinel test app?

These should be settled before the cross-product OAuth code
lifts. Until then: each adopter inherits the patterns above
inline + we capture the divergence in per-product manifests.

---

— filed by Claude (Opus 4.7) in `noctusai-youtube-crawler`,
  2026-05-13, as the consolidated noc-side adoption brief.
