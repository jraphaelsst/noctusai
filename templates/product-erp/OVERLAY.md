# templates/product-erp — ERP organ overlay

An overlay ON TOP of `templates/product-seed`. It carries only the ERP organ bindings; everything else
(auth, SSO, finance mount, team, notifications) is the base template, copied first.

`noctus.dev.scaffold_product(..., overlay="erp")` applies it (`overlay.json` is the manifest, this file is not copied):

| What | How |
|---|---|
| `backend/app/erp_organs.py`, `erp_scheduler.py`, `tests/test_erp_wiring.py`, `frontend/src/lib/erpHooks.ts`, `pages/*.tsx` | copied over the base |
| `frontend/src/pages/Dashboard.tsx` | replaces the base placeholder dashboard (`replaces` in the manifest) |
| `backend/app/main.py` | anchored patch: `organs=[mount_finance(...)]` -> `organs=ERP_ORGANS` + scheduler lifespan hooks (a missing anchor FAILS the scaffold) |
| `frontend/src/App.tsx` | anchored patch: lazy page imports, lucide icons, two nav groups, routes |
| `backend/migrations/NNN_<organ>.sql` | rendered from the organ generators (`expected_organ_migration`, the logic behind `render_organ_migration`), numbered after the base chain in `OrganSpec.requires` order |
| `backend/migrations/NNN_status_pagina_erp.sql` | one `status_pagina` row per overlay page (a nav page without a row is hidden from everyone) |

Market ERPs scaffold to `deploy_scope='dev'` only: an agent never takes a new product to prod
(`KB § PATTERNS/devops/prod-exposure-consent.md`).
