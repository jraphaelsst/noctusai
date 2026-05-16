# 📩 Session findings — Google OAuth scope auto-discovery

> **Date:** 2026-05-13
> **Source workspace:** `noctusai-youtube-crawler`
> **Source branch:** `feat/google-scope-discovery`
> (parallel to `feat/meta-integrations`)
>
> **Reference scope:** historical / read-before-planning. The
> work was sibling to the Meta auto-discovery branch — same
> "kill manual scope env-var maintenance" goal, applied to
> Google's OAuth.

---

## TL;DR

Ported the Meta scope-discovery pattern to Google with the same
`GOOGLE_OAUTH_SCOPES=auto` convention. Half of what Meta gets
(Google has no public "list my app's configured scopes" endpoint —
the GCP Consent Screen scope list isn't queryable via API), but
still removes the per-workspace env-var maintenance burden + adds
post-consent introspection.

**Two implementation insights worth lifting into noc:**

1. **Google requires scopes to be added to the OAuth Consent
   Screen BEFORE they can be requested at consent.** Requesting an
   unregistered scope produces a non-obvious "unverified app"
   warning per scope. The kitchen-sink approach is less forgiving
   than Meta's (which auto-filters scopes the app doesn't have).
   Document this prominently in the noc setup guide.

2. **Google's `oauth2/v3/tokeninfo` endpoint is the ground truth
   for "what scopes did the user actually grant"** — accept a
   token, get back the granted-scope string. Implement this as a
   sibling to Meta's `/me/permissions` probe to give operators
   four-layer scope visibility on both providers.

When this lifts into noc, the promotion manifest at
`.promotions/google-scope-discovery.md` is the migration map.
Target: `noctusai_lib/integrations/google/scopes/`.

---

## 1 · What landed

### `app/services/google_scopes.py` (new module, ~200 LoC)

| Symbol | Role |
|---|---|
| `GOOGLE_TOKENINFO_URL` | `https://www.googleapis.com/oauth2/v3/tokeninfo` |
| `GOOGLE_KITCHEN_SINK_SCOPES` | Curated list: openid + userinfo.email/profile + calendar + calendar.events + drive.readonly + drive.file + drive.metadata.readonly. Covers Calendar + Drive adapters this product ships today. |
| `resolve_google_scopes(configured)` | "auto" / empty → kitchen-sink; comma OR space-separated explicit list → verbatim. Dedupes preserving first-occurrence order. |
| `format_scopes_for_authorize(scopes)` | Joins with spaces (Google's authorize endpoint format, not commas). |
| `discover_granted_scopes(access_token)` | Probes `tokeninfo` to read the granted-scope string. Returns `[]` on any failure (treat as "unknown"). |
| `diagnose_consent_screen_gaps(requested, granted)` | Set-diff + coverage % — answers "did Google honor everything I asked for?" without manual list comparison. |

### `app/routers/google_router.py` (new, with one endpoint)

`GET /api/google/scopes` returns a 4-layer view:

```json
{
  "configured": [<what oauth_start would request>],
  "kitchen_sink_default": [<hardcoded full list>],
  "granted_to_user": [<from tokeninfo after consent>] | null,
  "declined_by_user": [<configured - granted>] | null,
  "coverage_pct": 100.0 | null,
  "note": "<actionable text>"
}
```

The endpoint deliberately uses the prefix `/api/google/` (not
`/api/calendar/`) because Google scopes cover Calendar + Drive
today and Gmail/Sheets/Docs tomorrow — "Google-wide" not
"Calendar-specific".

### `calendar_router.oauth_start` updated

The consent URL builder now calls `resolve_google_scopes()` and
`format_scopes_for_authorize()` instead of using the raw env value.
Response model gained `scopes` + `scope_source` fields
("configured" | "kitchen-sink"). The callback persists the
resolved scope list on the credential row (not the raw env value
"auto"), so post-consent introspection works correctly.

### Tests

`tests/services/test_google_scopes.py` — 16 tests covering:
- Resolver: auto / empty / comma / space / dedupe (6)
- format_for_authorize (2)
- discover_granted_scopes: success / 401 / network / missing field (4)
- diagnose_consent_screen_gaps: perfect / partial / extra / empty (4)

All 16 pass. Full backend unit suite: 182 passing.

---

## 2 · Meta vs Google — the architectural diff

| | Meta | Google |
|---|---|---|
| Scopes catalogued per app via API? | ✅ Yes — `GET /{app-id}/permissions` with App Access Token | ❌ No — Consent Screen config isn't exposed publicly |
| Auto-allow scopes the app didn't pre-register? | ✅ In dev mode for testers/admins | ❌ No — Google blocks scopes not in Consent Screen |
| Post-consent introspection? | ✅ `GET /me/permissions` (status: granted/declined) | ✅ `oauth2/v3/tokeninfo?access_token=...` returns granted scope string |
| Kitchen-sink approach safety | High (Facebook auto-filters) | Low (operator must add every scope to GCP Console first) |

**Implication for noc:** the "scope auto-discovery" pattern is
provider-shaped, not generic. A `noctusai_lib.integrations.oauth`
abstraction would need a `provider.list_app_scopes()` Protocol
where the Google impl returns `None` (signaling "no discovery
available, use defaults") and the Meta impl returns the actual
list from Graph.

## 3 · Operator playbook (Google scopes only)

The kitchen-sink scopes shipped here are:
- `openid`
- `https://www.googleapis.com/auth/userinfo.email`
- `https://www.googleapis.com/auth/userinfo.profile`
- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/calendar.events`
- `https://www.googleapis.com/auth/drive.readonly`
- `https://www.googleapis.com/auth/drive.file`
- `https://www.googleapis.com/auth/drive.metadata.readonly`

**Mandatory operator step:** ALL of the above must be added in
GCP Console → APIs & Services → OAuth Consent Screen → Scopes
BEFORE the consent flow can request them. Google blocks
unconfigured scopes (unlike Meta which silently filters).

If the operator wants to extend (e.g. add Gmail), they must:
1. Add the new scope in GCP Console Consent Screen
2. Add the scope literal to `GOOGLE_KITCHEN_SINK_SCOPES` in code
3. Re-consent via `/api/calendar/oauth/start`

The `/api/google/scopes` endpoint surfaces what was granted vs.
requested with a `coverage_pct` — if it drops below 100% after a
consent flow, that's the signal a scope is missing from the GCP
Console config.

## 4 · Files + pointers

- Code: `noctusai-youtube-crawler/products/youtube-crawler/backend/app/services/google_scopes.py`
- Router: `app/routers/google_router.py`
- Wired in: `app/routers/calendar_router.py` (oauth_start + callback)
- Config: `app/config.py` (`google_oauth_scopes: str = "auto"`)
- `.env.example`: documented "auto" default + GCP Console reminder
- Tests: `tests/services/test_google_scopes.py` (16 tests)
- Promotion manifest: `.promotions/google-scope-discovery.md`
- Companion docs:
  - `SESSION-NOTES_meta-integration-2026-05-13.md` — the sibling
    Meta auto-discovery work that this mirrors
  - `SESSION-NOTES_google-integrations-2026-05-12.md` — the
    original Calendar + Maps + Drive integration this builds on

## 5 · What's deferred

- **Discovery via GCP Console programmatic API** — there's no
  public endpoint for this. Operator manual setup remains a
  requirement. (If Google ever exposes one, our adapter is shaped
  to call it via a simple `discover_app_scopes()` swap.)
- **Multi-product scope bundles** — a future
  `noctusai_lib.integrations.google.bundles` module could expose
  preset bundles (`PRODUCTIVITY` = Drive+Docs+Sheets;
  `COMMUNICATIONS` = Gmail+Calendar) so each product opts in
  rather than hand-rolling kitchen-sinks.
- **YouTube scopes** — managed by a separate OAuth client
  (`youtube_router`/`settings_router.oauth_router`), intentionally
  NOT lumped into the kitchen-sink. Lift separately when promoting.

---

— filed by Claude (Opus 4.7) working in `noctusai-youtube-crawler`
  on branch `feat/google-scope-discovery`, 2026-05-13, at the
  user's request as historical reference + future noc-side
  promotion plan.
