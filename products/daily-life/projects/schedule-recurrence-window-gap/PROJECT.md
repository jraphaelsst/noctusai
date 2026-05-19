# Schedule Recurrence Window Gap — Project Document

> Living document. Interrogate the user before drafting/revising; capture Q→A in §2. Written for a zero-context reader. Symbol-first per `KB § PATTERNS/doc-symbology.md` (phase icons `✅ ⏳ ❌ 🔒 🅿️`; triage `[F]/[R]/[A]`; `N≥3 ⇒ MUST formalize`).

- **Created:** 2026-05-18
- **Last updated:** 2026-05-18
- **Status:** Phase 0 ✅ — Q1/Q2 decided (§2), §3a audit `[A]` (no seed-lift); **P1/P2 unblocked, awaiting user "continue"** (phase-by-phase cadence)
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Related docs:** `products/daily-life/backend/app/routers/schedule.py` · `…/app/services/schedule_service.py` · fix commit `48309a00` (recurring-events expansion) · `KB § PATTERNS/project-execution.md §2.13` (in-flight-resolution / surfaced-needs-a-decision)
- **Project slug:** `schedule-recurrence-window-gap` (subject `schedule-recurrence-window`, intent `gap`; single-product → `products/daily-life/projects/`)

---

## 1. Context & Purpose

`GET /api/schedule` (daily-life) now expands recurring events into occurrences — `expandir_recorrencias` was imported-but-never-called; wired + regression-tested in commit `48309a00` (37 schedule tests pass). While fixing it, two further correctness/semantic gaps were found and **deliberately surfaced rather than silently changed** (no-silent-errors: a silent semantic change risks regressing existing callers). This project captures them as a tracked destination so they are resolved by decision, not lost:

1. **Window-filter excludes recurring parents that started before the window.** `listar_eventos` filters `data_inicio` with `gte(data_inicio)` ∧ `lte(data_fim)` — both on the *start* field. A weekly/daily event that began before the requested `data_inicio` but recurs *into* the window is never fetched, so its in-window occurrences are never generated even though expansion is now wired.
2. **Expand-vs-paginate count mismatch.** Expansion runs *after* DB pagination (`.range(offset, offset+page_size-1)`); `paginated_response(_eventos, result.count, …)` returns `count` = parent-row count while the body may hold more (expanded) rows. Pagination over occurrences is undefined.

The win: recurring events return their true in-window occurrences with a defined pagination contract, both test-pinned.

---

## 2. Confirmed constraints

- **The expansion bug itself is already fixed ∧ shipped** — `48309a00` on `main`; this project is ONLY the two residual semantics. *(Rules out re-doing the wiring; scope is the filter + pagination model.)*
- **Surfaced, not silently changed** — the Explore-suggested `data_inicio→data_fim` line-79 swap was NOT applied: `gte/lte` both on `data_inicio` is a coherent "starts-in-window" filter; changing it is a product-semantic decision. *(Drives §7 Q1 — needs the intended behavior before any code.)*
- **`data_fim` is nullable** — all-day / open-ended events store `data_fim = NULL` (see `schedule.py` create path). *(Any overlap-filter must handle NULL or it silently drops all-day events.)*
- **User directive, verbatim** (2026-05-18): *"do it, then file the follow-up"*, then *"decide Q1 and Q2, then run its Phase 0"* — user delegated the Q1/Q2 decisions to the architect (decide + record rationale, don't re-ask).
- **Q1 DECIDED (window-filter semantic)** — **recurrence-aware lower-bound drop**: for rows with `recorrencia ∉ {nenhuma, NULL}` do NOT apply the `gte("data_inicio", data_inicio)` lower bound (so pre-window recurring parents are fetched, then window-clipped by `expandir_recorrencias`); non-recurring rows keep `gte`+`lte` unchanged. *(Minimal · zero-regression to non-recurring listing · NULL-`data_fim`-safe (filter stays on `data_inicio`) · the expansion service already clips occurrences to `[inicio,fim]` so an earlier-starting recurring parent cannot flood. Rejected full-overlap-on-`data_fim` — NULL-handling complexity + would alter non-recurring semantics = the very regression risk that drove the original defer.)*
- **Q2 DECIDED (pagination contract)** — `count` = **parent-row count**; expanded occurrences are derived, NOT separately paginated; documented at the call site + asserted by a test. *(Low-risk, matches current shape, no pagination redesign. Rejected expand-then-paginate for this project — correct long-term but a larger occurrence-cursor redesign = scope-creep; recorded as a named future follow-up `schedule-occurrence-pagination` if true occurrence-paging is later wanted.)*
- **§3a/Q3 audit RESOLVED — `[A]` accept-with-rationale** — recurrence-expansion is domain-divergent across daily-life (calendar window-expand) / erp `recorrencia_service` (financial rent-row generation, persists) / PF `recorrentes_service` (financial-transaction recurrence); even the period vocabularies differ (daily-life `diario/semanal/mensal/anual` vs PF `semanal/quinzenal/mensal/bimestral/…`). No `N≥3` *unifiable* contract → a forced seed-lift would be a wrong abstraction. Recurrence rule does NOT fire `[F]`. Cataloged in `KB § PATTERNS/accept-with-rationale.md`. *(Note: the broad cross-product scan also surfaced general platform-wide helper duplication — `audit_hook` `_get_engine_and_factory`/`_noop_writer` ×5 etc. — that is **pre-existing, out of THIS project's scope**; destination = the standing absorption queue, NOT actioned here, not silent.)*

---

## 3. Design principles

1. **No silent semantic change** — the filter/pagination behavior is decided WITH the user (§7), then implemented; never guessed.
2. **Regression-test-first** — the original bug shipped because no endpoint test exercised expansion. Every change here lands with a test that would have caught its absence.
3. **AST-first** edits (libcst), per CLAUDE.md §1.
4. **Right-layer fix** — §3a decides product-local vs seed; recurrence rule (`N≥3 ⇒ MUST formalize`) applies if cross-product duplication is found.

---

## 3a. Seed-first analysis (REQUIRED)

Six-question checklist (`KB § GUIDES/seed-first-design.md`):

1. **Contract identical for every product?** ¬ clear — recurrence-expansion exists product-locally in several places with *different domains*: daily-life `schedule_service.expandir_recorrencias` (calendar), erp `recorrencia_service` (financial), PF `recorrentes_service` (financial), therapy `recurring.py` (sessions). Same *idea*, different semantics/data.
2. **Data source product-specific?** YES — `eventos` table is daily-life-local.
3. **Placement product-specific?** YES — the defect is in daily-life's `schedule.py` router + its local service.
4. **Visibility/permission rule same?** N/A (same per-user RLS, not the concern).
5. **Seam already in seed?** PARTIAL — `noctusai_lib.domain.scheduling` exists but is an *appointment-scheduling* primitive (conflict/scorer/travel), **not** a calendar-recurrence-window-expansion primitive. No existing seed seam for "expand recurrence within a window + paginate."
6. **Default-on / opt-in?** N/A.

**Litmus — per-product code count:** the immediate fix is **a small product-specific section** in daily-life's router/service (correctly product-bounded). **BUT** P0 MUST run the absorption-scan sextet (`scan_cross_product_helpers` + `scan_within_product_helpers`) to test whether windowed recurrence-expansion is duplicated `N≥3` across daily-life/erp/PF/therapy with a unifiable contract — if so, recurrence rule fires ⇒ a seed primitive (`noctusai_lib.domain.scheduling.recurrence`) is the `[F]` destination and a seed phase is added. **Phase-plan implication:** §6 phases work in the daily-life product (correct) for the fix; the P0 audit gates whether an additional *seed* phase is warranted — §6 does NOT walk products one-by-one.

---

## 4. Scope

**In scope:**
- Decide (Q1) + implement the window-filter so recurring parents starting before the window still yield in-window occurrences; NULL-`data_fim` safe.
- Decide (Q2) + implement the expand-vs-paginate count contract.
- Regression tests for both (endpoint-level).
- P0 cross-product recurrence-expansion absorption-scan; route the outcome.

**Out of scope (with reason):**
- Redesigning the scheduling/recurrence engine — too broad; this is a bounded correctness gap.
- Cross-product seed lift — only if the P0 scan shows `N≥3` unifiable duplication (then it becomes the `[F]` destination, not pre-decided here).
- erp/PF financial-recurrence + therapy session-recurrence — different domains; out unless P0 proves a shared contract.

---

## 5. Architecture / Data Model

- `products/daily-life/backend/app/routers/schedule.py` — `listar_eventos`: the `query.gte("data_inicio", data_inicio)` / `query.lte("data_inicio", data_fim)` filter (~L92-95 post-fix) + the `_eventos = expandir_recorrencias(result.data or [], _as_date(data_inicio), _as_date(data_fim))` call (~L101) + `paginated_response(_eventos, result.count or 0, …)` (~L102).
- `products/daily-life/backend/app/services/schedule_service.py` — `expandir_recorrencias(events, inicio, fim)` (window defaults today-30 … today+90); `recorrencia` ∈ {`nenhuma`/None pass-through, `diario`, `semanal`, `mensal`, `anual`}; `recorrencia_fim` honored; occurrences carry `is_recorrencia` + `evento_pai_id`.
- Tests: `products/daily-life/backend/tests/routers/test_schedule_router.py` (`test_list_events_expands_recurring` is the existing pin) + `tests/services/test_schedule_service.py` (isolated expansion contract — 7-for-daily over a 7-day window).
- Test runner: seed framework on path — `PYTHONPATH=seed/framework/backend:seed/lib/backend:<backend>` (no product-local `.venv`).

---

## 6. Implementation phases

### Phase 0 — Audit + decisions ✅ (user-delegated Q1/Q2; audit `[A]`)
- [x] Q1 (window-filter semantic) ∧ Q2 (pagination model) decided + recorded in §2 (user delegated the decision to the architect — recorded with rejected-alternatives rationale).
- [x] Absorption audit across daily-life/erp/PF/therapy recurrence-expansion — domain-divergent, no `N≥3` unifiable contract → triage `[A]` (no seed phase added); §11 + accept-with-rationale catalog.
- [x] `data_fim` NULL-distribution confirmed: all-day / open-ended events store `data_fim = NULL` (`schedule.py:47,61`); the Q1 filter stays on `data_inicio` only ⇒ NULL-safe by construction.

**Improvements:**
- The original defect (imported-but-uncalled `expandir_recorrencias`) is a class — a keeper could flag "module-level import used nowhere in the file" for router/service modules. Deferred → standing absorption/keeper queue (out of this project's bounded scope; named, not silent).
- `expandir_recorrencias` default window (today−30 … today+90) silently caps an unbounded query; acceptable but the cap should be explicit/asserted when P1 changes the fetch — captured for P1.
*Phase proposal:* none filed — Phase 0 is decisions+audit; the two improvement bullets are deferred-with-destination (above), no bundle warranted.

### Phase 1 — Window-filter fix (recurring parents not excluded)
- [ ] Implement the Q1-decided filter (libcst). *Recommendation pending decision:* for rows with `recorrencia ∉ {nenhuma, NULL}` do **not** apply the `gte("data_inicio", data_inicio)` lower bound (or fetch by `recorrencia_fim`-overlap), so pre-window recurring parents are fetched ∧ expanded; non-recurring rows keep current behavior.
- [ ] Endpoint regression test: a weekly event starting *before* the window returns its in-window occurrences (would fail pre-fix).

### Phase 2 — Expand-vs-paginate count contract
- [ ] Implement the Q2-decided model. *Recommendation pending decision:* short-term — document `count` = parent-count (occurrences derived, not paginated) + assert it in a test; long-term option — expand-then-paginate (bigger change, note as follow-up if not chosen).
- [ ] Test pinning the chosen pagination contract.

### Phase 3 — Verify + route
- [ ] Full daily-life schedule suite green (`tests/routers/test_schedule_router.py` + `tests/services/test_schedule_service.py`).
- [ ] §3a audit outcome routed (seed `[F]` follow-up filed if `N≥3`, else `[A]` recorded).

---

## 7. Open questions

1. ✅ **RESOLVED (Phase 0, §2)** — window-filter semantic = recurrence-aware lower-bound drop. P1 unblocked.
2. ✅ **RESOLVED (Phase 0, §2)** — pagination contract = `count` = parent-row count, occurrences derived/not separately paginated. P2 unblocked. Larger occurrence-pagination = named future follow-up `schedule-occurrence-pagination` (not this project).
3. ✅ **RESOLVED (Phase 0 audit, §2)** — `[A]` accept-with-rationale; recurrence-expansion domain-divergent, no `N≥3` unifiable contract, no seed-lift. Cataloged in `KB § PATTERNS/accept-with-rationale.md`.

---

## 8. Dependencies & blockers

- **Q1 + Q2 answers** — gate P1 ∧ P2 respectively (this project does not execute until Phase 0 resolves them).
- **P0 absorption-scan evidence** — gates whether a seed phase is added (§3a).

---

## 9. Success criteria

- A recurring event starting before the requested window returns its in-window occurrences via `GET /api/schedule` — endpoint-test-pinned (fails on the pre-fix filter).
- The pagination contract for expanded results is defined ∧ asserted by a test.
- daily-life schedule suite fully green; no regression to non-recurring listing.
- §3a cross-product audit outcome recorded in §11 with an explicit `[F]/[R]/[A]` triage.

---

## 10. How to use this plan

- Single source of truth for progress; live-tick `- [ ]` → `- [x]`.
- Phase-by-phase by default; **Phase 0 is interrogation — do not implement P1/P2 before Q1/Q2 are answered in §2**.
- Commit plan changes with the code; one bundled proposal per phase per `KB § PATTERNS/proposals-and-improvements.md`.
- Interrogate before designing; capture Q→A in §2.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-18 | Filed as the §2.13 deferred-with-destination for two needs-a-decision items surfaced while fixing the recurring-events expansion bug (`48309a00`). NOT executing — Phase 0 interrogation gates P1/P2. User-directed ("do it, then file the follow-up"). | Claude Opus 4.7 (1M context) |
| 2026-05-18 | **Phase 0 ✅** (user-directed "decide Q1 and Q2, then run its Phase 0"). Q1 = recurrence-aware lower-bound drop; Q2 = `count`=parent-count (occurrence-paging → named future follow-up); both rationale+rejected-alternatives in §2. §3a absorption audit: recurrence-expansion domain-divergent across daily-life/erp/PF (divergent period vocabularies, in-memory-clip vs persist-rows) → triage **`[A]`**, no `N≥3` unifiable contract, no seed phase; cataloged in `KB § PATTERNS/accept-with-rationale.md`. `data_fim` NULL-safe confirmed. P1/P2 unblocked; paused per phase-by-phase cadence. Out-of-scope platform helper-duplication noted (standing absorption queue, not actioned here). | Claude Opus 4.7 (1M context) |
