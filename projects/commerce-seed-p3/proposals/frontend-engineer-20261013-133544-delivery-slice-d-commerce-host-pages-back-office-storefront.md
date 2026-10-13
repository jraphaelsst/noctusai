## Delivery — P3 slice D (feat/commerce-p3-pages, rebased on origin/dev bb2666451)

Commits:
- 7ebe8e0f0 feat(commerce): host pages — back office /admin/* + host-resolved storefront (P3 slice D) — includes `commerce` added to the product-frontend-tests CI matrix (check_ci_test_matrix_coverage) and the CONTRACT-DELTAS hold note marked resolved by D31
- 66b9d03e2 feat(commerce): admin-menu status_pagina rows (migration 013, 'desenvolvimento') + retire the scaffold example router/service/schema/tests (003_examples.sql + table kept)
- fc891869c fix(commerce): product editor page rendered the offers editor twice (ProductEditor already embeds OffersEditor)

Verification (on the tip): commerce backend pytest 72 passed; frontend vitest 28/28 (run twice); vite build green; tsc 0 errors; keepers canonical-organ-consumption / consent-routes / lying-loading-state clean; outline-corpus test 6/6.

Wiring audit: green in substance. `--scan-wiring commerce` reports 1 false positive: `DELETE /api/commerce/hosts/{hostname}` exists (seed-lib `commerce_staff_router`, default prefix `/api/commerce`, router.py:361); the scanner does not resolve seed-lib organ factory routers. Every page reads organ endpoints and owns its CRUD; the staff privacy-request queue has no endpoint (D4).

Contract deltas: D1–D8 in projects/commerce-seed-p3/CONTRACT-DELTAS.md (D6 now done by migration 013).

codification-events: s1=8 (contract deltas D1–D8) s2=none s3=none s4=none
drift-found: the scaffold signed-webhook skeleton (`app/routers/webhook_router.py`, `/api/webhooks/example`, `example_webhook_secret`) is still mounted in products/commerce — not requested for removal, left as is
scoped-improvement: scan_wiring does not resolve seed-lib organ factory routers and skips generic `api.get<T>(...)` calls (false positive / unchecked calls); the seed's deep-link restore only runs when `/` is an auth route; admin nav needs a migration per page (a vertical-scaffold overlay could seed the rows); my own slips: a stray copy into the primary checkout (refused by primary_write_guard, nothing written) and a duplicate OffersEditor that a timing-lucky test missed (fixed in fc891869c, test now pins exactly one)