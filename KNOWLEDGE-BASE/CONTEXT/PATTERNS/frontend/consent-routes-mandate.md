# Consent Routes Mandate

> Seed-first. Every product exposes `/consent`, `/consent/privacy-policy`, and
> `/consent/terms-of-use` by construction via `createProductApp`. These are the
> canonical URLs for Google OAuth verification + Meta App Review (LGPD/ABNT).
> Enforced by the `check_consent_routes_mounted` keeper (severity `high`).

---

## The mandate

The seed mounts three public, unauthenticated routes in every product:

| Path | Component |
|------|-----------|
| `/consent` | `ConsentHubPage` |
| `/consent/privacy-policy` | `PrivacyPolicyPage` |
| `/consent/terms-of-use` | `TermsOfUsePage` |

These routes are mounted in `seed/framework/frontend/src/app.tsx` inside
`createProductApp`'s `AppRoutes` — outside the authenticated gate — so they
render without login. They are also re-exported from
`seed/framework/frontend/src/index.ts` so products and tests can consume the
components and content directly.

## Why it cannot regress

- **Google OAuth verification** requires a publicly accessible privacy-policy
  URL. Google validates this URL when configuring an OAuth consent screen; a
  missing or 404 page blocks the OAuth app approval.
- **Meta App Review** requires publicly accessible privacy-policy and
  terms-of-use URLs before approving a Meta (Facebook/Instagram) app for
  production permissions.
- **LGPD/ABNT** (Brazilian data-protection law) requires every SaaS product
  to display a privacy policy to users.

Because the mount lives in the seed, a regression here removes all three URLs
from every product simultaneously — not just one.

## Invariants enforced by `check_consent_routes_mounted`

1. `seed/framework/frontend/src/app.tsx` contains all three route mounts
   (`path="/consent"`, `path="/consent/privacy-policy"`,
   `path="/consent/terms-of-use"`) AND imports the three page components
   (`ConsentHubPage`, `PrivacyPolicyPage`, `TermsOfUsePage`).

2. `seed/framework/frontend/src/index.ts` exports the three page components
   + the `consent` content module (so products/tests can consume them from
   `@noctusai/lib`).

3. No file under `products/<slug>/frontend/` **declares** (function/const/class
   definition of) `ConsentHubPage`, `PrivacyPolicyPage`, or `TermsOfUsePage`.
   Products **consuming** these via import is correct; a local re-declaration
   shadows the seed mount and is a drift violation.

## Consuming consent pages in a product

Do NOT re-implement. Import from the lib re-export:

```tsx
// Correct — consume from seed lib
import { ConsentHubPage } from "@noctusai/lib";
```

The seed's `createProductApp` already mounts these routes for you. A product
never needs to route to them explicitly unless it needs a custom override
(which must be declared as a named-seam extension, analogous to the
`// @consumes-organ` pattern).

## Keeper wiring

```
python mcp/noctusai/cli.py --check-consent-routes
```

- Severity: `high` (blocking)
- Registered in `_DETECTOR_TEST_OVERRIDES` → `tests/test_consent_routes_mandate.py`
- Composed into `check_all_products()` after `check_canonical_organ_consumption`
- CI: runs via the MCP Toolkit Tests job (`pytest mcp/noctusai/tests/ -q`)

## Memory reference

`project_consent_legal_pages` — consent-routes project memory entry (delivery
record, 2026-05-24 ship date, routing to seed framework).

`feedback_consent_routes_mandate` — methodology lesson: consent routes are a
seed-first mandate; no product-local re-implementation allowed.
