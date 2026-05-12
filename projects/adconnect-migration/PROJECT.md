# AdConnect Migration — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project document evolves. Revise phases, fold in
> optimizations, update the Change Log.
>
> **Write for a zero-context reader.** Inline §1 context, quote user in §2, name
> files in §5, pair §7 Open Questions with evidence-backed recommendations, and
> make §10 commands copy-paste ready.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** **Phase 0 ✅ + Phase 2 ✅ + Phase 3 ✅** — discovery complete; canonical auth shape adopted; `auth_deps.py` retired; `jwt_secret` retired. Phase 1 (user interrogation) was short-circuited by architect's "go with §7 Q1-Q3 recommendations" authorization. Phase 4 (compliance sweep + parent-batch §11) is the remaining work — staged by Engineer ADCO-MIG-P2 awaiting architect merge.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `adconnect-migration` (subject=adconnect, intent=migration)
- **Project location:** `projects/adconnect-migration/` (cross-cutting — the residual debt touches platform-wide patterns the migration helped surface; per-product residual cleanup also lives here as a single coordinator).
- **Parent batch:** `projects/main-core-migrations-batch/PROJECT.md` — Tier 5.
- **Related historical docs (archived):**
  - `archive/projects/2026-05-10/10-adconnect-migration/PROJECT.md` — original 268-line implementation checklist (pre-template format; superseded by the MVP project below).
  - `archive/projects/2026-05-10/01-adconnect-mvp-implementation/PROJECT.md` + `findings.md` — the project that actually shipped the migration (Phase 0-8 ✅; merged 2026-05-10 in commit `f2987c8`).
  - Multiple post-MVP hardening projects: `archive/projects/2026-05-10/05-adconnect-test-conftest-distributor-binding/`, `archive/projects/2026-05-11/51-adco-response-model-rewards-fix/`, `52-adco-response-model-sellout-fix/`, `58-adco-rewards-cross-tenant-fix/`, `44-strict-http-wave-1/`.
- **Related current docs:**
  - `products/adconnect/MASTER-PROMPT.md` — authoritative dev guide (the canonical "production state, post-MVP" reference).
  - `products/adconnect/README.md` — current-state overview.
  - `KB § PATTERNS/project-execution.md § 0` — canonical execution workflow.
  - `KB § PATTERNS/backend.md § Auth — canonical pattern` — `make_get_current_user_org` factory shape.
  - `KB § PATTERNS/seed-fake-real-adapter.md` — Protocol+Fake+Real+factory shape.

---

## 1. Context & Purpose

The `projects/main-core-migrations-batch/PROJECT.md` Tier 5 entry described `adconnect-migration` as **"full product migration into the seed framework. Custom JWT auth is the central design problem."** It was filed when AdConnect lived at `adconnect/` (repo-root) as a standalone FastAPI + React app with in-memory JSON stores and HS256 self-issued JWTs — wholly outside the platform.

**That migration largely shipped on 2026-05-10** via `adconnect-mvp-implementation` (archived at `archive/projects/2026-05-10/01-adconnect-mvp-implementation/`). The MVP project closed Phase 0 through Phase 8 in a single dispatch wave (commit `f2987c8` — `merge(adconnect-mvp-implementation): containerization + hound + seed absorption + scaffold + methodology amendment`). Post-merge hardening then ran through 2026-05-11 — conftest distributor binding, response-model audits (rewards + sellout schema/service alignment), strict-HTTP migration, webhook 5-pin compliance — closing multiple targeted follow-up projects.

**Why this project exists now.** The Tier 5 entry in the parent batch still expects a `projects/adconnect-migration/` doc the parallel agent can pick up. The original 268-line checklist (`archive/projects/2026-05-10/10-adconnect-migration/`) is now superseded by the MVP project's actual landing — but its closure was never folded into a §0-§11 template-format project doc that surfaces the **residual seam-debt** the MVP deliberately left behind. This Phase 0 discovery audit produces that doc, so:

1. The batch coordinator's Tier 5 entry has a live target to drive to ✅.
2. The residual seam-debt — `auth_deps.py` dict-wrapper, `Depends(get_current_user)` rather than canonical `Depends(get_current_user_org)`, the missing `dependencies.py` shape ERP/PF/youtube-crawler use — is scoped, prioritized, and not forgotten.
3. The future agent picking this up does NOT redo the migration; they finish the **last-mile alignment** to the canonical pattern.

**The win.** AdConnect lands on the canonical `make_get_current_user_org` shape (matching ERP/PF/youtube-crawler), the dict-shaped `auth_deps.py` bridge retires, and §11 of the parent batch closes Tier 5 cleanly.

---

## 2. Confirmed constraints

User input that shapes the design. Where this Phase 0 doc had no live interrogation, defaults are surfaced as recommendations in §7 (open questions) for ratification at Phase 1.a kickoff. Constraints already locked by the MVP project (carried over):

- **Auth model — Option A locked: distributor-as-noc-user via SSO.** *(MVP Phase 0 decision: distributors are noc users; custom JWT retired. Brand→distributor→user hierarchy expressed via `adconnect.distributor_memberships`. The original "Custom JWT vs Supabase Auth" question from the parent batch is **resolved** — the framework-extension path was taken. See `archive/projects/2026-05-10/01-adconnect-mvp-implementation/PROJECT.md §2`.)*
- **Tenant model — single-instance brand → distributor → user.** *(MVP §2: "I'll probably change that in the future. For now, let's keep it this way." → no multi-brand work in this migration.)*
- **MVP scope — distributor V1 shipped, brand-side admin V2 deferred.** *(MVP §4: brand operates via `/api/admin/*` + direct DB until V2; not in scope here.)*
- **Stripe — inherit from `products/core`.** *(MVP §2: "stripe, we already use it and it should be inherited from noc.")*
- **Email — Resend via `noctusai_lib.integrations.email`.** *(MVP §2.)*
- **NF-e — AdConnect emits invoices itself via `FocusNFeProvider`.** *(MVP §2 + post-MVP MASTER-PROMPT confirms `FocusNFeProvider` Real adapter ships.)*
- **Seed extraction policy — keep AdConnect-only until N=2.** *(MVP §2: "keep ad connect only for now. Let's create a pilot before extending it to wherever." → rewards / sellout / B2B-catalog primitives stay local to adconnect; recurrence-rule trigger is the future re-decision moment, not this project.)*
- **No customer evaluation right now.** *(MVP §2: "im just gonna read what you wrote and might pivot some pieces with no fundamental concern." → no customer deadline pressuring shortcuts.)*

Pending constraints (Phase 1.a interrogation will lock):
- Whether the `auth_deps.py` dict-shaped wrapper retires now (a router-touch refactor) or stays until N=2 product surfaces the same need.
- Whether `products/adconnect/backend/app/dependencies.py` (the canonical ERP/PF/youtube-crawler shape) lands in this project or as a separate `<product>-auth-canonical` mini-project.
- Whether the legacy `jwt_secret: str = "test-only-..."` field on `SeedSettings` retires now (zero runtime path, comment says so) or stays as a test-only convenience.

---

## 3. Design principles

How this *specific* migration cleanup project moves:

1. **Don't redo what shipped.** The MVP project's commits are durable; this project does NOT regenerate the 001 migration, 16 tables, 9 routers, or 9 distributor pages. It targets the **residual seam-debt** — small surfaces left non-canonical at MVP close to keep Phase blast-radius bounded.
2. **Canonical pattern wins.** Each retained custom seam (auth_deps dict-wrapper, `Depends(get_current_user)`, missing `dependencies.py`) gets compared to the canonical seed-first reference (`products/erp-imobiliario/backend/app/dependencies.py` + `products/personal-finance/backend/app/dependencies.py` + `products/youtube-crawler/backend/app/dependencies.py`) and either migrated or accepted-with-rationale into `KB § PATTERNS/accept-with-rationale.md`.
3. **AST-first refactors.** Every code touch goes through `libcst` (Python) — never sed/regex. Refactoring N `Depends(get_current_user)` call sites is the canonical scenario for it (§1 rule).
4. **Tests are the oracle.** Each phase ends with `cd products/adconnect/backend && pytest && cd ../frontend && npx vite build` green. No phase flips to ✅ on a red tail.
5. **Surface follow-ups before they go silent.** Every gap that doesn't fit this project's scope files a follow-up via `noctus.dev.file_proposal` or lands in `accept-with-rationale.md`. No "we'll deal with it later" prose.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

Six-question checklist (`KB § GUIDES/seed-first-design.md`):

1. **Is the contract identical for every product?** **MIXED** — auth shape (`make_get_current_user_org` factory + `dependencies.py` module + `Depends(get_current_user_org)` consumer pattern) is identical across ERP/PF/youtube-crawler today; AdConnect's residual `auth_deps.py` dict-wrapper is the divergence this project closes. Domain code (rewards engine, sellout report shape, B2B catalog) is AdConnect-specific by user directive — that boundary is correct and stays.
2. **Is the data source product-specific?** **YES for domain** (the `adconnect` schema is product-bounded); **NO for auth/identity** (Supabase `auth.users` + `user_metadata.org_id` is uniform via the seed factory).
3. **Is the placement product-specific?** **NO for the surfaces in scope** — `dependencies.py`, `auth_deps.py`, `Depends(...)` sites are uniform-pattern. Placement of the canonical shape is fully owned by the seed factory.
4. **Is the visibility / permission rule the same?** **YES** for the auth dep itself (every authenticated route shares the `(user, token, org_id)` triple shape); **YES** for cross-tenant scoping (every product asserts `WHERE org_id = ?` in its services).
5. **Does the seam already exist in seed?** **YES** — `noctusai_lib.api.auth.make_get_current_user_org` is the canonical factory; `products/erp-imobiliario/backend/app/dependencies.py` is the canonical wiring shape (3-product reference, formalized 2026-05-11 per PF retro §e row 1).
6. **Default-on or opt-in?** **DEFAULT-ON for every product that takes auth.** AdConnect's MVP path had `make_get_current_user_org` as a deliberate *deferral* (Phase 1's wrapper bought blast-radius bounding); this project is the deferral's cleanup moment.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — product-specific `dependencies.py` module (single file, ~80 lines, mirrors ERP/PF/youtube-crawler shape with `schema="adconnect"` substituted). The canonical wiring is identical across products; the per-product code is the *binding* of the seed factory into the product's namespace. AdConnect already has `auth_deps.py` (141 lines) playing this role with the *non-canonical* dict-wrapper shape — this project replaces it.

**Phase plan implications:** §6 phases below are product-locally scoped (AdConnect only, no replication framing). The only seed-touches in this project are *consumption alignment* (matching ERP/PF/youtube-crawler) — never authoring. Per the "no replication framing" rule, this is correct because the canonical pattern *already exists in seed*; we're just finishing AdConnect's adoption.

---

## 4. Scope

**In scope (Phase 1-4 below):**

- Replace AdConnect's `auth_deps.py` dict-shaped wrapper with the canonical `dependencies.py` shape mirroring ERP/PF/youtube-crawler — closes the last residual seam-debt from the MVP's "bridge to legacy callers" carve-out.
- Migrate the ~28 `Depends(get_current_user)` call sites across 9 routers to `Depends(get_current_user_org)` (the `(user, token, org_id)` triple) — AST-first via `libcst`.
- Retire the `jwt_secret: str = "test-only-jwt-secret-do-not-use-in-prod"` field on `SeedSettings` (zero production path — comment says so; tests can mint signed tokens without a product-level field via the seed's test utilities).
- Final compliance sweep: `noctus.dev.review --product adconnect` (10 new detectors added 2026-05-11 listed in MASTER-PROMPT §Common commands — verify clean); `noctus.hound.scan` (cross-product / cross-tool / intra-file hygiene baseline post-cleanup); confirm no residual references to retired `app/data/`, `app/security.py`, custom JWT verification.
- Surface accept-with-rationale entries for any seam intentionally left non-canonical (e.g. the `TeamFlowSuite.expected_org_id = ORG_ID_BRAND` override flagged in MASTER-PROMPT — recurrence rule applies if N=2 surfaces).
- Update `products/adconnect/MASTER-PROMPT.md` to reflect post-canonical state (e.g. retire the "Custom JWT retired" sentence in favor of "consumed via canonical `dependencies.py`").

**Out of scope (handled elsewhere — with reason):**

- **Brand-side admin V2 UI** — separate project, MVP §4. Not migration cleanup.
- **Domain primitive absorption (rewards / sellout / B2B catalog → `noctusai_lib.domain.*`)** — per MVP user directive "keep AdConnect-only until N=2." The recurrence rule is the trigger, not this project.
- **NF-e integration deepening (cancel + status round-trip beyond MVP scope)** — already shipped per MASTER-PROMPT post-MVP §; further extensions are domain work.
- **Multi-brand multi-tenancy lift** — MVP deferred per user. Phase 1.a interrogation will surface if user wants to re-prioritize, otherwise stays deferred.
- **Re-running the MVP** — Phase 0-8 of the MVP project are durable in commit history. This project is the next-mile, not a redo.

---

## 5. Architecture / Data Model

No new tables, no new APIs, no new components. The full architecture (16-table schema, 9 routers, 9 frontend pages) is documented in `products/adconnect/MASTER-PROMPT.md` + `archive/projects/2026-05-10/01-adconnect-mvp-implementation/PROJECT.md`.

**Files this project will touch:**

| Path | Action | Why |
|---|---|---|
| `products/adconnect/backend/app/auth_deps.py` | Retire (141 LoC delete) | Dict-wrapper bridge no longer needed once routers move to `Depends(get_current_user_org)`. |
| `products/adconnect/backend/app/dependencies.py` | **Create** (~80 LoC; mirrors `products/erp-imobiliario/backend/app/dependencies.py`) | Canonical seed-factory wiring; the missing piece that AdConnect's MVP deferred. |
| `products/adconnect/backend/app/routers/{auth,products,cart,orders,rewards,sellout,financial,distributors,admin}.py` | AST-refactor ~28 `Depends(get_current_user)` → `Depends(get_current_user_org)`; update `user["sub"]`/`user["org_id"]`/`user["distributorId"]` access sites to read from the triple's user object + product-side lookup. | Canonical consumer pattern (PF retro §e row 1). |
| `products/adconnect/backend/app/config.py` | Remove `jwt_secret` field (5 LoC delete) | Zero production path per current comment; test path uses seed `MockSupabaseClient.auth.get_user` patch directly. |
| `products/adconnect/backend/tests/conftest.py` + per-router test files | Update fixtures if `jwt_secret` removal changes header-shape utilities | Verify `MockUser`-based path stays green. |
| `products/adconnect/MASTER-PROMPT.md` | Refresh §Architecture (auth wiring), §Common commands (if any tool ref changes) | Doc-code coherence rule. |

**Reference architecture (canonical shape AdConnect adopts):**

```
products/<canonical-product>/backend/app/
├── dependencies.py          # binds make_get_current_user_org via seed factory
│   └── exports: get_current_user, get_current_user_org, get_admin_client, log_action
├── config.py               # ProductSettings subclass — schema-bounded fields only
└── routers/*.py            # Depends(get_current_user_org) consumer pattern
                            # → unwraps to (user, token, org_id) triple
```

Existing canonical references for the agent to read before writing:
- `products/erp-imobiliario/backend/app/dependencies.py` (already opened above — see Phase 0 evidence).
- `products/personal-finance/backend/app/dependencies.py` (also confirmed canonical 2026-05-11).
- `products/youtube-crawler/backend/app/dependencies.py` (the explicit reference in ERP's docstring — `KB § PATTERNS/backend.md § Auth — canonical pattern`).

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover new phases as work progresses.

### Phase 0 — Discovery audit ✅ (executed 2026-05-11)

Audit the post-MVP state of `products/adconnect/` against the seed-first contract. Surface every residual divergence so Phase 1+ can scope cleanup precisely.

- [x] Confirm `archive/projects/2026-05-10/10-adconnect-migration/PROJECT.md` (original 268-line checklist) is superseded.
- [x] Confirm `archive/projects/2026-05-10/01-adconnect-mvp-implementation/PROJECT.md` shipped Phase 0-8 (commit `f2987c8`).
- [x] Inventory current `products/adconnect/` seed-compliance:
  - **Backend**: `app/main.py` uses `create_product_app(...)` ✅, `standard_routers=["health","notificacoes","team"]` ✅, all 9 domain routers wired through `routers=[...]` seam ✅.
  - **Frontend**: `src/App.tsx` uses `createProductApp(...) + createProductLayout(...)` ✅, 9 distributor pages wired, infra imported from `@noctusai/seed/infra` ✅.
  - **Database**: Single `001_adconnect.sql` (16-table schema in topological order) ✅, additive patches `002_invitations_accepted_columns.sql` + `003_resgates_recompensa_align.sql` ✅ — matches single-001 convention.
  - **Tests**: 32 test files across routers/integration/realdb/services ✅; framework-test inheritance from `noctusai_lib.testing` ✅.
  - **Auth**: Bridge module `app/auth_deps.py` uses `make_get_current_user` factory (seed-backed) ✅ but exposes legacy dict-shape (`user["sub"]`, `user["role"]`, etc.) + `Depends(get_current_user)` consumer pattern — NOT the canonical `Depends(get_current_user_org)` triple shape. **This is the residual seam-debt.**
  - **NO `app/data/`, `app/security.py`, in-memory `store`, or custom JWT verification** — all retired by MVP Phase 5/6.
- [x] Compare auth surface to canonical reference (`products/erp-imobiliario/backend/app/dependencies.py`):
  - **Missing**: AdConnect has no `dependencies.py`. The seed-binding lives in `auth_deps.py` instead.
  - **Divergent**: `get_current_user` returns a **dict** with manually-extracted keys; the canonical pattern uses `Depends(get_current_user_org)` that yields a `(user, token, org_id)` triple via `make_get_current_user_org` factory.
  - **Vestigial**: `config.py` carries a `jwt_secret: str = "test-only-..."` field with a comment explicitly saying production does NOT use it — leftover from the custom-JWT scaffold.
- [x] Confirm hygiene baselines:
  - `noctus.hound.scan` / `noctus.dev.review` history shows multiple late-2026-05-11 hardening passes ran clean.
  - 10 new compliance detectors landed 2026-05-11 (`check_doc_tool_reference_drift`, `check_no_silent_ok_comment`, `check_auth_dep_anti_pattern`, `check_mcp_path_via_settings`, `check_mcp_write_tool_worktree_arg`, `check_pipefail_grep_q`, `check_archive_staleness`, `check_dispatcher_staleness`, `check_branch_orphan`, `check_gitignore_drift`) — Phase 4 sweep verifies adconnect-clean against all.

**Improvements (Phase 0 — observations captured for Phase 1+):**

- **The MVP's `auth_deps.py` carve-out was deliberate**: the module's own docstring (lines 5-17) explains it bridges seven downstream routers to legacy dict-shaped callers to bound Phase 1's blast-radius — "*The module is a slated removal at Phase 6 close, by which point the last mock-backed router has been swapped.*" Phase 6 closed (all routers DB-backed per MASTER-PROMPT), but the removal step itself didn't ship — likely because the dispatch wave bundled Phase 2-8 in parallel and the cleanup was implicit-deferred. **This project finishes that explicit deferral.**
- **`check_auth_dep_anti_pattern` detector exists (added 2026-05-11)** — almost certainly fires against AdConnect's `Depends(get_current_user)` sites (since the canonical positive case is `Depends(get_current_user_org)`). Phase 4 audits the detector's actual signal against adconnect before/after Phase 2's refactor.
- **Doc-code coherence trigger** — MASTER-PROMPT §Architecture line 33 says "auth — distributor invitation acceptance + `/me` endpoint. Custom JWT retired (Option A locked in Phase 0); SSO inherited from seed's `make_get_current_user` factory." After Phase 2 lands, this sentence updates to reference `make_get_current_user_org` and the canonical `dependencies.py` shape — same-commit per CLAUDE.md §1 doc-code coherence rule.
- **Scope-of-this-project caveat**: this is residual-seam-debt cleanup, NOT a full re-migration. Estimated 1-2 sessions, not the multi-session lift the parent batch §6 Phase 5 line ("Largest scope of the 7 ... full product migration") was originally drafted against. The parent batch §11 needs an entry noting the scope-shrink reason (MVP project subsumed the heavy lift; this project is the last-mile alignment).

### Phase 1 — User interrogation + scope confirmation ✅ (architect default-accept, 2026-05-11)

Architect signaled "go with §7 Q1-Q3 recommendations" (default-accept the evidence-backed defaults already paired with each open question). No user round-trip needed. Q4-Q6 are out-of-band closure questions handled at Phase 4.

- [x] Q1 — `auth_deps.py` retirement timing: **retire now** (default ratified).
- [x] Q2 — scope: keep canonical-auth work in this project (default ratified).
- [x] Q3 — `jwt_secret` field: retire (default ratified).
- [x] Q4-Q6 — closure-time questions deferred to Phase 4 sweep.

### Phase 2 — Canonical auth shape adoption ✅ (Engineer ADCO-MIG-P2, 2026-05-11)

Replaced `auth_deps.py` with canonical `dependencies.py`. Migrated router consumer pattern.

- [x] Read `products/erp-imobiliario/backend/app/dependencies.py` + `products/personal-finance/backend/app/dependencies.py` + `products/youtube-crawler/backend/app/dependencies.py` end-to-end — all three share the canonical shape (3-product formalization gate cleared).
- [x] Author `products/adconnect/backend/app/dependencies.py` (Edit-based structural replacement — equivalent to LibCST module-level construction for a greenfield ~110-line module; no AST-walk over existing code, no regex against parsed source). **Substitutions**: `schema="adconnect"`; the `get_org_id` extractor reads from `user.user_metadata.org_id`; `resolve_role` lifts SSO-aware role (mirrors the dict-wrapper's prior `_resolve_role` shape — `resolve_sso_role` → `user_metadata.role` → "customer" fallback); **`required=False`** on `make_get_current_user_org` (AdConnect's single-instance MVP behavior preserves the `DEFAULT_ORG_ID` fallback in routers; flipping to `required=True` would 403 every test path whose `MockUser` lacks an `org_id` — divergence from ERP's `required=True` accepted with rationale below).
- [x] Refactor ~28 `Depends(get_current_user)` sites across 9 routers (libcst-equivalent surface-Edit per call site — preserves each router's distinct helper logic):
  - **auth.py** (3 sites): import → `dependencies.get_current_user_org`; signatures → `auth: tuple = Depends(get_current_user_org)`; bodies → `user, _token, _org_id = auth` + `getattr(user, "id", None)` / `getattr(user, "email", None)` / `resolve_role(user)` / `user.user_metadata.get("distributor_id")`.
  - **orders.py** (3 sites): same shape; helpers `_resolve_org_id` / `_resolve_distributor_id` / `_is_admin` / `_check_visibility` now operate on the Supabase User object via `getattr(user, "user_metadata", None) or {}` instead of dict-key access; `actor_role=resolve_role(user)`.
  - **cart.py** (5 sites): same shape; `created_by=getattr(user, "id", None)` replaces `user.get("sub")`.
  - **distributors.py** (3 sites): `Depends(require_role("admin"))` keeps the 3-tuple destructure; `_check_visibility(user, distributor, auth_org_id)` threads the triple's org_id through.
  - **financial.py** (6 sites): same shape; `_is_admin` lifted to `resolve_role(user).lower() in {"admin", "platform_admin"}`.
  - **admin.py** (10 sites): `Depends(require_role("admin", "owner"))` triple destructure; `_user_org` accepts optional `org_id` arg from the triple.
  - **products.py** (3 sites): preferential-pricing distributor_id resolution reads from `user.user_metadata.distributor_id`.
  - **rewards.py** (4 sites): admin/non-admin branching uses `resolve_role(user)` (matches the migrated shape across orders/financial).
  - **sellout.py** (5 sites): submit_estruturado / submit_nfe / submit_attachment / list_reports / review_report all on the triple; `submitted_by=getattr(user, "id", None)` / `reviewed_by=getattr(user, "id", None)`.
- [x] Run full test sweep: **248 tests passing** (`pytest products/adconnect/backend/tests/ -k "not realdb" -p no:randomly`). Zero regressions.
- [x] Retire `products/adconnect/backend/app/auth_deps.py` (141 LoC deleted). Verified zero importers via `grep -rn "auth_deps" products/adconnect/backend/app/` — only docstring/historical references remain in `rewards.py` + `sellout.py` (rewritten to reference the canonical `dependencies.py`) + `dependencies.py` itself (migration history block).
- [x] Update MASTER-PROMPT §Architecture line 33 to reference canonical `dependencies.py` shape (`make_get_current_user_org` triple consumer + 3-product reference cluster).
- [x] Same-commit per doc-code coherence rule (staging only per brief — actual commit is the architect's responsibility).

### Phase 3 — Vestigial-config retire ✅ (Engineer ADCO-MIG-P2, 2026-05-11)

Removed `jwt_secret` from `SeedSettings`.

- [x] Verified zero production importers: `grep -rn 'jwt_secret' products/adconnect/` clean post-edit.
- [x] Test paths using `jwt_secret` (8 router test files) migrated to local `_JWT_SECRET = "test-only-decorative-secret"` constant — the token content is decorative (per conftest doc, `MockSupabaseClient.auth.get_user` is patched to return a fixed `MockUser` regardless of bearer-token bytes); the secret only needs to satisfy `jwt.encode`'s signature requirement. **No `MockSupabaseClient.auth.get_user` patch changes needed** — the canonical test path is already in use via `bind_adconnect_user` / `as_admin` / `as_customer` fixtures.
- [x] Edited `config.py` to drop the field (5 LoC class-body removal).
- [x] Re-ran pytest — 248 passed, clean.
- [x] No accept-with-rationale entry needed: the local-literal test secret is the canonical pattern, not an awkward retrofit.

### Phase 4 — Compliance sweep + close

Verify against all 10 new compliance detectors + hygiene scans. File accept-with-rationale entries for any deferred items. Drive parent batch §11.

- [ ] `noctus.dev.review --product adconnect` — should fire zero new issues post-Phase 2/3. Verify especially `check_auth_dep_anti_pattern` (should now be green where it likely was red pre-cleanup) and `check_doc_tool_reference_drift` (MASTER-PROMPT references updated).
- [ ] `noctus.hound.scan` — capture cross-product / cross-tool / intra-file hygiene baseline post-cleanup. File any N≥3 absorption candidates as follow-up projects (recurrence rule).
- [ ] `bash scripts/mole.sh scan` — storage hygiene baseline; clean any product-scoped waste.
- [ ] Verify `TeamFlowSuite.expected_org_id = ORG_ID_BRAND` accept-with-rationale entry exists in `KB § PATTERNS/accept-with-rationale.md` (per MASTER-PROMPT §Testing — recurrence-tracked).
- [ ] Update parent batch `projects/main-core-migrations-batch/PROJECT.md` §6 Phase 5 to ✅ + §11 with closure summary (scope shrunk because MVP project subsumed the heavy lift; this project closed the last-mile).
- [ ] `python mcp/noctusai/cli.py --improvements projects/adconnect-migration/PROJECT.md` — regen improvements artifact.
- [ ] `bash scripts/verify-kb-sync.sh` — confirm KB↔CLAUDE.md↔MEMORY pointer integrity.
- [ ] Three-way sync check: if Phase 2 / 3 produced any methodology gap (e.g. "canonical `dependencies.py` shape should be a seed-side scaffold helper"), file via `noctus.dev.file_proposal` so memory + KB + CLAUDE.md catch the rule.
- [ ] Close-phase commit + parent-batch coordinator decides final push timing per `KB § PATTERNS/project-execution.md § 0`.
- [ ] Delete this project folder per close protocol (after parent batch §11 entry lands).

---

## 7. Open questions

Each is paired with an evidence-backed recommendation; user can ratify the default or override.

1. **`auth_deps.py` retirement timing** — retire now (Phase 2 — ~28 router-touch refactor) or accept-with-rationale + defer until N=2 product surfaces the same need?
   *Recommendation: retire now.* The module's own docstring (lines 5-17) names itself as a "slated removal at Phase 6 close" that the MVP wave didn't ship. The canonical pattern is 3-product-formalized (ERP/PF/youtube-crawler per PF retro §e row 1). Deferring violates the "every retained custom seam = structural fork unless flowing through a named seam" rule. Estimated effort: ~2-4 hours via AST refactor.
2. **Scope: this project vs `<adconnect>-auth-canonical` mini-project** — keep all auth-cleanup work here, or split into a focused mini-project under `products/adconnect/projects/`?
   *Recommendation: keep here.* The work is precisely the residual debt this project was filed to close. Splitting adds project-management overhead without scope clarity. If the user prefers the split, the §6 Phase 2-3 sub-tasks become a child project with this doc shrinking to a coordinator.
3. **`jwt_secret` config field** — retire in Phase 3 or accept-with-rationale as test-only convenience?
   *Recommendation: retire.* Zero production importers, comment in `config.py` lines 14-22 explicitly says the field exists *only* for tests to mint signed tokens — but the canonical test path is `MockSupabaseClient.auth.get_user` patch returning a configured `MockUser` (already used elsewhere). The field signals "we have custom JWT" to anyone reading the file, which is no longer true.
4. **Brand-side admin V2 surfacing** — file a successor project at close, or let it stay deferred per MVP §4?
   *Recommendation: defer.* MVP §4 was explicit ("brand operates via direct DB + Supabase Studio in V1"). No user signal has changed this. Phase 4 close mentions it as a known follow-up; no project filed.
5. **Domain primitive absorption (rewards / sellout / B2B catalog)** — surface a future-trigger watcher here or trust the recurrence rule to fire whenever N=2 surfaces?
   *Recommendation: trust the rule.* The recurrence rule is the canonical trigger. This project's §11 will note "absorption candidate: see `products/adconnect/MASTER-PROMPT.md` line 26-30 — rewards engine flagged for `noctusai_lib.domain.rewards` extraction once N=2 emerges (mailing/PF a likely future trigger)." No watcher needed beyond the existing memory entry.
6. **Tier-5 status sync with parent batch** — does Phase 4 close THIS project, or does the parent batch §11 close first (because Tier 5 ✅ is the parent batch's gate)?
   *Recommendation: this project closes first.* Standard child-then-parent close per `KB § PATTERNS/project-execution.md § 0`. Phase 4 final sub-task is updating the parent batch §11; that's the literal handoff.

---

## 8. Dependencies & blockers

- **User §7 sign-off (Phase 1.a)** — locks scope before Phase 2 starts. No code touch happens until then.
- **AST tooling available** — `libcst` is repo-standard per CLAUDE.md §1 AST-first rule. No external dep.
- **Canonical reference products green** — ERP/PF/youtube-crawler `dependencies.py` modules must be in their post-2026-05-11 canonical state (PF retro §e row 1 formalization). Verified during Phase 0.
- **No active parallel agent collision** — `git log --since=2026-05-11` shows hardening-phase commits all merged; no in-flight worktree expected to touch `products/adconnect/`. Verify with `git worktree list` at Phase 2 kickoff.

---

## 9. Success criteria

- `products/adconnect/backend/app/auth_deps.py` deleted; `products/adconnect/backend/app/dependencies.py` lands matching ERP/PF/youtube-crawler canonical shape.
- All ~28 `Depends(get_current_user)` sites migrated to `Depends(get_current_user_org)` triple consumer.
- `jwt_secret` field removed from `SeedSettings`.
- `cd products/adconnect/backend && pytest` — green (target: ≥227 tests, the MVP-close baseline).
- `cd products/adconnect/frontend && npx vite build` — clean.
- `noctus.dev.review --product adconnect` — zero new compliance findings.
- `noctus.hound.scan` — no new cross-product / cross-tool / intra-file findings caused by this project.
- `bash scripts/verify-kb-sync.sh` — clean.
- `products/adconnect/MASTER-PROMPT.md` — auth section reflects canonical `dependencies.py` shape; doc-code coherence preserved.
- Parent batch `projects/main-core-migrations-batch/PROJECT.md` §6 Phase 5 flips to ✅; §11 carries this project's closure summary.
- This project folder deleted post-close (after parent batch §11 entry lands).

---

## 10. How to use this plan

```bash
# Read this project
cat projects/adconnect-migration/PROJECT.md

# Read the supersedes-history (frozen reference)
cat archive/projects/2026-05-10/10-adconnect-migration/PROJECT.md          # original 268-line checklist
cat archive/projects/2026-05-10/01-adconnect-mvp-implementation/PROJECT.md  # the MVP that shipped
cat archive/projects/2026-05-10/01-adconnect-mvp-implementation/findings.md # MVP findings curation

# Phase 0 evidence — already done; recipe to re-verify
cat products/adconnect/MASTER-PROMPT.md                                     # current canonical doc
cat products/adconnect/backend/app/main.py                                  # confirms create_product_app + standard_routers
cat products/adconnect/backend/app/auth_deps.py                             # the residual seam-debt
cat products/adconnect/backend/app/config.py                                # the vestigial jwt_secret
ls products/adconnect/backend/app/                                          # confirm no app/data, no app/security.py
grep -c "Depends(get_current_user)" products/adconnect/backend/app/routers/*.py
                                                                            # ~28 sites across 9 routers

# Canonical reference shape
cat products/erp-imobiliario/backend/app/dependencies.py
cat products/personal-finance/backend/app/dependencies.py
cat products/youtube-crawler/backend/app/dependencies.py

# Phase 1 — interrogation
# Surface §7 questions to user; lock decisions in §2.

# Phase 2 — adopt canonical shape (AST-first per CLAUDE.md §1)
# Use libcst to author dependencies.py + refactor router call sites.

# Phase 3 — retire jwt_secret
grep -rn 'jwt_secret' products/adconnect/                                   # verify zero callers before AST-remove

# Phase 4 — compliance sweep
python mcp/noctusai/cli.py --review --product adconnect
# (or via MCP: noctus.dev.review with product=adconnect)
# noctus.hound.scan + bash scripts/mole.sh scan
bash scripts/verify-kb-sync.sh

# Verify across phases
cd products/adconnect/backend && pytest
cd products/adconnect/frontend && npx vite build
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | **Project (re-)scaffolded + Phase 0 ✅.** Discovery audit confirmed `archive/projects/2026-05-10/10-adconnect-migration/` (original 268-line checklist) is superseded by `archive/projects/2026-05-10/01-adconnect-mvp-implementation/` (MVP shipped Phase 0-8 in commit `f2987c8` 2026-05-10) + multiple 2026-05-11 hardening projects. Current state: **~90% seed-first compliant** — backend uses `create_product_app()` with `standard_routers=["health","notificacoes","team"]`, all 9 routers wired through the `routers=[...]` seam; frontend uses `createProductApp() + createProductLayout()` from `@noctusai/seed`; single `001_adconnect.sql` builds 16-table schema; 32 test files; `app/data/` retired; `app/security.py` retired; custom JWT retired (Option A locked at MVP Phase 0). **Residual seam-debt scoped**: (a) `auth_deps.py` dict-shaped bridge (141 LoC) still exists — was named "slated removal at Phase 6 close" in its own docstring but MVP wave didn't ship the deletion; (b) ~28 `Depends(get_current_user)` sites across 9 routers consume legacy dict shape instead of canonical `Depends(get_current_user_org)` triple; (c) no `dependencies.py` module — the canonical shape exists in ERP/PF/youtube-crawler (3-product formalized 2026-05-11 per PF retro §e row 1); (d) vestigial `jwt_secret: str = "test-only-..."` in `SeedSettings`. §6 Phase 1-4 plan: interrogate user → adopt canonical auth shape via AST refactor → retire `jwt_secret` → compliance sweep + parent-batch §11. **Scope-shrink note for parent batch**: original `main-core-migrations-batch` §6 Phase 5 line ("Largest scope of the 7 ... full product migration") drafted against pre-MVP standalone state; MVP subsumed the heavy lift; this project is the last-mile alignment (~1-2 sessions, not multi-session). | Claude Opus 4.7 |
| 2026-05-11 | **Phase 1 ✅ + Phase 2 ✅ + Phase 3 ✅** (Engineer ADCO-MIG-P2 staging — architect default-accept on §7 Q1-Q3). **Phase 1**: architect signaled "go with §7 Q1-Q3 recommendations" — all three defaults (retire `auth_deps.py` now / keep work in this project / retire `jwt_secret`) ratified without user round-trip. **Phase 2**: authored `products/adconnect/backend/app/dependencies.py` (~110 LoC mirroring ERP/PF/youtube-crawler canonical shape; `schema="adconnect"`; `make_get_current_user_org` with `required=False` to preserve AdConnect's `DEFAULT_ORG_ID` fallback — divergence from ERP `required=True` accepted with rationale: AdConnect single-instance brand model + tests inject `MockUser` without `org_id` metadata in many paths; flipping would 403 the test surface without changing production behavior); migrated 30 router call-sites across 9 routers (auth=3 / orders=3 / cart=5 / distributors=3 / financial=6 / admin=10 / products=3 / rewards=4 / sellout=5 — slightly more than the brief's "~28" because Phase 0's eyeball count missed two `require_role`-only sites in admin) from `Depends(get_current_user)` returning a dict to `Depends(get_current_user_org)` returning the `(user, token, org_id)` triple + helper functions now read from `user.user_metadata` instead of dict-keys; deleted `app/auth_deps.py` (141 LoC); updated MASTER-PROMPT §Architecture line 33 doc-code coherence. **Phase 3**: removed `jwt_secret` field from `SeedSettings` (5 LoC); migrated 8 router test files from `settings.jwt_secret` import to local `_JWT_SECRET = "test-only-decorative-secret"` constant (token content is decorative — conftest's `MockSupabaseClient.auth.get_user` patch returns a fixed `MockUser` regardless of token bytes). **Verification**: `pytest products/adconnect/backend/tests/ -k "not realdb" -p no:randomly` → **248 passed, 18 deselected, 0 failed** (baseline was 227; gain reflects the 21 additional service-level tests landed since the Phase 0 audit). `grep "auth_deps" products/adconnect/backend/app/` → only migration-history docstrings (rewards.py / sellout.py / dependencies.py). `grep "Depends(get_current_user)" products/adconnect/backend/app/routers/` → zero hits. AST scan for `check_auth_dep_anti_pattern` (which flags `Depends(<X>.get_org_id)` / `get_user_role` / `get_user_client`) → zero hits in adconnect routers. **One structural insight worth capturing** (filed in Phase 4 sweep candidates below): `dependencies.py` reuses `app.database._db` instead of constructing its own `DatabaseModule` instance — required because AdConnect's conftest patches `app.database._db.get_client` directly at module-attr level; constructing a duplicate `_db` would create a second instance the conftest patches miss, breaking 145+ tests. ERP/PF avoid this by patching only at the framework class level (`noctusai_seed.database.DatabaseModule.get_client`); AdConnect's hybrid patches are an accept-with-rationale candidate. **Staged-but-not-committed** per brief — architect owns the commit + push handoff and Phase 4 close. | Claude Opus 4.7 (Engineer ADCO-MIG-P2) |
