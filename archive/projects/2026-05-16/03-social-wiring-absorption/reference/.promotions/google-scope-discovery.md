---
slug: google-scope-discovery
origin:
  - products/youtube-crawler/backend/app/services/google_scopes.py
  - products/youtube-crawler/backend/app/routers/google_router.py
  - products/youtube-crawler/backend/tests/services/test_google_scopes.py
intended_noc_destination: noctusai_lib/integrations/google/scopes/
layer_rationale: |
  Six-layer model: integration shared-helper — belongs alongside the
  Google adapter packages already in noc (calendar, drive, maps).
  The scope module is provider-wide (touched by every Google adapter
  on the consent path), so it sits at the top level of
  `noctusai_lib.integrations.google/` rather than inside any single
  adapter package.
seed_first_analysis: |
  Q1 — Cross-product candidate? YES. Any product using Google OAuth
  (Calendar / Drive / Gmail / Sheets / Docs / YouTube) shares the
  same consent flow + the same "operator drift" problem. Solving
  it once means every adopter inherits it.
  Q2 — Variance? Per-product variance lives in the kitchen-sink
  CONTENTS (a therapy product needs Gmail; an ERP product might
  add Sheets). The resolver mechanics + tokeninfo probe + gap
  diagnosis are identical everywhere.
  Q3 — Existing seed coverage? None — Google adapter packages in
  noc each have their own scope literals scattered across config
  files. Centralizing removes that fragmentation.
  Q4 — Fake+Real? N/A (pure-logic + httpx-mocked tokeninfo).
  Q5 — Migration cost? Low. ~200 LoC, no cross-product imports.
  The kitchen-sink constant becomes the per-product extension
  point (each product imports BASE_KITCHEN_SINK and extends).
  Q6 — Premature lift risk? Low. The mechanic (env var "auto" → in-
  code list, tokeninfo for granted-scope ground truth) is stable
  Google OAuth behavior + obvious operator ergonomics.
dependencies_on_other_additions:
  - google-integrations  # the consent flow this resolver feeds into
promoted_on: not-yet
---

## Why this addition exists

User feedback after the calendar OAuth flow shipped: "Today they
are hardcoded on env" — meaning maintaining GOOGLE_OAUTH_SCOPES
manually across workspaces is exactly the kind of toil that should
die.

This branch ports the Meta scope-discovery pattern
(`feat/meta-integrations`) to Google. Google doesn't expose a "list
my app's configured scopes" endpoint, so we can't fully auto-discover
from Google's side — but we can:

1. Move the canonical list into code (`GOOGLE_KITCHEN_SINK_SCOPES`)
   with the `GOOGLE_OAUTH_SCOPES=auto` convention to invoke it.
2. Probe Google's `oauth2/v3/tokeninfo` post-consent to read the
   actually-granted scope list — the ground truth the operator
   needs to confirm "did GCP Console accept all my scopes?".
3. Diff requested vs granted (`diagnose_consent_screen_gaps`) so
   the operator gets a "covered 100% / 60% / 0%" answer with
   exact missing-scopes list.

Surface exposed: `/api/google/scopes` returns all four layers
(configured / kitchen-sink / granted / declined) + coverage %.

## Integration notes for noc-side

When promoting:

1. **Move `google_scopes.py` → `noctusai_lib/integrations/google/scopes.py`**
   (or `noctusai_lib/integrations/google/scopes/__init__.py` if it
   grows). Sibling to `google_calendar/`, `google_maps/`.

2. **`/api/google/scopes` endpoint**: lift into a noc-level
   helper that any product can register, e.g.:
   ```python
   from noctusai_lib.integrations.google.routers import google_scopes_router
   app = create_product_app(..., routers=[..., google_scopes_router])
   ```
   The endpoint reads from the product's CredentialStore + settings,
   so as long as those follow the seed conventions, it works
   per-product without changes.

3. **Kitchen-sink list is per-product extensible**: factor it as a
   base list with a per-product addendum:
   ```python
   # noctusai_lib side
   GOOGLE_KITCHEN_SINK_BASE = [
     "openid",
     "https://www.googleapis.com/auth/userinfo.email",
     "https://www.googleapis.com/auth/userinfo.profile",
   ]

   # per-product
   GOOGLE_KITCHEN_SINK = GOOGLE_KITCHEN_SINK_BASE + [
     "https://www.googleapis.com/auth/calendar",
     "https://www.googleapis.com/auth/drive.readonly",
     ...
   ]
   ```
   This product currently bakes both layers into one list; split at
   promotion.

4. **Calendar router's resolver wiring** (calendar_router.oauth_start
   + callback) is product-specific because the calendar router itself
   is product-specific (no `noctusai_lib` calendar router today). At
   promotion, the calendar router would also lift — at which point
   the wiring goes with it.

5. **Tokeninfo URL**: hardcoded constant in this module
   (`https://www.googleapis.com/oauth2/v3/tokeninfo`). Stable since
   2017. If Google deprecates v3, we'd bump in one place.

## Future work (NOT in this promotion)

- **GCP Console scope-state probe** — there's an internal `discovery`
  endpoint Google uses for its own dashboard that could theoretically
  surface "what's in my Consent Screen config" but it's not public
  API. Cleanest path stays operator-driven: kitchen-sink in code,
  operator adds to Consent Screen.
- **Per-product scope bundles** — at noc level, expose preset bundles
  (`GOOGLE_BUNDLE_PRODUCTIVITY` = Drive+Docs+Sheets;
  `GOOGLE_BUNDLE_COMMUNICATIONS` = Gmail+Calendar) so a product can
  opt into a curated set rather than hand-rolling a kitchen-sink.
- **Token health probe** — tokeninfo also returns `expires_in` +
  `email_verified` etc; future `/api/google/token` endpoint could
  surface refresh-token health without consuming actual API quota.
