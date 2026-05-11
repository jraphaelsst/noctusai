# dev-team pydantic forward-ref fix — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1 complete (fix applied) — Phase 2 verification in progress
- **Owner / stakeholders:** Engineer DT-FORWARD-REF (architect dispatched)
- **Related docs:**
  - Sister project: `projects/auth-rate-limit-rollout/PROJECT.md` (AUTH-RL — same root-cause)
  - `KB § PATTERNS/ast.md` (AST-first; this case is a 1-line removal at file-top — Edit is fine)
  - Memory entry: `feedback_no_silent_errors.md`
- **Project slug:** `dt-test-forward-ref-fix` at `projects/dt-test-forward-ref-fix/` (single-product fix but inherits the AUTH-RL platform pattern; lives at platform-projects root for visibility alongside its sibling)

---

## 1. Context & Purpose

CORS-ROLLOUT's per-product test run surfaced 18 pre-existing `PydanticUndefinedAnnotation: name 'RunRequest' is not defined` errors in `products/dev-team/backend/tests/test_api_smoke.py`, plus 1 failure. The shape is identical to the AUTH-RL slip on `core/sso.py` + `media-scheduling/oauth.py`:

`from __future__ import annotations` (PEP 563) makes ALL annotations strings. slowapi's `@limiter.limit` decorator wraps the route with `@functools.wraps(func)` but does NOT propagate `__globals__`. When FastAPI/Pydantic try to resolve the string annotation `RunRequest` via `eval()`, the lookup runs in slowapi's module namespace where `RunRequest` doesn't exist — `PydanticUndefinedAnnotation` at import time, cascading into every test collection in `test_api_smoke.py`.

The fix shape AUTH-RL applied: drop `from __future__ import annotations` from the affected router file. Safe when no PEP 604 `X | Y` union syntax is used — `dev-team/backend/app/api/run.py` qualifies (uses `Optional[str]` only).

Win: dev-team backend tests collect + run cleanly; CORS-ROLLOUT downstream verification unblocked; the AUTH-RL pattern formalizes across one more product.

---

## 2. Confirmed constraints

- **Root cause locked** — slowapi + `from __future__ import annotations` + Pydantic forward-ref on a BaseModel param. *(Surfaced by CORS-ROLLOUT's per-product test run; pattern matches AUTH-RL exactly.)*
- **Fix shape preferred** — Option A: drop `from __future__ import annotations` from `app/api/run.py`. *(Matches AUTH-RL's fix; preserves the locality of the workaround at the affected file.)*
- **Branch rename** — `dev-team-pydantic-forward-ref-fix-2026-05-11` per KB §20 engineer-letter naming convention. *(Done at session start.)*
- **AST-first ok with Edit here** — the change is a single-line removal at file-top, no symbol rewiring; pytest is the verification oracle.
- **No --no-verify** — pre-commit hook must pass.

---

## 3. Design principles

1. **Single-file change matches the cause.** Only `app/api/run.py` carries the `@limiter.limit` + future-annotations combo in dev-team. Other api/*.py files use future-annotations but no slowapi decoration; leaving them touched would be needless churn.
2. **Test count is the oracle.** Brief reports 18 errors + 1 failure; verification target is 0 errors and the test_api_smoke.py suite green.
3. **Don't expand scope.** The 4 `test_team_*_401` failures observed in the local baseline are unrelated to forward-refs (they're `404 vs 401` on `/api/team` routes) — surface as a finding for the architect, do not fix in this scope.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** Partial — `from __future__ import annotations` + slowapi is a cross-product foot-gun. The recurrence catalog already fired (AUTH-RL N=2 + this brings N=3 → MUST formalize).
2. **Is the data source product-specific?** N/A — process / hygiene fix.
3. **Is the placement product-specific?** YES — the fix lives in the affected router file. The PATTERN belongs in seed docs (already referenced in memory under "feedback_silent_ok_is_not_a_substitute_for_logging" + KB § PATTERNS/backend.md for slowapi guidance — TBD).
4. **Is the visibility / permission rule the same?** N/A.
5. **Does the seam already exist in seed?** YES — `noctusai_lib.api.middleware.rate_limit` factory; the foot-gun is consumer-side wiring, not seed-side.
6. **Default-on or opt-in?** N/A — defect fix.

**Litmus — per-product code count this design requires:** 1 line (the `from __future__ import annotations` removal in `app/api/run.py`).

**Phase plan implications:** §6 phases work in the affected file only. The recurrence rule fires at N=3 (core/sso, media-scheduling/oauth, now dev-team/run) — recommend the architect file a follow-up project: KB documentation entry + linter / keeper detector for "slowapi-decorated route in a file with `from __future__ import annotations`". Captured in §11 findings.

---

## 4. Scope

**In scope:**
- Drop `from __future__ import annotations` from `products/dev-team/backend/app/api/run.py`.
- Run pytest and confirm 0 errors in `test_api_smoke.py` collection.

**Out of scope (for now — with reason):**
- Fixing the 4 `test_team_*_401` failures in `test_e2e_flows.py` — different root cause (`/api/team` routes returning 404 instead of 401); surfaced as a finding for the architect to triage.
- Removing `from __future__ import annotations` from sibling api files (`agents.py`, `configs.py`, `metrics.py`) — they don't use slowapi, so they don't trigger the bug. Pre-emptive removal would churn without payoff.
- Authoring a keeper detector or KB §PATTERNS/backend.md note for the slowapi + future-annotations interaction — N=3 recurrence work that the architect should scope as a follow-up.

---

## 5. Architecture / Data Model

N/A — single-line defect fix at `products/dev-team/backend/app/api/run.py:2`.

---

## 6. Phases

**Phase 0 — Diagnose** (DONE):
- Read `tests/test_api_smoke.py` — confirmed `from __future__ import annotations` at top.
- Read `app/api/run.py` — confirmed `from __future__ import annotations` + `class RunRequest(BaseModel)` + `@limiter.limit("10/minute")` on `async def run_team(... body: RunRequest, ...)`.
- Checked sibling api files: only `run.py` combines slowapi with a BaseModel parameter and future-annotations. Other future-annotations files (agents/configs/metrics) have no slowapi.
- Verified no PEP 604 `X | Y` union syntax in run.py.
- Confirmed AUTH-RL fix shape: `products/core/backend/app/routers/sso.py` + `products/media-scheduling/backend/app/routers/oauth.py` have NO `from __future__ import annotations` at top (already fixed by AUTH-RL).

**Phase 1 — Fix** (DONE):
- Drop line 2 `from __future__ import annotations` from `products/dev-team/backend/app/api/run.py`.

**Phase 2 — Verification** (IN PROGRESS):
- `pytest products/dev-team/backend/tests/test_api_smoke.py -q` → all green.
- `pytest products/dev-team/backend/ -q` → confirm no NEW regressions beyond the 4 pre-existing `test_team_*_401` failures noted as out-of-scope.

---

## 7. Open Questions

None blocking this fix. Surfaced for architect attention:
- **N=3 recurrence on slowapi + future-annotations** — `feedback_no_silent_errors.md` shape applies. Recommend: ship a keeper detector OR a KB §PATTERNS/backend.md note + `noctus.hound.scan` rule + linter check. *(Architect-scoped follow-up.)*

---

## 8. Risks & Mitigations

- **Risk:** Dropping `from __future__ import annotations` could break a forward-reference elsewhere in `run.py`. *Mitigation:* file uses only `Optional[str]` annotations on already-defined types; nothing references a class before its definition. Pytest verifies.

---

## 9. Done definition

- `app/api/run.py` no longer has `from __future__ import annotations` at top.
- `pytest tests/test_api_smoke.py -q` collects + runs all tests without `PydanticUndefinedAnnotation` errors.
- Full backend pytest run shows no NEW regressions vs baseline.
- Branch `dev-team-pydantic-forward-ref-fix-2026-05-11` pushed; orchestrator does FF-to-main per close gate.

---

## 10. Reproduction / commands

```bash
# Baseline
cd products/dev-team/backend
PYTHONPATH=$(pwd):$(pwd)/../../.. /Users/rapha/Documents/repository/NoctusAI/noctusai/products/dev-team/backend/.venv/bin/pytest tests/ -q

# After fix
PYTHONPATH=$(pwd):$(pwd)/../../.. /Users/rapha/Documents/repository/NoctusAI/noctusai/products/dev-team/backend/.venv/bin/pytest tests/test_api_smoke.py -q
```

---

## 11. Change log

- **2026-05-11** — Engineer DT-FORWARD-REF dispatched. Phase 0 diagnose, Phase 1 fix (line-2 removal), Phase 2 verification. N=3 recurrence on slowapi + `from __future__ import annotations` noted; surfaced for architect follow-up.
