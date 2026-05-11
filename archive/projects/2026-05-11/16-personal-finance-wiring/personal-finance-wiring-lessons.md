# personal-finance-wiring — Lessons learned

Distilled from Phases 0-7 (2026-05-03 → 2026-05-11). Intended for the parent
`products-wiring-rollout` to fold into the ERP plan before ERP starts. Aim:
top 5-7 actionable lessons. Slips + raw findings live in `findings.md` next
to this file.

## (a) What worked

1. **Phase 0 as the load-bearing phase.** A near-clean gap inventory (0
   path / 0 verb / 0 404 / 7 orphans / 1 systemic DTO drift) — produced by
   actually opening each hook + each router and joining the two lists — let
   the rest of the project execute almost entirely against §5.2.3 rows
   rather than re-discovery. Pure audit, no code edits, ~1 session. The
   payoff compounds across every later phase: each phase opened §5.2.3 and
   had a row-driven sub-task list. **For ERP: budget a full session for
   Phase 0; do NOT try to overlap audit + first fix batch.**

2. **Branching-first orchestration with same-shape parallel batches.**
   Phases 2 + 3 + 4 + 5 all dispatched as same-day same-shape engineers
   in isolated worktrees (`worktree-agent-*`), each touching disjoint
   files. Wall-clock parallel hit ≈4× serial estimate. The architect-only
   orchestration discipline (engineers never plan) kept dispatched briefs
   focused — every brief was ≤ 200 LoC scope, every brief had a single
   verification gate, every brief surfaced cross-product follow-ups
   without expanding scope.

3. **Verify-the-seed-ships-it test fired at Phase 1.** Phase 1's
   "absorption" sweep planned `make_get_current_user_org` + AI-plumbing
   wrappers + Metas absorption as inline fixes; reading the seed
   `__init__.py` exports showed the helpers did NOT ship. Standalone-mode
   dispatch could not touch seed, so all three landed as deferred-with-
   destination follow-up projects rather than consumer-side forks. **This
   is the test working as designed.** The slip would have been: "the seed
   has Protocol X, so we can do Y" — without verifying X actually exposes
   a Real adapter.

4. **Worktree base verification (§16.7) + push-first directive
   structurally closed the worktree-base gap.** Every engineer brief
   contained the §16.7 preamble; engineers pushed branches; orchestrator
   FF-merged at fresh-eyes-review. **No re-work surfaced from agents
   editing the wrong base** — a regression-free statistic on a known
   slip class.

## (b) What to redo

1. **Set up `scripts/bootstrap-worktree.sh` BEFORE Phase 0, not during
   Phase 5.** Three engineers in Phases 3 + 5 + 6 hit the "three-install
   dance" (root npm + product frontend npm + seed/framework npm). The
   bootstrap script eventually closed the gap but cost ≈ 15-20 min per
   engineer over Phases 3-6. **For ERP: dispatch a one-engineer "worktree
   bootstrap calibration" in pre-Phase-0 if the script doesn't already
   handle ERP's frontend + node_modules surface.**

2. **Catch consumer-existence at Phase 0 audit, not at Phase 5
   wiring-time.** Phase 5's `StaleBadge` component shipped ready-to-wire,
   but Phase 0 verified `useCotacao` → `/api/cotacoes/{ticker}` route
   alignment WITHOUT verifying any page actually calls `useCotacao` (zero
   call-sites). The cross-product symmetry rule fires at READ/PLAN time
   per the methodology. **For ERP Phase 0: extend §5.2.3 with a "consumer
   count" column — hooks with 0 page consumers get flagged as
   `Pattern H: orphaned-hook` and routed to deletion-or-wire decision at
   Phase 0, not at Phase 5.**

3. **Status-code-assertion rule needs a Phase 0 calibration pass.** Phase
   2 + 3 + 5 + 7 each surfaced tests asserting on `.json()` / `.text`
   without an accompanying `.status_code` assertion. Fixed each instance
   inline, but the rule's enforcement was reactive across 4 phases. **For
   ERP: run `noctus.dev.scan_block_patterns mode=status_assertion` over
   the existing ERP test corpus in Phase 0; produce an inventory of
   violations; either fix in Phase 0 OR pin as "TIER B" baseline-no-
   regress before any new tests land.**

## (c) Seed-lib reuse hit rate

| Surface | Result | Notes |
|---|---|---|
| `noctusai_lib.api.responses` (`success_response`, `paginated_response`, `ok_response`) | **100% reuse** | All PF routers use these wrappers; no per-product variants. |
| `noctusai_lib.api.auth.delete_or_404` | **N=3 adopted** | Phase 2 (transacoes/orcamentos/recorrentes) — single canonical pre-check pattern. Seed already shipped real adapter; no follow-up needed. |
| `noctusai_lib.testing.MockSupabaseClient/AuthClient` | **100% reuse** | Per-product conftest builds on these; deep-copy fix at the seed (separately) closed PF's only Phase 2 false-failure. |
| `noctusai_lib.api.auth.make_get_current_user_org` | **NOT SHIPPED** | Filed `proposals/phase-1-seed-absorption-followups.md` → future `make-get-current-user-org-factory` project. PF + ERP N=2 today; therapy adds N=3. |
| `noctusai_lib.domain.ai.*` (P1 indicator + feedback) | **100% reuse** for `persist_output`; **DEFERRED** for `safe_persist_indicator` / `require_credential_or_422` (N=2 PF+ERP) | Phase 1 surfaced the gap. |
| `noctusai_lib.domain.metas.*` (Goal/Progress/period_bounds) | **NOT YET ADOPTED** by PF (lifted but PF still on local copies) | N=3 MUST-FORMALIZE per recurrence rule; filed as follow-up `metas-domain-seed-absorption` project. |
| `noctusai_seed` standard routers (`health`, `notificacoes`, `team`, `ai_outputs`, `ai_feedback`) | **5/5 mounted** | Standard-router smoke tests added Phase 7 to pin contracts. |
| `seed scheduler` standard router | **NOT SHIPPED** | Filed `proposals/phase-5-scheduler-standard-router.md`; N=3 likely adopters (PF + mailing + therapy). |

**Net seed-lib hit rate (intent-vs-shipped)**: ≈ 60% of the absorption
candidates surfaced in Phase 0 actually consumed the seed during PF
phases; the remainder are filed as follow-up projects. **The follow-up
projects are the right outcome** — verify-the-seed-ships-it kept consumer-
side forks from accumulating.

## (d) Test pattern recurrences

1. **`vi.importActual` on barrel modules trips UMD resolution.** N=4
   across Phase 6 tests (Login, ForgotPassword, AcceptInvite, Equipe).
   Fix: stub only the named export consumed by the SUT; drop
   `importActual` entirely. **For ERP: pre-document this fix in the
   first ERP frontend test brief; flip to `__test_helpers__/stubDesignSystem.ts`
   at first recurrence (N=5+).**

2. **`vi.hoisted` is required when stubbing modules with closure-
   captured spies.** Equipe.test.tsx hit this once; pattern is in vitest
   docs but easy to miss. **Add to `KB § PATTERNS/testing.md` § Frontend
   stubbing — vi.mock hoisting**.

3. **Test fixture deep-copy at the seed.** A 4F→0F therapy regression
   (2026-05-11) traced to module-level fixture mutation across tests.
   Fixed at the seed via `MockRequestBuilder.__init__` deep-copying
   `_data`. PF benefited automatically. **The mock-supabase-deep-copy
   memory entry captures the diagnostic recipe** (2-second `pytest
   <single-test>` classifies pollution vs genuine bug).

4. **Standard-router mount-smoke per product.** Phase 7 surfaced the
   gap: `ai_outputs`, `ai_feedback`, `health` had zero per-product
   smoke tests in PF (seed-tested, but PF's mount-shape unverified).
   3 tiny smoke tests landed (5 functions; 2 per router with status +
   body assertion). **For ERP: dispatch the same 5-test pattern at ERP
   Phase 7 — trivial cost, high signal for future seed-side regressions.**

## (e) Cross-product lift candidates surfaced by PF

| Candidate | Recurrence | Destination |
|---|---|---|
| `make_get_current_user_org` factory | PF + ERP (N=2); ERP-imobi likely N=3 | `make-get-current-user-org-factory` project (filed) |
| AI-plumbing wrappers (`_persist_indicator`, `_require_openai`, `check_openai_configured`) | PF + ERP (N=2 byte-identical modulo `schema=` + rate-limit decorator) | `ai-plumbing-seed-absorption` project (filed) |
| Metas-domain absorption (`Goal/Period/Progress` + `compute_progress` + `accumulate_contribution`) | PF + ERP + daily-life (N=3 MUST-FORMALIZE) | `metas-domain-seed-absorption` project (filed); now shipped at `noctusai_lib.domain.metas` per KB pointer |
| `scheduler` standard router (last-run / next-run / executar) | PF + mailing + therapy (N=3 likely) | `phase-5-scheduler-standard-router` proposal |
| Cross-schema `db.table("organizations")` reach (the PF-8 slip) | PF + ERP + therapy + daily-life (N=4 monthly-narrative-shaped services) | `cross-schema-organization-reach-audit` follow-up project (filed Phase 4) |
| DELETE false-404 via `delete().execute() + if not result.data:` | PF (3) + ERP (`meta_periodos_service` + `regras_pontuacao_service`) = N=5 cross-product | `delete-precheck-seed-lift` formalized — seed `delete_or_404` ships and PF Phase 2 adopted; ERP sister fixes pending |
| `<StaleBadge>` + `computeStaleness` decision fn | PF only today (N=1) | Defer to seed when ERP / therapy asset-pricing consumer surfaces (N=2+) |
| `ultima_execucao` scheduler-history column | PF + mailing + therapy (cross-product if schedulers want history) | Captured for scheduler-standard-router design |

**Key insight for ERP**: ERP runs SECOND in the master rollout. **Half
the absorption candidates above will fire at ERP Phase 0 as N=2 promotes
to N=3, automatically flipping accept → formalize.** The orchestrator
should pre-stage the follow-up projects so ERP Phase 0's recurrence-rule
checks have a destination ready, not a "TBD" placeholder.
