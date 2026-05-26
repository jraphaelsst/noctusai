# Product-internal-wiring rule

> **One-line rule.** Every product is, **by construction, internally wired** — each
> UI surface shows **real data** via **real endpoints that actually return real
> data**, real internal data flows work end-to-end, **and each page fully manages
> its own related data — the page that lists an entity is where you create / edit /
> delete it (page-scoped CRUD)**. **Route-exists ≠ wired**, and **read-only ≠
> managed.** A page that renders zeros/empty/stub, calls an endpoint that
> 404s/500s/returns a stale shape, **or that lists an entity the user cannot
> create / edit / delete *on that same page***, is an *unwired* surface — a defect,
> not a state. **The platform is the tool for managing data — never raw Supabase
> SQL or a Python script.**

## 1 · Why this rule exists

A product can look "done" — pages render, routes exist, tests pass — yet show the
user **nothing real**. The trigger case (2026-05-25): the core admin Dashboard
displayed `0` for every stat and "Nenhum produto cadastrado" while the DB held 15
orgs / 9 products / 10 licenses. Root cause: `/api/subscriptions` 500'd on a
`plans.name` column that doesn't exist (schema is `nome`), and the page's
`Promise.all` single-`catch` turned that **one** 500 into an **all-zeros**
dashboard. The route existed; the wiring didn't.

**The lesson: "the route exists" is not "the surface shows real data."** Wiring is
only proven by data flowing **end-to-end**, observed at runtime — not by a
route-existence check.

## 2 · The wiring audit checklist (the mechanism)

For each product, for each UI surface (page/widget/tile/table/stat):

1. **Extract** every backend call the surface makes (`api.get/post/patch/delete('<path>')`).
2. **Route exists** — a matching backend route (prefix + path + method) is defined. *(static — catches 404s.)*
3. **Returns real data at runtime** — hit the endpoint against a live instance with a real (admin where needed) token; it returns `200` **and real rows**, NOT `500` / `403`-where-it-should-pass / a stale shape. *(runtime — catches the class route-existence misses: the `name`/`nome` 500, an expired-license 403, a schema drift. This is the step that route-checks skip.)*
4. **No fast-fail aggregation** — a surface that fetches N endpoints must NOT let one failure zero everything; use per-endpoint `.catch()` (degrade independently) — never a single shared `try/catch` around a `Promise.all`.
5. **No EN/PT column mismatch** — PostgREST selects read the **real** column. The platform schema is Portuguese (`nome`/`descricao`/`ativo`); a select of `(plans|products|organizations)(...name...)` is the recurring 500 class — read `nome`. *(static lint.)*
6. **Empty is allowed only when truly empty** — `0`/empty is correct iff the underlying data is genuinely absent (verified), not because the fetch errored. Distinguish "no data yet" (real state) from "fetch failed" (defect).
7. **Page-scoped CRUD** — each page that **lists/owns** an entity also **creates, edits, and deletes** that entity **on that same page** (the subscriptions page is where you manage subscriptions; the products page is where you manage products). A page that only *displays* an entity it owns is an unwired surface. Managing that data must **never** require raw Supabase SQL or a Python script. *(Carve-out: a page showing genuinely read-only/derived data — analytics rollups, audit logs, computed metrics — has no write side by design; that's not a CRUD gap. The test: "does this page list an entity an operator/user would need to manage?" If yes → that page needs Create+Update+Delete.)*

## 2a · Page-scoped CRUD (the management mandate)

The platform is a **tool for managing data**, not only visualizing/analyzing it —
and management is **co-located with the listing**: *each page controls its own
related data.* The page that lists an entity is the page that creates, edits, and
deletes it. You manage subscriptions on the subscriptions page; you manage products
on the products page. There is no separate "admin SQL console" and no expectation
that an operator drops to `supabase.db.query` for routine data work.

For **every page that lists/owns an entity**, the page ships the full lifecycle:

- **Create** — a form/modal **on the page** to add a new row (not "insert via SQL").
- **Read** — list + detail (the display wiring of steps 1–6).
- **Update** — edit an existing row in place, **on the same page**.
- **Delete / deactivate** — remove or soft-delete **from the listing** (and, for soft-delete, **see + reactivate** deactivated rows on that page — the admin-products bug: deactivate hid the row forever because the list filtered `ativo=true`; fixed by an admin `include_inactive` + an "Ativar" action **on the products page**).

If a page **lists** an entity but offers no way to manage it there — forcing the
operator to reach for `supabase.db.query` / a migration / a one-off script — that
page is **missing its CRUD surface**: file it as a wiring gap. (Schema migrations +
seed data remain code; *operational, page-related data management* belongs on the
page that owns it.) Because every product has its own pages, **every product
inherits this mandate** — it propagates with the rule.

**Automated mechanism:** the static legs (2, 4, 5) ship on **two surfaces from
one predicate** (DRY): the `noctus.dev.scan_wiring <product>` MCP tool **and the
`cli.py --scan-wiring <product>` flag** (on-demand, per-product report; `--json`
+ `--worktree-path`-aware, exit `0` clean / `1` findings / `2` typed-error) AND —
codified as **Stage-4 keeper detectors** (regulatory: compliance gate +
pre-commit) — `check_fe_route_missing` (leg 2 — FE-endpoint → backend-route
existence, severity `high`) + `check_name_on_nome_select` (leg 5 — the
`name`-on-`nome` 500 lint, severity `high`) + `check_promise_all_shared_catch`
(leg 4 — the shared-catch all-zeros anti-pattern, severity `warning`; **precision:
flags ONLY a *pure* shared-catch — every `api.*` element under the `Promise.all`
is bare; a mixed shape (one primary call + sibling calls each `.catch()`-guarded)
is the legitimate one-primary-plus-degrading-aux pattern, NOT flagged**). Both the
tool and the keepers import the SAME three pure leg analyzers from
`mcp/noctusai/tools/noctus/dev/scan_wiring.py` (`analyze_missing_routes` /
`analyze_name_on_nome` / `analyze_promise_all_shared_catch`) — one predicate, two
surfaces, no copy-paste. The keepers are wired into `check_all_products()` +
`review.py::_detect()` with colocated `tests/test_product_wiring_keeper.py`
regression tests (true-positive + false-positive shapes pinned). The 32
pre-existing leg-2 findings the keeper surfaced (adconnect / erp-imobiliario /
therapy-platform FE calls with no matching backend route) were absorbed into the
high/critical regression baseline (`tests/compliance_baseline.json`, grow-only
with cited triage — genuine pre-existing wiring debt, not a regression to
silence; leg-4 `warning` findings never enter the baseline by severity). The
runtime leg (3) + the page-scoped-CRUD leg (7) are NOT deterministic and STAY
advisory: leg 3 is a live auth-gated endpoint probe (see the admin-probe pattern
in the trigger session); leg 7 needs judgment (the read-only/derived carve-out).

## 3 · When it fires

- **Product evaluation / audit** — assert every UI surface is wired (steps 1–7).
- **New product (scaffold)** — the seed ships a wired example surface; a scaffolded
  product inherits a wired skeleton by construction. Hand-added surfaces must wire.
- **Absorption** — an absorbed product's surfaces are wired to the real (often
  renamed) schema before sign-off (the `name`/`nome` class is an absorption smell).
- **Any new page/widget** — it ships wired (real endpoint, real data) or not at all
  (no incomplete commits — `CLAUDE.md` §1).

## 4 · Forbidden anti-patterns (the unwired smells)

- Hardcoded/stub/mock data standing in for a real fetch.
- A surface that renders `0`/empty with **no** fetch, or whose fetch silently
  swallows errors and shows zeros.
- `Promise.all([...fetches])` under one shared `catch` (one failure → all zero).
- PostgREST selecting a column that doesn't exist (EN name vs PT `nome`) — 500.
- "Route exists, therefore wired" — the slip this rule exists to kill.
- A page that **lists** an entity it owns but offers no create/edit/delete there —
  forcing raw SQL / a script to manage it (read-only ≠ managed; page-scoped CRUD).

## 5 · Provenance

Born 2026-05-25 from the core admin-panel wiring session: the all-zeros admin
Dashboard → root-caused to the `plans.name`/`nome` 500 (3 endpoints, 4 admin
pages) + the `Promise.all` fast-fail. Fixed by reading the real `nome` column +
per-endpoint catch; verified by probing **all** admin endpoints on live prod
(route-existence had passed for all; the runtime probe found the 3 broken ones).
Generalized into this rule + the per-product internal-wiring initiative
(`projects/product-internal-wiring/`). Siblings: `boundary-contract-tests.md`
("tests-green-dashboard-red" boundary class) · `core-url-routing.md` (a specific
wiring class — product↔core) · `CLAUDE.md` §1 "No incomplete commits".
