# Proposal: pf-metas-seed-wiring end-of-project bundle

**Agent:** claude-opus-4-7 (engineer-A; Batch 1C of `in-flight-execution-rollout` master tree — sister projects: `erp-metas-seed-wiring`, `daily-life-goals-seed-wiring`)
**Origin:** project:pf-metas-seed-wiring:phase-3
**Generated:** 2026-05-04
**Severity:** medium
**Effort:** small
**Affected products:** personal-finance (this project), seed-lib (drive-by methodology fix surfaced — not landed in this project)
**Status:** pending

---

## 1. Context

`projects/pf-metas-seed-wiring/` shipped the PF consumer-side wiring of `noctusai_lib.domain.metas` (the seed module that `projects/metas-domain-seed-absorption/` lifted on 2026-05-03 from PF + ERP + Daily Life per N=3 MUST-FORMALIZE).

PF's `MetasService` (3 methods), `DashboardService.resumo()`, and `OrcamentosService.obter_progresso()` now consume seed `compute_progress` / `accumulate_contribution` / `project_completion_date`. The inline `from dateutil.relativedelta import relativedelta` import inside `metas_service.obter_progresso` was dropped (the seed uses stdlib `_add_months`). All math + state-transition logic now lives in `seed/lib/backend/noctusai_lib/domain/metas/`; PF retains schema, persistence (Supabase + RLS), PT-BR status vocabulary, and HTTP boundary.

**Test counts:**
- PF backend pytest: 26 (target services) → 26 passed; 584 (full backend, excluding `realdb`) → 584 passed.
- Seed-lib pytest: 660 passed.

**Code surface change (after refactor):**
- `metas_service.py` listar/adicionar_contribuicao/obter_progresso bodies replaced via libcst codemod.
- `dashboard_service.py` resumo()'s metas-percentual loop replaced.
- `orcamentos_service.py` obter_progresso()'s percentual_usado calc replaced.
- `metas_service.py`: dropped inline `dateutil.relativedelta` import + trimmed `from datetime import date, datetime` to `from datetime import date`.
- PF tests/conftest.py: prepended worktree-aware seed-lib shadow purge (drive-by methodology fix; see §2.4).

---

## 2. Bundled improvements

### 2.1 Duplications absorbed (before/after counts)

**`MetasService.listar` percent calculation** (1 site → 0 sites; replaced by 3-line seed call):

```diff
- meta["percentual"] = min((valor_atual / valor_alvo * 100) if valor_alvo > 0 else 0, 100)
+ progress = compute_progress(target=Target(valor_alvo), current=valor_atual)
+ meta["percentual"] = progress.percent_complete
```

**`MetasService.adicionar_contribuicao` accumulation + status flip** (1 site → 0 sites):

```diff
- novo_valor = float(meta.get("valor_atual", 0)) + float(data.get("valor", 0))
- update_data = {"valor_atual": novo_valor}
- if novo_valor >= float(meta.get("valor_alvo", 0)):
-     update_data["status"] = "concluida"
+ transition = accumulate_contribution(target=..., current=..., increment=...)
+ update_data = {"valor_atual": transition.new_current}
+ if transition.completed:
+     update_data["status"] = "concluida"
```

**`MetasService.obter_progresso` ETA + percent + remaining** (1 site → 0 sites; biggest absorption — 16 LOC replaced by seed `compute_progress(...)` call):

```diff
- valor_alvo = float(meta.get("valor_alvo", 1))
- valor_atual = float(meta.get("valor_atual", 0))
- percentual = min((valor_atual / valor_alvo * 100) if valor_alvo > 0 else 0, 100)
- data_previsao = None
- if contribs and valor_atual < valor_alvo:
-     total_contrib = sum(...)
-     meses_com_contrib = len(set(...))
-     if meses_com_contrib > 0:
-         media_mensal = total_contrib / meses_com_contrib
-         if media_mensal > 0:
-             meses_restantes = (valor_alvo - valor_atual) / media_mensal
-             from dateutil.relativedelta import relativedelta
-             data_previsao = (date.today() + relativedelta(months=int(meses_restantes))).isoformat()
+ progress = compute_progress(
+     target=Target(valor_alvo),
+     current=valor_atual,
+     contributions=seed_contribs,
+     today=date.today(),
+ )
+ data_previsao = progress.projected_completion_date.isoformat() if progress.projected_completion_date else None
```

**`DashboardService.resumo` metas-percentual loop** (1 site → 0 sites; was a within-PF DRY-N=2 duplication of `MetasService.listar`'s loop):

```diff
- for meta in metas_data:
-     valor_alvo = float(meta.get("valor_alvo", 1))
-     valor_atual = float(meta.get("valor_atual", 0))
-     meta["percentual"] = min((valor_atual / valor_alvo * 100) if valor_alvo > 0 else 0, 100)
+ for meta in metas_data:
+     progress = compute_progress(
+         target=Target(float(meta.get("valor_alvo", 0))),
+         current=float(meta.get("valor_atual", 0)),
+     )
+     meta["percentual"] = progress.percent_complete
```

**`OrcamentosService.obter_progresso` percentual_usado** (1 site → 0 sites):

```diff
- "percentual_usado": (total_gasto / total_planejado * 100) if total_planejado > 0 else 0,
+ progress = compute_progress(target=Target(total_planejado), current=total_gasto)
+ ...
+ "percentual_usado": progress.percent_complete,
```

**Total absorbed in PF: 5 inline math sites + 1 `dateutil.relativedelta` import.**

### 2.2 PF `dateutil.relativedelta` partial sweep — only `metas_service.py` cleaned

**Status of absorption proposal §2.6** ("after seed wiring, drop `python-dateutil` from PF's `pyproject.toml` if zero hits"):

- `dateutil.relativedelta` no longer imported in `metas_service.py` ✅
- `recorrentes_service.py` still imports `from dateutil.relativedelta import relativedelta` for transaction recurrence math (semanal / quinzenal / mensal / bimestral / trimestral / semestral / anual). Different concern — out of scope per the brief.
- Net: **`python-dateutil` cannot be dropped from PF requirements yet.**

**Application steps (deferred):** When (and if) PF's transaction recurrence math is also lifted to a seed primitive (e.g. a future `noctusai_lib.domain.recurrence` module), revisit this sweep. Meanwhile, the dependency stays.

**Triage:** **Accept** — partial sweep is the honest outcome given the current seed surface. Catalog this as a "watch list" item rather than a follow-up project (no clear N=3 trigger yet for transaction recurrence math).

### 2.3 `crossed_threshold_pct` — no PF consumer wired (per absorption proposal §2.3 guidance)

The seed's `accumulate_contribution(...) -> ProgressTransition` ships a third optional field `crossed_threshold_pct` (detects 25/50/75/100% milestone crossings) for future gamification consumers. PF has no use case today; the absorption project explicitly bundled this as accept-with-rationale (audit trail in the predecessor proposal §2.3).

**Application steps:** None. The wiring in `metas_service.adicionar_contribuicao` reads only `transition.new_current` + `transition.completed`. When PF gets a notifications-on-milestone or gamification-confetti feature, that consumer cycle wires `transition.crossed_threshold_pct` — the seam already ships.

**Triage:** Accept-with-rationale (already cataloged in predecessor project; no new entry needed).

### 2.4 Drive-by methodology fix — PF tests/conftest.py shadow-purge corrected (CROSS-CUTTING IMPLICATION)

**Linkage.** When wiring tests started failing with `ModuleNotFoundError: No module named 'noctusai_lib.domain.metas'`, root-cause analysis revealed:

1. The pip editable install of `noctusai_lib` was created from another worktree (`media-scheduling-port-resume`) which doesn't have the `metas/` subpackage yet.
2. PF tests' conftest had no shadow-purge logic (only `seed/lib/backend/tests/conftest.py` did).
3. **The seed-lib conftest's shadow-purge logic itself has a bug**: `getattr(finder, "MAPPING", None)` inspects the FINDER CLASS, but pip's PEP-660 finders (the `_EditableFinder` shape installed by `__editable___noctusai_lib_0_1_0_finder.py`) store MAPPING on the FINDER MODULE. The class-level `getattr` silently returns None, the finder is kept, and the editable install continues to win.

**Fix landed in `products/personal-finance/backend/tests/conftest.py`:**

```python
# Class-level MAPPING (legacy / hypothetical):
mapping = getattr(finder, "MAPPING", None)
if mapping is None:
    # Module-level MAPPING (pip's __editable___pkg_finder.py shape):
    mod_name = getattr(finder, "__module__", None)
    mod = sys.modules.get(mod_name) if mod_name else None
    mapping = getattr(mod, "MAPPING", None)
if isinstance(mapping, dict) and "noctusai_lib" in mapping:
    ...
```

**Cross-cutting implication.** The same fix likely belongs in `seed/lib/backend/tests/conftest.py § _purge_shadowing_editable_finders`. The seed-lib conftest probably never exercised the failing path because the seed-lib's own tests don't trigger fresh `noctusai_lib.X` resolution AFTER the purge — they import their own local modules via the `_LIB` sys.path entry, which works regardless of finder ordering. PF/ERP/daily-life tests *do* trigger fresh `noctusai_lib.X` resolution (via `app/services/*.py` files), so they hit the gap.

**Application steps:** Backport the corrected purge logic to `seed/lib/backend/tests/conftest.py`. ERP and daily-life sister-engineer wiring projects (Batch 1C) likely hit the same wall and need the same conftest fix on their side. Surface this so the orchestrator can decide:
- Apply once at seed-lib (cleanest — both PF/ERP/daily-life/future products inherit).
- Or apply per-product conftest (if seed-lib conftest is ABI-frozen for some reason).

**Triage:** Formalize at seed-lib layer. The product-side conftest fix in this project is necessary for THIS project to be green; the seed-lib backport is the durable cross-cutting fix.

### 2.5 Phase 1+2 collapse — methodology calibration validated

**Linkage.** Per absorption proposal §2.5, "future seed-absorption projects should plan for **1 collapsed implementation phase**." PF wiring shipped exactly this shape — Phase 1+2 collapsed into one libcst codemod pass touching three files. No test/validation gate between them; both pass through the same green pytest run. The methodology calibration generalized correctly.

**Application steps:** None — this is a methodology validation point, not a behavior change. The recommendation in absorption §2.5 to log this in `KB § PATTERNS/proposals-and-improvements.md` or `KB § PATTERNS/seed-lib-layout.md` is still pending; surfacing here as confirmation.

**Triage:** Methodology learning — orchestrator can apply (KB amend) or defer with destination.

### 2.6 Codemod over-imports — small future improvement

**Linkage.** The libcst codemod inserted the same 4-name seed import into all three target files, even though `dashboard_service.py` and `orcamentos_service.py` only use 2 of the 4 names. Manually trimmed post-codemod.

**Application steps:** A future codemod could be context-aware (analyze each method body to determine which seed names to import). Acceptable as-is for this project — manual trim was 2 small Edits.

**Triage:** Accept-with-rationale (small recurring nuisance, not blocking; might generalize to a future "smart import" codemod helper if N=2+ codemods need this shape).

---

## 3. Acceptance Criteria

- [x] PF backend pytest 100% green (584 passed).
- [x] Seed-lib pytest 100% green (660 passed).
- [x] Zero `dateutil` references in `metas_service.py` / `dashboard_service.py` / `orcamentos_service.py`.
- [x] Zero `valor_atual / valor_alvo * 100` (or equivalent inline percent shape) in PF backend services.
- [x] PF `MetasService.adicionar_contribuicao` writes `transition.new_current` (not the stale inline sum).
- [x] PF `MetasService.obter_progresso` ETA sourced from seed `project_completion_date` (no inline `relativedelta`).
- [x] Branch `pf-metas-seed-wiring` is up-to-date with origin/main; this project's commits are on the branch only (orchestrator does FF merge).
- [ ] **(Cross-cutting deferred)** Seed-lib conftest shadow-purge backport — surfaced as §2.4; orchestrator decides timing.

---

## 4. Standalone vs scheduled

- §2.1, §2.2, §2.3, §2.5, §2.6 are completed / accept-with-rationale / no-op-now. Audit-trail-only after this proposal.
- **§2.4 (seed-lib conftest backport) is the only standalone executable item** — independently scheduleable. Likely high-leverage because sister engineers (Batch 1C) probably hit the same wall and applied the same per-product fix; consolidating at seed-lib closes the recurrence at the framework level.

---

## 5. Related files

- `projects/pf-metas-seed-wiring/PROJECT.md` — design + audit + change log.
- `projects/pf-metas-seed-wiring/findings.md` — 5-category curated knowledge artifact.
- `products/personal-finance/backend/app/services/metas_service.py` — refactored.
- `products/personal-finance/backend/app/services/dashboard_service.py` — refactored.
- `products/personal-finance/backend/app/services/orcamentos_service.py` — refactored.
- `products/personal-finance/backend/tests/conftest.py` — shadow-purge fix (drive-by).
- `seed/lib/backend/noctusai_lib/domain/metas/**` — the seed module (consumed; not modified).
- `seed/lib/backend/tests/conftest.py` — has the BUG noted in §2.4 (not modified by this project).
- `projects/metas-domain-seed-absorption/proposals/claude-opus-4-7-20260503-end-of-project-bundle.md` — predecessor that named this project.
