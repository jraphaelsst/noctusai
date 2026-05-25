# product-internal-wiring — Project Document

> Per-product initiative enforcing the **product-internal-wiring rule** (`KB §
> PATTERNS/product-internal-wiring.md` + CLAUDE.md §1): every product UI surface
> shows **real data** via a **real endpoint that returns real data** —
> **route-exists ≠ wired**. Born from the core admin all-zeros dashboard
> (2026-05-25), root-caused to a `plans.name`/`nome` 500 that a `Promise.all`
> single-catch turned into all-zeros across 4 admin pages.

- **Created:** 2026-05-25
- **Status:** 🚧 In progress — **Wave 1 (active): `core` · `seed` · `social-wiring`**. Wave 2 (deferred, filed not implemented): the other 7 products.
- **Owner:** joaoraphaelsst · architect
- **Related:** `KB § PATTERNS/product-internal-wiring.md` (the rule + 6-step audit) · `boundary-contract-tests.md` · `core-url-routing.md`

---

## 1 · Context & purpose

A product can look "done" (pages render, routes exist, tests pass) yet show the
user **nothing real**. The rule closes that gap: a UI surface is *wired* only when
data flows end-to-end, observed at runtime. This project audits + fixes every
product against the rule, in waves, and ships the **wiring-check mechanism**
(`noctus.dev.scan_wiring`) so the rule is verified deterministically going forward.

## 3a · Seed-first analysis

- The **rule + audit checklist** is platform-wide (one KB doc) — per-product copy = 0.
- The **wiring-check mechanism** (`noctus.dev.scan_wiring`) is ONE MCP tool (seed/dev layer) consumed across all products — per-product copy = 0.
- The **audit + fix** IS per-product by nature: each product's UI surfaces + endpoints are its own code. This is legitimately per-product work (not a replication slip) — the cross-product concern (the rule + the tool) is correctly centralized; only the realized wiring is product-local.
- **Page-scoped CRUD propagates with the rule** (user directive 2026-05-25): every product has its own pages, so every product inherits the "each page manages its own related data" mandate. Cross-product copy = 0 (rule + tool centralized); the CRUD surfaces themselves are product-local (each page's own forms/modals/edit/delete). The seed demonstrates the canonical page-scoped-CRUD shape so scaffolded products inherit it by construction.

## 4 · Scope

**Wave 1 — implement now (this session):** *(each product = the 7-step audit, incl. step 7 page-scoped CRUD: every page that lists an owned entity creates/edits/deletes it there)*
1. **`scan_wiring` tool** — `noctus.dev.scan_wiring <product>` static legs: FE-endpoint→backend-route existence + `name`-on-`nome` lint + `Promise.all` shared-catch anti-pattern + colocated test.
2. **core** — full UI-surface wiring audit + fix + **page-scoped CRUD** (manage subscriptions/products/orgs/plans/licenses on their own admin pages). admin `name`/`nome` 500s + dashboard resilience already SHIPPED 2026-05-25 `1ef21ba8`/`892d1baee28d`; this verifies the rest + adds the management surfaces + closes core.
3. **seed** — the canonical skeleton's example surface must show real data **and demonstrate page-scoped CRUD** by construction (so scaffolded products inherit a wired + manageable skeleton).
4. **social-wiring** — full UI-surface wiring audit + fix + **page-scoped CRUD** for its owned entities.

**Wave 2 — filed, deferred (NOT implemented now):** `erp-imobiliario` · `personal-finance` · `therapy-platform` · `daily-life` · `adconnect` · `dev-team` · `knowledge-extractor`. Each gets a wiring audit + fix in a later wave (gated on Wave 1 + the tool). Deferring here is the rule, not a silent error — destination = Wave 2.

## 5 · Per-product audit checklist (the 7 steps — from `KB § PATTERNS/product-internal-wiring.md`)

For each UI surface (page/widget/stat/table):
1. Extract every backend call (`api.get/post/patch/delete`).
2. Route exists (prefix + path + method) in the backend.
3. **Returns real data at runtime** — probe live with a real (admin) token: `200` + real rows, not `500`/`403`/stale shape.
4. No fast-fail aggregation (per-endpoint `.catch()`, never a shared `Promise.all` catch).
5. No EN/PT column mismatch (read `nome`, not `name`, on `nome`-tables).
6. Empty only when *truly* empty (distinguish "no data yet" from "fetch failed").
7. **Page-scoped CRUD** — each page that lists/owns an entity also **creates, edits, and deletes** that entity **on that same page** (the subscriptions page is where you manage subscriptions). Managing routine data must never require Supabase SQL or a script. *(Carve-out: pages showing genuinely read-only/derived data — analytics, audit logs, computed metrics — have no write side by design.)*

## 6 · Implementation — per-product roster

| Product | Wave | Status | Notes |
|---|---|---|---|
| `core` | 1 | 🚧 | admin `name`/`nome` + dashboard resilience SHIPPED (`1ef21ba8`); verify remaining surfaces (non-admin pages) + close |
| `seed` | 1 | ⏳ | example surface real-data-by-construction |
| `social-wiring` | 1 | ⏳ | full audit + fix |
| `scan_wiring` tool | 1 | ⏳ | the mechanism |
| `erp-imobiliario` | 2 | 📋 | deferred |
| `personal-finance` | 2 | 📋 | deferred |
| `therapy-platform` | 2 | 📋 | deferred |
| `daily-life` | 2 | 📋 | deferred |
| `adconnect` | 2 | 📋 | deferred |
| `dev-team` | 2 | 📋 | deferred |
| `knowledge-extractor` | 2 | 📋 | deferred |

## 7 · Success criteria (Wave 1)

- `noctus.dev.scan_wiring` ships (static legs + colocated test, green).
- core/seed/social-wiring: every UI surface passes the 7-step audit; the runtime probe shows real data (or genuinely-empty) on every surface; **every page that lists an owned entity creates/edits/deletes it on that page** (no routine data needs SQL/scripts); `vite build` + `pytest` green per product.
- The rule is live in CLAUDE.md §1 + KB + memory (DONE this session).
- Wave 2 (7 products) remains filed here as the deferred roster.

## 8 · Change log

| Date | Change | By |
|---|---|---|
| 2026-05-25 | Filed. Rule doc'd (`KB § PATTERNS/product-internal-wiring.md` + CLAUDE.md §1 + memory). Wave 1 = core/seed/social-wiring + the `scan_wiring` tool; Wave 2 = 7 deferred products. core admin already fixed + shipped to prod (`1ef21ba8`). | claude-opus-4-7 · architect |
| 2026-05-25 | **Page-scoped CRUD** folded into the rule (user clarification): each page manages its **own** related data (manage subscriptions on the subscriptions page); audit grows to 7 steps; propagates to every product. KB §2a + audit step 7 + CLAUDE.md §1/§2 + memory updated. | claude-opus-4-7 · architect |
| 2026-05-25 | Wave 1 shipped to `dev`: `scan_wiring` tool + 3 keepers (`4c889827`,`c2a3035e`) · shared `ResourceManager` + seed canonical CRUD (`5c88db02`) · core CRUD (orgs/subs/users + 5 shared-catch fixes) · social CRUD (EmailMarketing page; was backend-no-frontend). Methodology learnings codified (§9). | claude-opus-4-7 · architect |

## 9 · Process retro + learnings (the "doc process" deliverable)

**The playbook that worked** (rule → enforcement → seed-first → products), a reusable shape for any new product-quality rule:
1. **Rule first** (s3): KB pattern doc + CLAUDE.md §1 bullet + memory, three-way synced. The rule named the slip ("route-exists ≠ wired"; later "read-only ≠ managed").
2. **Enforcement** (s4): the static, deterministic legs became BOTH an on-demand scanner (`noctus.dev.scan_wiring`) AND `check_*` keepers — **one predicate, two surfaces** (`analyze_*` extracted once, imported by both). The judgment/runtime legs stayed advisory (honest about what a keeper can't assert).
3. **Seed-first formalize** before touching products: the hand-rolled list+modal CRUD was N=3 → built ONE shared `<ResourceManager>` + made the **seed** the canonical consumer, so it propagated into the scaffold template (new products inherit page-scoped CRUD by construction). **Meta-lesson:** the data layer (`createCrudHooks`) was *already* half-formalized-but-unused — check that before formalizing, and don't force a heavy dep (react-query) when self-contained-on-`api` fits the actual adoption reality.
4. **Products consume, in waves**: seed (reference) → core + social (parallel, file-disjoint engineers consuming the shared component). Existing working CRUD pages left as-is (don't churn).

**What surfaced + was codified (three-way synced this session):**
- **Self-branch verification-env recipe** — fresh worktrees lack node_modules/.venv; the symlink + `@noctusai` repoint + venv-PYTHONPATH recipe → `KB § PATTERNS/self-branching-mode.md § 5a` + `feedback_self_branch_verification_env`. (Biggest time-sink.)
- **Engineer worktree-slip** — one engineer drifted onto the primary checkout; hardened `engineer-default.md §1` (confirm `pwd` + never-touch-primary + FF-rebase-clean-behind-don't-blanket-STOP). VALIDATED: the next 2 engineers stayed in-worktree.
- **`ResourceManager` discoverability** → `KB § 04-SHARED-LIBRARY.md components/` (so the next product consumes, not re-hand-rolls).
- **Lib vitest render-harness dual-React gap** → `reference_lib_frontend_vitest_render_harness_gap` (not CI-gated; gate = tsc).

## 10 · Open follow-ups (filed, non-silent)
- **`scan_wiring` not live as an MCP tool** in long sessions (no `cli.py` flag) — engineers called the pure fn. Add the `cli.py --scan-wiring` flag + confirm `.mcp.json`/registration ships (MCP-first-scripts convention: tool + flag + test).
- **`scan_wiring` leg-4 precision** — the `Promise.all` shared-catch detector near-false-positives on the "one-primary + degrading-aux" shape (bare *first* element that's the deliberate auth/error driver, siblings already `.catch()`-guarded). Refinement: treat an element as guarded if ≥1 sibling has `.catch()` AND the bare element is the documented primary. Route through the codification pipeline.
- **`task_branch action=start` env auto-wire** — automate the §5a verification-env recipe so FE/backend self-branch tasks can build/test without manual symlinking.
- **Wave 2** — the 7 deferred products (erp/PF/therapy/daily-life/adconnect/dev-team/knowledge-extractor) get the 7-step audit + page-scoped CRUD in a later wave (gated on Wave 1 green). The keepers now flag their leg-2 debt in the baseline (adconnect 20 / therapy 9 / erp 3).
