## Slice B1 — backend (delivered)

**Branch:** `feat/portal-roi-backend` @ `ea8b3fd420aca194e2a3c4656610768ff714ef83` (based on `origin/dev@44dd8042`). Committed in-worktree, not pushed/merged — tech-lead integrates.

### Files
- `products/social-wiring/backend/migrations/047_portal_roi_view_null_investimento.sql` — new, unapplied
- `products/social-wiring/backend/app/services/portal_roi_service.py` — new
- `products/social-wiring/backend/app/routers/portal_roi_router.py` — new
- `products/social-wiring/backend/app/main.py` — registration only (2-line diff: import + routers-list entry)
- `products/social-wiring/backend/tests/routers/test_portal_roi_router.py` — new, 31 tests
- `products/social-wiring/backend/tests/test_migration_047_portal_roi_view.py` — new, 11 tests

### §2 lying-number fix — migration 047 (unapplied, production has no dev DB)
`cpl`'s numerator was `COALESCE(c.investimento, 0)`, masking the NULL that means "no `lead_campanhas` row exists for this portal" before division ever saw it. Fix: bare `c.investimento` — NULL propagates through SQL division naturally (`NULL / x = NULL`), so unrecorded stays `null` and a genuinely-entered `R$ 0,00` stays a real `0.00` (previously both would have collapsed to the same value under either the old bug or the roadmap doc's literally-sketched `NULLIF(COALESCE(...),0)` fix, which I evaluated and rejected — see the migration header for the full trace).

`roi` — confirmed already correct (its `COALESCE(...,0)`/`NULLIF(...,0)` pair sits on the *denominator*, where "unrecorded" and "genuinely zero spend" are both legitimately undefined-ROI cases; untouched).

**`taxa_conversao` verdict:** formula is UNCHANGED, and this was a deliberate call, not an oversight. `lead_vendas` has no coverage marker analogous to `lead_campanhas.periodo_inicio/periodo_fim` — a row's mere existence there proves "the operator entered something for this portal in some period," so zero rows unambiguously means "never entered." `lead_vendas` has nothing equivalent: nobody logs a periodic "no sale occurred" row, so zero `lead_vendas` rows cannot distinguish "genuinely closed nothing" from "sales tracking not in use for this portal" — not now, and not with any realistic future write surface, because sales are recorded as they happen rather than declared periodically. Mirroring the `cpl` fix onto `taxa_conversao` was considered and rejected: it would not resolve that ambiguity, it would just force every portal with zero recorded sales to read "não informado" — including one that's been diligently tracked for months and genuinely converts nothing, a real fact worth showing. Since `total_vendas` itself is already decided (`043`'s header) to stay `COALESCE(...,0)` — "counts of things, zero really is zero" — `taxa_conversao` inherits that. Doubly moot for this launch: B1 ships no `/vendas` write surface at all, so `lead_vendas` holds zero rows platform-wide regardless of this formula until that surface exists.

### Service/router (§3.1-3.4)
All five routes. `org_id` from auth context only. GENERATED-column rejection (`cpc`/`cpl`/`custo_visita` → 422) is implicit via `StrictHttpModel`'s `extra="forbid"` — those fields are simply never declared on the write schemas. Business-rule 422s (`periodo_fim < periodo_inicio`, `investimento < 0`) and the 409-with-conflicting-id all ride `AppException` subclasses (`NotFoundError`/`ConflictError`/a new `PortalRoiValidationError`), which `create_product_app` already wires an exception handler for — no router-level try/except needed.

**Non-obvious build note:** `MockSupabaseClient.schema(name)` returns a brand-new wrapper with an empty per-table row cache on every call — a service that re-resolves `.schema()` per table access (the `imoveis_service.py`/`marcas_service.py` shape) silently loses every prior insert the instant two calls re-bind the schema. This slice's 409 duplicate-check and create-then-list flows need write-then-read to actually persist, so `portal_roi_service.py` ships its own schema-scoped, admin-client-object-cached DI seam (`get_portal_roi_client`) — this is the SAME fix already living in `app/modules/leads/deps.py::get_leads_client`. N=2 now; see `scoped-improvement` below.

### Assumptions (not specified in §3, made explicit)
- DELETE `/campanhas/{id}` returns `200 {"deleted": true, "id": "<uuid>"}`, not `204` — kept a body since every other route in this contract returns one and the FE may want confirmation.
- PATCH/DELETE on a nonexistent `campanha_id` → `404` (not explicitly listed in §3.3's error table, which only covers `origem_id` not found).
- Period filtering on `/resumo` and `/campanhas` uses "fully contained" semantics (`lead_campanhas.periodo_inicio >= filter.inicio AND periodo_fim <= filter.fim`), not overlap — simplest, avoids partial-period attribution ambiguity. `leads`/`lead_vendas` are filtered by their own date column (`data_entrada`/`data_venda`) within the same window.
- `/resumo`'s `periodo` in the response is `null` only when BOTH query params are absent; either one given renders `{"inicio": ..., "fim": ...}` with the missing side as `null` (open-ended on that side).

### Tests
42 new (11 migration structure + 31 router: auth-boundary strict-401 incl. route enumeration, CRUD round-trips, 404/409/422 paths, the 409-carries-id assertion, GENERATED-column-name rejection ×3, and the null-vs-zero regression pin + its "recorded zero survives as zero" counterpart + period filtering). Full `social-wiring` suite: **1750 passed / 0 failed / 2 skipped** (skips pre-existing, unrelated — `pglast` not installed + one other). Baseline before this slice: 1708 passed (1750 − 42 new).

### Coordination
No file overlap with F1 (frontend, separate worktree per `PROJECT.md` §4). Only shared surface is the JSON contract in §3 — built to it exactly, no redesign. Branch pointer filed + updated (`project-history/branch-tree.ndjson`) — filed retroactively at delivery rather than pre-edit (see `scoped-improvement`).

### drift-found
`portal-roi-PROJECT.md` has no §4a (dispatch routing / slice→lens table / codification expectations / routes-not-taken) — per `engineer-seed.md` §1b this is the tech-lead's responsibility to populate; executed the slice on the brief alone.

### scoped-improvement
1. I missed the §1d branch-pointer "append BEFORE self-branching" step — the worktree/branch already existed when I started (pre-created by the dispatching session), and I only filed the pointer retroactively at delivery. Worth a brief-template note: when a worktree is pre-created for the engineer (not self-branched by the engineer), the pointer-append step still needs an explicit trigger, since "right before self-branching" doesn't fire.
2. `get_portal_roi_client`'s schema-scoped-cache DI seam is now duplicated verbatim (module-level `WeakKeyDictionary` + same docstring trace) in `app/modules/leads/deps.py::get_leads_client` and `app/services/portal_roi_service.py::get_portal_roi_client`. N=2 — candidate for promotion to a single `app/dependencies.py` helper (e.g. `get_scoped_admin_client()`, schema-parameterized) rather than a third copy landing the next time a product module needs write-then-read consistency against `MockSupabaseClient`.

### codification-events
s1=2 (the two scoped-improvement items above, logged via this note) · s2=none · s3=none · s4=none
