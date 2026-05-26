---
name: noc-wiring-audit
description: Use to verify a product's UI shows REAL data and manages its own data — triggers "wiring audit", "all-zeros dashboard", "is this page wired", "route exists but no data", "page-scoped CRUD". route-exists ≠ wired; read-only ≠ managed.
version: 1.0.0
---

# noc-wiring-audit — every surface shows real data ∧ manages its own data

Each page/widget/stat/table is wired to a real endpoint that actually RETURNS real data, and the page that lists an entity is where you create/edit/delete it (page-scoped CRUD). Never raw Supabase SQL or a script for routine data.

## Workflow (7-step audit)

1. **Extract FE endpoints** the page calls.
2. **Route exists** for each.
3. **Returns real data at runtime** (route-exists ≠ wired — a route can 500 on a wrong column, fast-fail a `Promise.all`, or stub).
4. **No fast-fail aggregation** — a shared `Promise.all` catch hiding one bad call.
5. **No EN/PT column mismatch** — `name`/`nome` select drift (the all-zeros root, 2026-05-25).
6. **Empty only when truly empty.**
7. **Page-scoped CRUD** — the listing page manages its own related data.

## Mechanism
- `noctus.dev.scan_wiring` — static legs: `check_fe_route_missing` (high) · `check_name_on_nome_select` (high) · `check_promise_all_shared_catch` (warning).
- Live admin-token probe = runtime leg (advisory). Page-scoped-CRUD = judgment leg (advisory).

## Depth
`KB § PATTERNS/product-internal-wiring.md` · siblings `KB § PATTERNS/boundary-contract-tests.md`, `KB § PATTERNS/core-url-routing.md`.
