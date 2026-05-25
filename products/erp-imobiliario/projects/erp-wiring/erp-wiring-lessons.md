# erp-wiring — Lessons learned

Synthesized from Phases 0–7 (2026-05-11 → 2026-05-20). Inherits the
`personal-finance-wiring-lessons.md` template from the PF retro (archived
at `archive/projects/2026-05-11/16-personal-finance-wiring/`). Intended as
pre-reading for the next wiring dispatch (therapy-platform-wiring Phase N+1
and any follow-on product wiring). Raw phase notes live in §11 of
`products/erp-imobiliario/projects/erp-wiring/PROJECT.md`.

---

## (a) What worked

1. **PF retro as a force-multiplier.** The Phase 0 audit opened the PF
   lessons doc FIRST and wired every ERP gap-table column to a PF lesson.
   Pattern H (orphaned hooks), status-code-assertion calibration, and the
   seed-candidate recurrence table all arrived at Phase 0 as pre-existing
   instruments rather than mid-flight discoveries. Net: Phase 0 closed
   complete (§5.4.1–§5.4.9) in a single session, setting the "row-driven
   execution" shape that held through all 7 subsequent phases.

2. **Phase 0 as the load-bearing phase — confirmed at ERP scale.** ERP is
   the platform's largest product (60 routers / 321 endpoints / 65 hooks /
   67 pages / 29 migrations). Every subsequent phase opened a §5.4 row and
   had zero re-discovery overhead. **For the next wiring product (any):
   invest the full first session in Phase 0. Do not overlap audit + first
   fix batch.**

3. **Deferred-item batching via [DEFERRED-TO-P3] inline markers.** Phases 1
   and 2 explicitly tagged skipped items with `[DEFERRED-TO-P3]` rather
   than silently shrinking scope. Phase 3 consumed exactly the tagged set.
   No work fell through the floor. The marker shape predates the
   `NOC-REMEDIATE` convention — both serve the same "named destination"
   contract.

4. **Libcst codemod for 300-callsite Phase 1 migration.** The
   `make_get_current_user_org` adoption at 300 callsites (Phase 1) ran via
   libcst, not grep-replace. Zero false positives. Equivalent sed-on-source
   would have broken multi-line decorator forms invisible to line-level
   regex. AST-first proved its value at production callsite volume here.

5. **Token-leak defense via `<entity>_row_to_dto` mapper pattern.** Phase 3b
   introduced a module-level mapper co-located in each
   `app/services/<domain>_service.py`. Phase 6 absorbed the same pattern
   onto `portal_externo` at N=2 without re-engineering. Mapper functions are
   trivially testable and enforce the DTO whitelist at the HTTP boundary.
   **This is the absorption shape for `erp-imobiliario-dto-contract` Phase 1.**

6. **Phase-5 §5.4.3a densification as a durable audit artifact.** The
   corretor-surface per-hook map (40+ exports ↔ 39+ router decorators,
   zero gaps) landed as a checked-in subsection of PROJECT.md rather than
   a transient agent note. Phase 8 verification consumed it directly. Any
   future audit of the corretor surface reads §5.4.3a, not re-discovers.

7. **`make_require_role` + `get_erp_user_role` resolver pattern.** Phase 3
   retired both the bespoke `vista_showcase.require_admin` (21 LoC) and the
   `metas_digest` inline role check via a single `get_erp_user_role`
   resolver injected into the seed factory. The resolver centralises the
   SSO platform_admin → erp_role → noctus_role → "user" priority chain —
   the ERP-specific part — while the generic role-gate machinery lives in
   the seed. **This is the correct seam shape for the next product.**

---

## (b) What to redo

1. **`sys.path` half-fix compounded silently across 5 products.** The ERP
   conftest injected `seed/lib/backend` for `noctusai_lib` but NOT
   `seed/framework/backend` for `noctusai_seed`. After the 2026-05-16
   axis-swap renamed the framework path, every worktree-isolated pytest run
   against ERP (and 4 sibling products) exploded with
   `ModuleNotFoundError: No module named 'noctusai_seed'`. Fixed in Phase 7
   by injecting BOTH paths. **The follow-up `conftest-worktree-sys-path-fanout`
   project should close the N=5 footprint (PF, daily-life, adconnect, core,
   ERP) in one pass.** Root cause: no test asserted `noctusai_seed` importable
   from the product conftest.

2. **Standard-router smoke pattern arrived at Phase 7, not Phase 0.** The 30
   mount-smoke tests (6 routers × 5 slots) that landed in Phase 7 cost
   nothing — the pattern was already proven by PF. Their absence for 6
   phases meant the seed `llm_router` `deps._db.get_user_client()` arity
   gap (a runtime crash) would not have been caught earlier. **For future
   products: dispatch standard-router smoke as a Phase 1 sub-task. Cost =
   30 test stubs.**

3. **Phase ordering placed Phase 3b (DTO sweep) before Phase 4 (scaffolding
   debt).** Phase 3b established the mapper shape for 6 routers; Phase 4
   then extended it for `portal_cliente` admin listing. Logical, but Phase
   3b's token-leak defense on portal_cliente was effectively duplicated 2
   phases later for portal_externo. **Preferred order for next product:**
   Phase 3 = seed absorption; Phase 4 = portal/public surfaces (includes
   token-leak defense across ALL public surfaces in one pass); Phase 5+ =
   domain surfaces.**

4. **Bystander `tailwindcss-animate` PostCSS resolution failure in worktrees
   was surfaced but not fixed.** Phase 5 correctly diagnosed that `vite build`
   fails in worktrees via symlinked `node_modules` (PostCSS plugin
   `require.resolve` breaks through symlinks) while vitest works fine. The
   correct fix is a per-worktree `npm ci` in the product's `frontend/`
   before dispatching any engineer running `vite build`. **Add to
   `scripts/bootstrap-worktree.sh`:** `cd products/$SLUG/frontend && npm ci`.
   Tracked as a Phase 8 follow-up but not shipped; cost ≈ 2 min per worktree.

5. **LGPD flags filed at phase-end, not at Phase 0.** Phases 6 and 7 each
   filed batches of `noctus.dev.lgpd_flag` entries after the engineering
   work landed. The P0 flag (`portal_externo /documentos` lacking
   `compartilhado_portal=True` gate) was severity-appropriate but arrived
   at Phase 6 rather than being pre-staged at Phase 0 as a "will audit this
   surface" marker. **For next product: Phase 0 should produce a LGPD
   surface inventory (which routers touch PII, public-vs-auth tier) that
   phases can reference, mirroring the §5.4.2 Pattern inventory.**

---

## (c) Seed-lib reuse hit rate

| Surface | Result | Notes |
|---|---|---|
| `noctusai_lib.api.responses` | **100%** | All 321 routes use wrappers; 0 per-product variants |
| `noctusai_lib.api.crud_safety.delete_or_404` | **N=5 adopted** | Phase 1 (15 sites) + Phase 4 (4 stragglers); 6 legitimate non-canonical sites documented |
| `noctusai_lib.api.auth.make_get_current_user_org` | **100%** (300 callsites) | Shipped before ERP Phase 1; verify-the-seed-ships-it confirmed |
| `noctusai_lib.api.auth.make_require_role` | **Adopted** (Phase 3) | vista_showcase + metas_digest inline check retired |
| `noctusai_lib.api.auth.require_credential_or_422` | **Adopted** (Phase 3) | `_require_openai` delegates; `matching.py` inline checks retired |
| `noctusai_lib.domain.ai.outputs.safe_persist_indicator` | **Adopted** (Phase 2) | libcst codemod; 5 callsites; local helper retired |
| `noctusai_lib.domain.metas` | **Partial** (2 imports pre-existing) | Full retirement deferred; local copies coexist; N=2 adoption |
| `noctusai_lib.domain.digest.BaseDigestService` | **NOT adopted** | ERP metas digest has bespoke 3-tier VGV cascade; `[A]` in accept-with-rationale |
| `noctusai_seed` standard routers (health/notificacoes/team/llm/ai_outputs/ai_feedback) | **6/6 mounted** | 30 smoke tests landed Phase 7 |
| `noctusai_lib.integrations.vista` | **Adopted** (pre-project) | ERP showcase router already consumed the seed adapter |
| `noctusai_lib.integrations.whatsapp` | **Adopted** (pre-project) | WAHA send formalized in `erp-imobiliario-test-baseline-recovery` |
| `noctusai_lib.integrations.llm` | **Adopted** (pre-project) | |
| `scheduler` standard router | **NOT shipped** | Follow-up project filed |
| Pattern E `response_model` rollout | **NOT adopted** | Deferred to `erp-imobiliario-dto-contract` project; `[A]` |

**Net hit rate**: ≈ 75% of targeted absorption candidates landed in-project (higher than PF's 60%). The delta traces to three candidates that shipped at seed before ERP Phase 1 (`make_get_current_user_org`, `make_require_role`, `require_credential_or_422`).

---

## (d) Test pattern recurrences

1. **Mock-fixture missing predicate-column failures (N=9 in baseline-recovery).** The
   most common pre-existing failure shape in ERP: router issues
   `query.eq(col, default_value)` but the mock fixture row omits `col` →
   the mock `_eval_eq` returns `None != default_value` → row evicted →
   0-result list → assertion fails. Fix: mock rows must include every column
   the router filters on with its default-mode value. **Surfaced at Phase 5
   fix-on-contact (`arquivado=False` predicate); N=9 drained by
   `erp-imobiliario-test-baseline-recovery`.** Detection candidate:
   `noctus.dev.scan_mock_predicate_skew` (proposed by Engineer G; N=1 in
   ERP now drained → defer Stage-4 until N=2 across products).

2. **Test fixture `_stub_persist` / `_bypass_openai_check` patch-target
   drift.** Both fixtures originally patched in-product symbols
   (`app.routers.ai.persist_output`, `app.routers.ai.check_openai_configured`,
   `app.routers.matching.check_openai_configured`). Phases 2 and 3 migrated
   the production code to seed surfaces, making the old patch targets
   unimportable. Both fixtures were lifted to patch the canonical seed
   external-boundary surface (`noctusai_lib.domain.ai.outputs.persist_output`,
   `noctusai_lib.config.credentials.resolve_credential`). **Pattern: when
   migrating production code from in-product to seed-lib, simultaneously
   migrate all `patch(...)` call-sites pointing at the old symbol.**

3. **Standard-router mount smoke (N=30 at ERP Phase 7).** PF added 3 smoke
   tests; ERP dispatched 30 (6 routers × 5 slots). The 5-slot shape
   (route-exists / auth-gate / happy-path / isolation / contract) is stable.
   **Seed-test-suite candidate `noctusai_lib.testing.framework_test_suites.StandardRouterMountSmoke`
   at N=3 (therapy/daily-life adoption gates the formalization).**

4. **`llm` smoke needed a boot-time mock seam.** The `llm` standard-router
   smoke hit `configure_credentials(url="")` leaving the public Supabase
   client uninitialized; `resolve_credential` then tried to materialize a
   real client. Workaround: `patch("noctusai_lib.config.credentials._get_public_client",
   return_value=mock_sb)` — external-boundary shape. **Root cause is a seed
   bug: `llm_router.obter_preferences` calls `deps._db.get_user_client()`
   which `DatabaseModule` does not expose (arity gap). Filed as seed-side
   follow-up.**

---

## (e) Cross-product lift candidates surfaced by ERP

| Candidate | Recurrence | Destination |
|---|---|---|
| `StandardRouterMountSmoke` test-suite base | ERP N=2 (PF + ERP) → N=3 at therapy/daily-life | Seed when N=3 adoption confirmed |
| Worktree `conftest.py` `sys.path` double-inject (lib + framework) | N=5 (PF + ERP + daily-life + adconnect + core) | `conftest-worktree-sys-path-fanout` project |
| `erp-financial-surfaces-role-gate` convention (reads gated + audit-logged) | N=4 within ERP (financeiro / dimob / impostos / banco) | `erp-financial-surfaces-role-gate` follow-up project |
| `portal_dto_whitelist` seed primitive (token-leak defense across portal surfaces) | N=2 (portal_cliente + portal_externo) | Seed when N=3 consumer surfaces |
| `<entity>_row_to_dto` mapper pattern (Phase 3b) | N=7 within ERP (53 remaining routers) | `erp-imobiliario-dto-contract` follow-up project |
| LGPD Phase 0 surface inventory | 0 products doing it proactively | Methodology: file issue for next wiring product brief |
| `noctusai_lib.domain.metas` full retirement in ERP | N=2 partial adoption (2 imports) | Resume in `erp-imobiliario-dto-contract` or standalone project |
| `llm_router.obter_preferences` `deps._db.get_user_client()` arity gap | N=1 (seed bug) | Seed-side bugfix follow-up |
| Per-worktree `npm ci` for FE products (tailwindcss-animate PostCSS) | N=1 surfaced (worktrees systemically) | `scripts/bootstrap-worktree.sh` extension |

---

## (f) Methodology deltas vs PF retro

Items where ERP execution diverged from or extended PF lessons:

- **DTO mapper pattern new** — PF deferred all DTO work; ERP Phase 3b
  established the mapper shape and Phase 6 absorbed it. The `[A]`
  accept-with-rationale for 53 remaining routers is the correct landing
  (follow-up project gates formalization).

- **Portal-surface token-leak defense new** — portal_cliente (Phase 3b)
  → portal_externo (Phase 6) N=2 absorption executed cleanly. PF had no
  portal surfaces.

- **vista_showcase SSO Path-1 gap** — ERP's Phase 7 added 3 gap tests
  for `org_role in (owner, admin)` (Path 1 of `resolve_sso_role`). PF
  didn't have a bespoke admin gate. **For future products: when adopting
  `make_require_role` + an SSO-aware resolver, pin BOTH Path-1 and Path-2
  in tests.**

- **Financial-surfaces N=4 DRY** — ERP surfaced 4 routers with byte-
  identical write-audit-logged / read-NOT-gated gap. Filed as
  `erp-financial-surfaces-role-gate`. **Pattern to watch in other
  products: any product with a financial/fiscal ledger that uses
  `log_action()` on writes should be audited for symmetric read gating.**

- **Worktree sys.path fix-on-contact** — ERP Phase 7 fixed the ERP
  conftest in-flight; the N=5 cross-product fanout is a named follow-up.
  PF did not surface this because the axis-swap happened AFTER PF closed.
  **Going forward: every new product conftest should inject BOTH
  `seed/lib/backend` AND `seed/framework/backend` from day one.**
