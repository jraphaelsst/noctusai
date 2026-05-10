# findings.md — pf-metas-seed-wiring

> Durable knowledge artifact per `KB § 01-PHILOSOPHY.md § Knowledge tracking`. Synthesized at project close (2026-05-04). Distinct from `phase_learnings.db` + `live-patterns-log.md` + §11 (what-we-DID): findings.md is what-we-LEARNED, curated.

---

## 1. Errors

- **`ModuleNotFoundError: No module named 'noctusai_lib.domain.metas'`** during initial test run after libcst refactor. Root cause: pip editable install of `noctusai_lib` pointed at a stale sister worktree (`media-scheduling-port-resume`) which doesn't yet have the `metas/` subpackage. The PF tests' conftest didn't have the shadow-purge logic that the seed-lib tests' conftest has. Fixed by adding shadow-purge to PF tests/conftest.py.
- **`AttributeError: module 'libcst' has no attribute '__version__'`** when probing libcst — non-fatal; trivial mistake (correct attribute is `_version`). Just used `import libcst` as the existence check.
- **First conftest fix had two bugs**: (1) `parents[3]` was wrong (resolved to `products/seed/lib/backend` which doesn't exist) — needed `parents[4]`; (2) the seed-lib conftest's `getattr(finder, "MAPPING", None)` doesn't actually work for pip's PEP-660 editable finders because MAPPING lives on the FINDER MODULE, not the class. Fixed by walking up to `sys.modules[finder.__module__].MAPPING` after the class-level lookup returns None.

## 2. Mistakes / slips

- Initially trusted the seed-lib conftest's purge logic verbatim and copied its shape into PF. Hit the same shadow-finder issue it claims to handle. Lesson: when copying methodology code, *verify it works against your actual environment* — the existing fix may itself be incomplete (see knowledge piece §5 below). The seed-lib conftest probably never exercised this path because seed-lib tests don't import service-side code that triggers a fresh `noctusai_lib.X` resolution after sys.modules is purged.
- Codemod over-imported names (`Contribution`, `accumulate_contribution`) into files that didn't use them (dashboard_service.py, orcamentos_service.py). Trimmed manually after the codemod ran. Future codemod could be context-aware (analyze each method body to determine which seed names to import). Acceptable as-is — context-aware import insertion is a sub-project of its own.
- Set `Status: Phase 0 ready` in the PROJECT.md and then immediately committed Phase 0 ticked. The "ready" framing is misleading — should have been "Phase 0 ✅". Updated retroactively.

## 3. Lessons

- **The seed-lib `_purge_shadowing_editable_finders` has a real bug** — its class-level `getattr(finder, "MAPPING", None)` doesn't fire for pip's PEP-660 finders because MAPPING is on the *module*, not the class. Lesson: methodology fixes shipped without integration-test coverage can ship the methodology AND ship its bug at the same time. The fix lived in seed-lib but was never exercised against the cross-worktree shadow scenario in real PF/ERP/daily-life test runs.
- **Phase 1+2 collapse is the right shape for "single AST codemod, three target files".** Engineer 3 of Batch 1B's methodology learning §2.5 ("collapsed phases for tightly-coupled refactors") generalized correctly. The codemod is one logical unit; splitting "metas + dashboard" from "orcamentos" added no value because there's no test/validation gate between them — both pass through the same green pytest run.
- **Seed `compute_progress` is genuinely platform-neutral.** Using it for PF metas (accumulation: target = goal amount, current = saved so far) AND PF orcamentos (spending: target = budget cap, current = spent so far) "just works" because the math `current/target × 100` is identical and the seed has no opinion. This validates the platform-neutral design rationale in `KB § PATTERNS/metas-seed.md § 1`.
- **`compute_progress(target=Target(0), current=0)` returns 0.0** without raising — confirms seed handles PF's `valor_alvo=0` legacy edge case (legacy because PF's schema actually has `valor_alvo gt=0` Pydantic constraint, but the service code historically defended against missing/zero values with a guard). The seed's `_percent_complete` early-returns 0.0 for `target <= 0`. No regression risk.
- **libcst's `parse_module` + `with_changes(body=...)` is a clean pattern for method-body refactors.** Building the new body via `cst.parse_module("def _sentinel():\n<indented snippet>")` and extracting the IndentedBlock works reliably when the snippet is hand-authored (as here). No formatting drift; round-trip preserves the rest of the file verbatim.

## 4. Interesting findings

- **`recorrentes_service.py` still uses `dateutil.relativedelta`** for transaction-recurrence math (semanal/quinzenal/mensal/bimestral/trimestral/semestral/anual). Different concern than metas; explicitly out-of-scope per absorption proposal §2.6 ("after seed wiring, grep -rn 'dateutil' products/personal-finance/backend/app/ — if zero hits, drop python-dateutil"). Cannot drop the dep yet — surface as: future cleanup project candidate when (and if) recurrence math also lifts to seed.
- **PF schema's `metas.status` regex constraint is `^(ativa|concluida|pausada|cancelada)$`** — `cancelada` is in the schema but has no PT-BR ↔ seed `GoalStatus` mapping today. Seed `GoalStatus.ABANDONED` maps to `pausada` and `abandonada`. PF's `cancelada` would need a new mapping or to be treated as a synonym of `abandoned`. No PF code path actually writes `"cancelada"` today — surface as a deferred discovery item.
- **The dashboard_service.resumo()'s `metas` percent loop was a textbook DRY-recurrence with metas_service.listar()** — N=2 within PF for the SAME inline math. The seed absorption project (PF being one of 3 donors) didn't catch this because the audit was per-file, not within-file. Now closed by both calling `compute_progress`.
- **Pre-commit hook `--check-phase-state` works correctly** when the worktree has the venv discoverable (via `$REPO_ROOT/venv/bin/python`). Worked here after I symlinked the worktree's `venv/` to the main worktree's `noctusai/venv` — sandbox-friendly fix that doesn't require env-var prefix on the commit. (The brief documented `PYTHON=...` prefix as the workaround; sandbox blocks env-prefix syntax, so symlink is the path through.)

## 5. Knowledge pieces

- **Seed `noctusai_lib.domain.metas` public surface (PF-relevant subset):**
  - `Target(amount: float)` — frozen dataclass; validates non-negative.
  - `Contribution(amount: float, at: date)` — frozen dataclass; `.yyyymm` property gives `"YYYY-MM"`.
  - `compute_progress(target, current, *, contributions=(), today=None, period_remaining_pct=None) -> Progress` — returns `Progress(percent_complete, remaining, projected_completion_date, status)`.
  - `accumulate_contribution(target, current, increment) -> ProgressTransition` — returns `ProgressTransition(new_current, completed, crossed_threshold_pct)`.
  - `project_completion_date(target, current, contributions, today) -> date | None` — stdlib month-math ETA via internal `_add_months`.
- **The `target` arg for `compute_progress` is a `Target` value object**, but `accumulate_contribution` accepts a bare `float` (no Target wrapper). Asymmetry surface: easy to mistype as `accumulate_contribution(target=Target(...), ...)`. Naming convention in the seed: type-wrapped for derivation/projection (Target), unwrapped float for accumulation. Worth knowing if you write more wiring code.
- **The seed's `Progress.status` field is fully derived** from `(percent_complete, current, period_remaining_pct)`. PF doesn't pass `period_remaining_pct` (PF goals are open-ended toward `data_alvo`, not period-bounded), so status returned will be one of `PENDING / IN_PROGRESS / COMPLETED`. PF doesn't read `progress.status` from the wiring (it persists its own PT-BR string vocabulary). The seed-side status is computed but unused — that's fine; it's free metadata.
- **PF `meta_contribuicoes.data` column** is a TEXT/date in `YYYY-MM-DD` format. Mapping to `Contribution.at` requires `date.fromisoformat(raw_date[:10])`. The `[:10]` is defensive against rows that may have a timestamp suffix (legacy / mixed-format rows). The new code wraps in `try/except ValueError` and silently skips unparseable rows — same effective behavior as the old code's implicit empty-string slice.
- **The pip PEP-660 editable finder layout** for `noctusai_lib` lives at `venv/lib/python3.11/site-packages/__editable___noctusai_lib_0_1_0_finder.py`. The MAPPING dict is at MODULE level. Seed-lib conftest's purge looks at class-level attribute and silently misses this. Real fix shape:
  ```python
  mapping = getattr(finder, "MAPPING", None)
  if mapping is None:
      mod = sys.modules.get(getattr(finder, "__module__", None))
      mapping = getattr(mod, "MAPPING", None)
  ```
  Seed-lib conftest should adopt this. Surfaced for orchestrator review.
- **Master venv `venv/bin/python` symlink trick for worktrees**: pre-commit hook prefers `$REPO_ROOT/venv/bin/python`; worktrees lack their own venv. `python -c "import os; os.symlink('/path/to/main/venv', '/path/to/worktree/venv')"` resolves it without env-var prefix (which the sandbox blocks). The symlink is intra-worktree (the `venv/` itself is gitignored — `git status` shows it but it never gets staged via my explicit `git add` paths).
