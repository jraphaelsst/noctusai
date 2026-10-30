# Org brand identity — CONTRACT (wave 1)

> Owner decisions 2026-10-29. One identity per org, owned by **core**, worn by core and every
> product of the **selected org** (seed org picker). Fallback = the NOC standard
> (`seed/lib/frontend/src/design-system/tokens.css`). Visuals only — colors, fonts, radius,
> logos, favicon, derived dark mode. Layouts never change per org. Brand voice is stored for
> agents and is never sent to the browser.
>
> Out of wave 1 (named destinations): signup form step (designed with the owner later),
> zip/folder intake, SW brand scoping (pending owner decision vs 2026-10-07 org-per-brand),
> agents consuming the voice (`resolve_org_brand_voice`, wave 2).

## 1 · Data — core migration `089_org_brand_identities.sql` (schema `public`)

| column | type | notes |
|---|---|---|
| `id` | uuid pk | |
| `org_id` | uuid null → `organizations(id)` on delete cascade | **NULL = the platform (NOC standard) row** |
| `version` | int not null | per org, starts at 1, monotonic |
| `status` | text check in (`draft`,`active`,`archived`,`failed`) | |
| `tokens` | jsonb not null | `noctus.brand-tokens/v1` (§2), validated server-side |
| `brand_book` | text not null default '' | markdown extracted / edited |
| `voice` | jsonb not null default '{}' | tone, vocabulary, do/don't — **server-only** |
| `assets` | jsonb not null default '{}' | storage object paths: `logo_light`, `logo_dark`, `logo_mark`, `favicon`, `fonts[]` |
| `source` | jsonb not null default '{}' | uploaded file paths + user descriptions + extraction model + usage |
| `validation` | jsonb not null default '{}' | contrast report, filled-from-default keys, warnings |
| `created_by` | uuid | |
| `created_at` / `activated_at` | timestamptz | |

- Partial unique: one `active` per org (`org_id`), and one `active` platform row (`org_id IS NULL`).
- Unique `(org_id, version)` (NULLs handled via `coalesce` index).
- RLS: org members SELECT their org's rows; writes only via backend service role after
  `settings:manage` check. Platform row readable by all authenticated users.
- Seed the platform row: tokens = exact values of `tokens.css` `:root` + `.dark`.
- Private bucket `brand-identities`, object prefix `<org_id>/<identity_id>/…`; served only through
  short-lived signed URLs.

## 2 · Tokens schema `noctus.brand-tokens/v1`

```json
{
  "schema": "noctus.brand-tokens/v1",
  "light": { "<token>": "H S% L%" },
  "dark":  { "<token>": "H S% L%" },
  "radius": "0.5rem",
  "fonts": {
    "heading": {"family": "Cormorant Garamond", "weights": [500, 600], "source": "google|asset|system"},
    "body":    {"family": "Lora", "weights": [400, 500], "source": "google"},
    "ui":      {"family": "Inter", "weights": [400, 500, 600], "source": "google"}
  }
}
```

- `<token>` keys = **exactly** the CSS variables declared in `tokens.css` (background, foreground,
  card*, popover*, primary*, secondary*, muted*, accent*, destructive*, success*, warning*, info*,
  danger*, border, input, ring, sidebar-*, chart-1..8). Derive the key list from `tokens.css`
  at build/test time — never a hand-maintained list (keeper rule: derive, don't sync).
- Values: HSL triplet regex `^\d{1,3}(\.\d+)? \d{1,3}(\.\d+)?% \d{1,3}(\.\d+)?%$`; radius
  `^\d+(\.\d+)?(rem|px)$`; font family `^[A-Za-z0-9 \-]{1,64}$`. Anything else is refused
  (**CSS injection guard** — values are written into `style.setProperty`, never into a stylesheet string).
- Missing keys are filled from the platform row and listed in `validation.filled_from_default`.
- Missing `dark` → derived server-side from `light` (deterministic function, unit-tested).
- Contrast recomputed in code (WCAG): foreground/background pairs < 4.5:1 → warning listed;
  never trust contrast numbers from the LLM.

## 3 · API — core, prefix `/api/brand`

| method | path | auth | body / response |
|---|---|---|---|
| GET | `/current` | any authenticated user; respects `X-Noctus-Acting-Org` (narrow-only) | `{source: "org"\|"platform", identity_id, version, tokens, assets: {logo_light,…: signed_url\|null}, updated_at}` + `ETag`. **No `voice`, no `source`, no `brand_book`.** |
| GET | `/identities` | `settings:manage` in the org | list versions (no voice) |
| GET | `/identities/{id}` | `settings:manage` | full row incl. brand_book + voice + validation |
| POST | `/identities/ingest` | `settings:manage` | multipart: `files[]` (.md, .pdf, .png/.jpg/.webp logos, .woff2 fonts; ≤ 10 files, ≤ 10 MB each, ≤ 25 MB total; magic-byte check; SVG refused), `descriptions` (json map filename→text, optional) → `202 {job_id}` |
| GET | `/jobs/{job_id}` | `settings:manage` | `{status: queued\|running\|done\|failed, identity_id?, error?}` |
| PATCH | `/identities/{id}` | `settings:manage`, draft only | partial `{tokens?, brand_book?, voice?}` → re-validated |
| POST | `/identities/{id}/activate` | `settings:manage` | activates (previous active → archived). Activating an archived version = rollback |
| POST | `/identities/{id}/assets` | `settings:manage`, draft only | multipart single logo/font with `slot` |

Cross-org ids → **404** (never 403). Rate-limited per seed defaults.

## 4 · Ingestion job

1. Store uploads in the bucket; create `draft` row with `source`.
2. Extract with the **seed LLM client** (no direct `anthropic` import in products — roadmap D26),
   model `claude-sonnet-5-5`, PDFs as native document blocks, md as text. Upload content is
   wrapped as fenced DATA; the system prompt states it may contain instructions to ignore.
   Output = structured JSON matching §2 + `brand_book` + `voice` (tool/JSON schema), parsed by Pydantic.
3. Deterministic validation (§2). Failure to parse → `failed` with reason (never silent).
4. Logos/fonts from uploads mapped to `assets` slots (filename/description hints; else left null).
5. Usage recorded to the AI usage ledger. Target ≤ 30 s p95 (signup waits ≤ 30 s, then falls back).

## 5 · Seed organ `BrandProvider` (`@noctusai/lib/design-system`)

- Mount once in the seed app shell (all products + core get it by construction).
- After org is resolved (org picker / home org), `GET {CORE_API_URL}/api/brand/current` through
  the same authenticated channel as `/api/me/access`; query key includes `org_id`.
- Apply: `document.documentElement.style.setProperty('--<token>', value)` for light, and a
  `.dark` set via a generated `<style>` built ONLY from validated triplets (or scoped vars);
  `--radius`; load Google fonts via `<link>` for `source: google`, `FontFace` for signed asset
  URLs; set favicon; expose `useBrand()` → `{logo, source, isLoading}` for Sidebar/Header logos.
- Cache last applied identity per org in `localStorage` (try/catch) and apply it synchronously
  at boot to avoid a flash of the NOC theme; reconcile when the fetch returns.
- On error → keep NOC standard, no crash, no silent swallow (log + `source: "platform"`).
- `organ.yaml` + tests; registered in the organ catalog.

## 6 · Core settings UI — "Identidade visual"

Core org settings page (org owners/admins): current identity preview (palette swatches light/dark,
fonts, logos), upload (files + per-file description), job progress, draft editor (token pickers,
not raw JSON; brand book markdown; voice fields), contrast warnings, activate, version history
with rollback. Complete loading/empty/error states; cache writes per `noc-cache-writes`.

## 7 · Org picker without reload (seed)

Swapping orgs must not hard-reload. Replace the reload with: set pin → clear/partition the
React Query cache so **no entry from org A survives under org B** (query keys carry `org_id`, or
`queryClient.clear()` + refetch) → re-run `/api/me/access` → BrandProvider reapplies. Must keep
the existing guarantees (server narrows only; one visit marker). Tests prove zero cross-org cache.
