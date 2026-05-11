# slowapi-pep563-keeper-detector — Project Document

> Living document. Authored from `templates/PROJECT-TEMPLATE.md`.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** ⏳ in progress (Engineer SLOWAPI-PEP563-DETECTOR)
- **Owner / stakeholders:** Architect · Engineer SLOWAPI-PEP563-DETECTOR
- **Related docs:** `KB § PATTERNS/testing.md § Regression-test-the-detector`, `mcp/noctusai/tools/noctus/dev/compliance.py`, previous incident fixes `auth-rate-limit-rollout`, `llm-endpoint-rate-limit-rollout`, `dt-test-forward-ref-fix`
- **Project slug:** `slowapi-pep563-keeper-detector` (cross-product / platform-infra — lives at `projects/<slug>/`)

---

## 1. Context & Purpose

`from __future__ import annotations` (PEP 563) makes ALL function/class annotations strings. slowapi's `@limiter.limit` decorator wraps its target via `@functools.wraps`, which copies `__module__`/`__name__`/`__qualname__`/`__doc__` but NOT `__globals__`. When FastAPI/Pydantic later resolves a string annotation via `eval()` to inspect the route signature, the lookup uses slowapi's globals — not the route module's. Any locally-declared model (`RunRequest`, `SSOTokenRequest`, `SubjectsRequest`, …) becomes a `PydanticUndefinedAnnotation` raised at app import time — the entire product fails to boot.

We have hit this slip **three** times this session:

1. `auth-rate-limit-rollout` — `core/sso.py` + `media-scheduling/oauth.py`
2. `llm-endpoint-rate-limit-rollout` — `mailing/routers/ai.py`
3. `dt-test-forward-ref-fix` — `dev-team/api/run.py`

Per the DRY recurrence rule (`KB § PATTERNS/project-execution.md § 2.7`), **N=3+ MUST formalize**. The right formalization for a "did this file get into the gotcha state?" question is a keeper detector (compliance contract — `KB § PATTERNS/testing.md § Regression-test-the-detector`).

---

## 2. Confirmed constraints

- **Severity** — HIGH. The combination causes app import failure (no fallback). *(Pin in detector output.)*
- **Detector home** — `mcp/noctusai/tools/noctus/dev/compliance.py`. *(The module's banner explicitly forbids sibling-module placement — meta-detector self-parses this file.)*
- **AST tool** — `import ast`. *(`compliance.py` has an explicit accept-with-rationale exemption for raw `ast` — KB § PATTERNS/accept-with-rationale.md; the dispatch dispatcher is parsed via `ast`, so the new detector follows suit. libcst would force a cross-module abstraction.)*
- **Scope** — `products/*/backend/app/routers/*.py` + `products/*/backend/app/api/*.py`. *(All known incidents fall here. Other backend files don't define decorated FastAPI routes.)*
- **Test colocation** — `mcp/noctusai/tests/test_compliance.py::TestCheckSlowapiWithPep563`. *(Matches the auto-discovery shape — no override entry needed.)*

---

## 3. Design principles

1. Detect both-conditions-true (`from __future__ import annotations` AND any `@limiter.limit`).
2. Be explicit in the rationale — engineers must understand the root cause (PEP 563 + `@functools.wraps`), not just see a red flag.
3. Follow the existing detector shape: `check_<name>(product_path: Path) -> list[dict]` returning `{product, file, issue, severity}` dicts.
4. Wire into `check_all_products()` AND `review._detect()` (the canonical pair documented in `compliance.py` banner).

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES — slowapi + PEP 563 incompatibility is platform-wide, not product-specific.
2. **Is the data source product-specific?** NO — we scan source files; the file walker is uniform.
3. **Is the placement product-specific?** NO — detector lives in `mcp/noctusai/tools/noctus/dev/compliance.py` (the seed-of-detectors); products inherit by virtue of being scanned.
4. **Is the visibility / permission rule the same?** YES — all products run the same compliance gate.
5. **Does the seam already exist in seed?** YES — `check_<name>` detector pattern + `check_all_products` + `review._detect` dispatch are the established seams. New detector slots in without seam invention.
6. **Default-on or opt-in?** DEFAULT-ON — same as every other keeper. No flag.

**Litmus — per-product code count this design requires: 0 lines.** The detector is platform-side; products incur zero new code.

**Phase plan implications:** §6 phases work in the detector module + tests; they do NOT walk through products. Correct shape.

---

## 4. Scope

**In scope:**
- New detector `check_slowapi_with_pep563(product_path: Path) -> list[dict]` in `mcp/noctusai/tools/noctus/dev/compliance.py`.
- Regression test class `TestCheckSlowapiWithPep563` in `mcp/noctusai/tests/test_compliance.py`.
- Plumb into `check_all_products()` + `review._detect()`.
- Verify zero false-positives across all 11 products (all known cases already fixed).

**Out of scope (for now):**
- Auto-fix tooling — keeper is observation-only (`KB § PATTERNS/keeper-observation-only`).
- Detecting OTHER `functools.wraps` losing-globals decorators — not the recurring slip; would be speculative scope creep.

---

## 5. Architecture / Data Model

### Detector signature

```python
def check_slowapi_with_pep563(product_path: Path) -> list[dict]:
    """Flag files combining `from __future__ import annotations` with
    `@limiter.limit` — the slowapi + PEP 563 incompatibility that
    crashes products at import time via PydanticUndefinedAnnotation."""
```

### Scan logic

1. Walk `product_path / "backend" / "app" / "routers" / "*.py"` + `product_path / "backend" / "app" / "api" / "*.py"`.
2. For each file, parse via `ast.parse(content)`.
3. **Check 1** — `from __future__ import annotations`:
   - Scan top-level `ast.ImportFrom` nodes where `module == "__future__"` and any alias `name == "annotations"`.
4. **Check 2** — any `@limiter.limit(...)` decorator anywhere in the file:
   - Walk the tree; for any `ast.FunctionDef`/`ast.AsyncFunctionDef`, inspect `node.decorator_list`. A decorator is "limiter.limit" if it's an `ast.Call` whose `func` is `ast.Attribute(value=ast.Name(id="limiter"), attr="limit")`.
5. If BOTH true → emit one issue per file (one is enough — the file-level state is the violation, not each decorator).

### Output shape

```python
{
    "product": <slug>,
    "file": <relative-path>,
    "issue": (
        "`<file>:<line>` combines `from __future__ import annotations` with "
        "`@limiter.limit` decorator(s). PEP 563 makes annotations strings; "
        "slowapi's `@functools.wraps` keeps `__module__`/`__name__` but NOT "
        "`__globals__`, so FastAPI/Pydantic `eval()` of forward-refs (e.g. "
        "`RunRequest`) resolves in slowapi's module → `PydanticUndefinedAnnotation` "
        "at app import. FIX: drop `from __future__ import annotations` from this "
        "file (safe if no PEP 604 `X | Y` annotations) OR move the rate-limited "
        "endpoint(s) to a separate file without the future import."
    ),
    "severity": "high",
}
```

---

## 6. Implementation phases

### Phase 0 — Read existing detector module shape ✅

**Improvements:** none identified — single-engineer keeper-detector authorship; meta-detector enforces colocated regression test (84/84 green).


- [x] Open `compliance.py` banner — rules about adding a new detector
- [x] Read `check_silent_errors` (closest model: per-product walk + AST)
- [x] Read `check_all_products` / `_detect` dispatch
- [x] Read `_detector_function_names` + `_DETECTOR_TEST_OVERRIDES` + meta-detector logic
- [x] Inventory existing files combining the two patterns (current state: 0, all 4 prior cases fixed)

### Phase 1 — Implement `check_slowapi_with_pep563` ✅

**Improvements:** none identified — single-engineer keeper-detector authorship; meta-detector enforces colocated regression test (84/84 green).


- [x] Add function in `compliance.py` (NOT a sibling module — meta-detector self-parses `compliance.py`)
- [x] AST-based detection using `import ast` (per the file's accept-with-rationale)
- [x] Return one issue per offending file

### Phase 2 — Regression test ✅

**Improvements:** none identified — single-engineer keeper-detector authorship; meta-detector enforces colocated regression test (84/84 green).


- [x] Add `TestCheckSlowapiWithPep563` in `test_compliance.py`
- [x] True-positive: file with BOTH patterns
- [x] False-positive 1: file with `@limiter.limit` only
- [x] False-positive 2: file with `from __future__ import annotations` only
- [x] False-positive 3: file with neither
- [x] Severity assertion (high)

### Phase 3 — Wire into review + check_all_products ✅

**Improvements:** none identified — single-engineer keeper-detector authorship; meta-detector enforces colocated regression test (84/84 green).


- [x] Add to `check_all_products()` list
- [x] Add to `review._detect()` import + per-product call

### Phase 4 — Verification ✅

**Improvements:** none identified — single-engineer keeper-detector authorship; meta-detector enforces colocated regression test (84/84 green).


- [x] Run pytest on the new test class
- [x] Run pytest on the rest of `test_compliance.py` to ensure no regression
- [x] Run the detector against all 11 products (should find 0 NEW — all 4 known cases fixed)

---

## 7. Open questions

None.

---

## 8. Dependencies & blockers

None.

---

## 9. Success criteria

- New detector lives in `mcp/noctusai/tools/noctus/dev/compliance.py`.
- Colocated `TestCheckSlowapiWithPep563` ships with the detector.
- `check_detector_has_regression_test()` finds the new test (auto-discovery via `Test<CamelCase>` shape).
- Running against all 11 products surfaces 0 NEW violations (all 4 known cases already fixed).
- `noctus.dev.review --product <X>` surfaces the new check.

---

## 10. How to use this plan

- Read §1 + §5 to understand the slip and the detector shape.
- Phase 1 is the canonical "add a new keeper detector" recipe; future detector additions can mirror it.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Project drafted from template after N=3 recurrence trigger | Engineer SLOWAPI-PEP563-DETECTOR |
| 2026-05-11 | Phases 0-4 shipped: detector + colocated regression test + dispatch wiring + verification (0 NEW violations across 11 products) | Engineer SLOWAPI-PEP563-DETECTOR |
