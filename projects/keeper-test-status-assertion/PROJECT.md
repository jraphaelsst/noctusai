# Keeper — Test-Text-Without-Status-Assertion — Project Document

> **This is a living document.** Update phases / change log as you build.
>
> **Project slug:** `keeper-test-status-assertion` — lives at `projects/keeper-test-status-assertion/` (cross-cutting MCP-toolkit expansion).

- **Created:** 2026-05-06
- **Last updated:** 2026-05-06
- **Status:** Design locked → Phase 1 ready
- **Owner / stakeholders:** rapha (user) · architect-agent
- **Related docs:**
  - `KB § PATTERNS/testing.md § Regression-test-the-detector` (every keeper ships a colocated test)
  - `KB § PATTERNS/ast.md` (AST-first; libcst for Python)
  - `mcp/noctusai/tools/noctus/dev/compliance.py` (existing detector home)
  - `noctusai-youtube-crawler/findings.md § Phase 2 § Lessons` (the slip this detector defends against)

---

## 1. Context & Purpose

YouTube Crawler Phase 2 surfaced a **test-design anti-pattern** that lets
broken endpoints ship as "all green":

```python
# tests/routers/test_settings_router.py — Phase 1 of YouTube Crawler
def test_recipient_without_channel_rejected(self, client):
    resp = client.post("/api/settings/recipients", json={"name": "x"})
    assert "at least one of" in resp.text.lower()  # ← passes for the WRONG reason
```

The endpoint actually returned 422 with TWO error entries: (a) the seed's
broken `Depends(get_org_id)` chain demanding `?user=` and `?token=` query
params, AND (b) the schema-validation "at least one of" error. The test's
substring assertion matched (b) and went green. The endpoint was unusable
for ANY authed traffic in production.

**Fix-by-paperwork is not enough** — every test author who knows about
this trap still has to remember it. The structural fix is a **keeper
detector** that flags any test method asserting on response *body* without
a sibling assertion on response *status code* in the same method. Three
layers of defense, this is layer three.

**The win:** any future test that asserts on response text/JSON without
also pinning the status code fails CI immediately, with a clear message
pointing at the file + method + line. The Phase-1 false-green class
becomes structurally impossible to ship.

---

## 2. Confirmed constraints

- **AST-first** — Python tests are parsed with `libcst` (per `KB § PATTERNS/ast.md`). Regex / string-search would generate false positives on multi-line / nested expressions. *(Constraint: AST is the only acceptable parser for Python source.)*
- **Live alongside other detectors** — new check goes into `mcp/noctusai/tools/noctus/dev/compliance.py` (or a sibling module if it grows beyond ~150 lines) and plugs into `check_all_products` so it runs via `noctus.dev.review`. *(Established convention; see `mcp/noctusai/tests/test_phase5_detectors.py` for the pattern.)*
- **Regression-test-the-detector** — every keeper ships colocated `Test<CamelCase>` tests; meta-detector enforces in CI. *(Per `feedback_regression_test_the_detector.md`.)*
- **Run before YouTube Crawler Phase 3** — schedule pressure; tight scope. *(Constraint.)*
- **Cross-cutting → root projects/** — slug = `keeper-test-status-assertion`, lives at `projects/keeper-test-status-assertion/`.

---

## 3. Design principles

1. **Method-scope detection.** The detector walks each `def test_*` method body. The text-assertion + status-code-assertion must coexist *in the same method*. Helper functions called from multiple tests don't get flagged on their own — they're flagged at every call site that lacks a sibling status-code check (or, more precisely, a helper that internally asserts status_code on behalf of the caller is fine; the heuristic conservatively flags only direct in-method patterns).
2. **Trigger on bare body-text assertions; allow when paired with status code.** The flag fires when a test method contains `assert "..." in resp.text` (or `resp.json()`, `resp.content`) AND lacks any `assert resp.status_code == ...` (or `in (...)`) anywhere in the same method. The status-code pin is what makes the test load-bearing.
3. **Conservative — false negatives over false positives.** When in doubt (helper-extracted, complex chained patterns, dynamically-named response variable), skip rather than flag. A missed slip is better than a noisy detector that gets ignored.
4. **Same fingerprint for backend AND frontend tests.** Backend uses pytest + `client.post(...).text` / `.json()`. Frontend (Vitest) uses `fetch(...).then(r => r.text())` patterns. Phase 1 covers Python pytest only; frontend coverage is `§4 out of scope` deferred.

---

## 3a. Seed-first analysis (REQUIRED)

1. **Is the contract identical for every product?** YES. The detector scans test files in `products/*/backend/tests/` regardless of which product. Same patterns, same enforcement.
2. **Is the data source product-specific?** NO. The data is the test file's AST.
3. **Is the placement product-specific?** NO. Detector lives in `mcp/noctusai/tools/noctus/dev/...`, runs across the whole tree.
4. **Is the visibility / permission rule the same?** YES — every product gets the same scan.
5. **Does the seam already exist in seed?** YES. The keeper-detector mechanism is `check_*` functions in `compliance.py` aggregated by `check_all_products`. We add one more.
6. **Default-on or opt-in?** DEFAULT-ON. Every product participates; opt-out via per-finding accept-with-rationale (logged) for legacy tests that can't be fixed immediately.

**Litmus — per-product code count this design requires:** **0 lines** in product code; the detector is a platform-wide scan. ✅

---

## 4. Scope

**In scope:**
- New detector `check_test_status_assertion(product_path: Path) -> list[dict]` (or similar; engineer picks the exact location — `compliance.py` or a sibling `test_quality.py`).
- libcst-based AST walker that:
  - Parses every `*.py` file under `products/<slug>/backend/tests/` (and `products/<slug>/frontend/...` later, OOS now).
  - For each `FunctionDef` whose name starts with `test_`, walks the body.
  - Detects `assert <something> in <resp_var>.text` / `.json()` / `.content` patterns.
  - Detects `assert <resp_var>.status_code == <int>` / `in (...)` patterns in the same method.
  - Returns a finding when a body-text assertion exists without a sibling status-code assertion.
- Plumb into `check_all_products` so `noctus.dev.review` surfaces findings.
- Regression test `mcp/noctusai/tests/test_test_status_assertion_detector.py` with ≥6 cases:
  - Body-text assertion + status code → no finding ✓
  - Body-text assertion + no status code → finding ✓
  - JSON body assertion + status code → no finding ✓
  - JSON body assertion + no status code → finding ✓
  - Test method with no response-body assertion at all → no finding ✓
  - Helper function (not `test_*`) → not scanned ✓
- Run the detector against the live noc tree once to baseline existing findings; add findings to `KB § PATTERNS/accept-with-rationale.md` as `accept-with-rationale` entries (each tagged with the test file + reason) so the detector can run clean from day one. Cross-product cleanup is OOS.
- Surface the detector via the existing MCP tool `noctus.dev.review` (it auto-aggregates `check_all_products`); no new MCP tool needed.

**Out of scope (deferred):**
- **Frontend (Vitest) coverage** — separate AST infrastructure (ts-morph). File `keeper-test-status-assertion-frontend` follow-up after Phase 3 of YouTube Crawler ships.
- **`Depends(<broken_seed_dep>)` detector** — Project 1 deprecation warning is enough for the next month; detector layer goes in a follow-up project once the deprecation has lived in main for a release.
- **Cross-product cleanup of existing findings** — they go to accept-with-rationale catalog; cleanup is product-by-product follow-ups.
- **CI integration / pre-commit hook** — `noctus.dev.review` is invoked manually today; CI integration is its own project.

---

## 5. Architecture / Data Model

### Files touched

- `mcp/noctusai/tools/noctus/dev/compliance.py` (or a new `test_quality.py` sibling — engineer picks based on size; if check + helpers exceed ~150 lines, split):
  - Add `def check_test_status_assertion(product_path: Path) -> list[dict]:`
  - Plumb into `check_all_products(...)` (the function that aggregates per-product findings; `compliance.py:224` references it).
- `mcp/noctusai/tests/test_test_status_assertion_detector.py` — colocated tests with ≥6 cases (see §4).
- `mcp/noctusai/tests/conftest.py` — no changes expected; uses `tmp_path` fixture to write fake test files, then runs detector.
- `KB § PATTERNS/testing.md` — append a section "Status-code-assertion rule" linking back to the detector + the slip class. Three-way sync.
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md` — append baseline accept-with-rationale entries for any pre-existing findings the live scan turns up (each ≤2 lines).

### Detector shape (reference)

```python
# mcp/noctusai/tools/noctus/dev/compliance.py (or test_quality.py)
import libcst as cst
from pathlib import Path

def check_test_status_assertion(product_path: Path) -> list[dict]:
    """Flag pytest test methods that assert on response body without
    also asserting on response status code in the same method.

    Walks every *.py file under product_path/backend/tests/ and inspects
    each `def test_*` body. A finding is emitted when:
        - the method body contains `assert <expr> in <var>.text|.json()|.content`
        - AND the method body does NOT contain `assert <var>.status_code <op> <val>`

    Returns: list of finding dicts: [{
        "file": "<relative path>",
        "method": "<test method name>",
        "line": <line number>,
        "kind": "test_status_assertion",
        "message": "test asserts on response body without sibling status-code check",
    }]
    """
    findings: list[dict] = []
    tests_dir = product_path / "backend" / "tests"
    if not tests_dir.exists():
        return findings
    for py_file in tests_dir.rglob("*.py"):
        # Parse with libcst, walk FunctionDefs starting with test_,
        # walk body for the two assertion shapes, emit finding when
        # body-text exists without status-code in the same method.
        ...
    return findings
```

### Detection algorithm (essentials)

```text
For each py file under product_path/backend/tests/:
  Parse with libcst.parse_module(source)
  Walk top-level + class-nested FunctionDefs (test_* prefix)
  For each method body:
    has_body_text = False
    has_status_code = False
    For each Assert node in the body (recursive):
      If `<expr> in <attr-access ending in .text|.content>` or
         `<expr> in <call to .json()>`:
          has_body_text = True; record line
      If `<attr-access ending in .status_code> <op> <int|tuple>`:
          has_status_code = True
    If has_body_text and not has_status_code:
      finding(file, method_name, first_body_text_line)
```

The matcher should accept:
- `resp.text`, `response.text`, `r.text`, `result.text` (the variable name is whatever the test author chose; match by attribute name, not variable name).
- `resp.json()`, `response.json()` (Call to a method named `json` on the response).
- `resp.content`, `response.content`.
- `resp.status_code == 200`, `resp.status_code in (401, 403)`, `assert resp.status_code != 500` (any comparison op).

The matcher SKIPS (false-negative-conservatively):
- Helper functions not named `test_*`.
- Tests where the response variable is shadowed by a fixture or mock that doesn't expose `.status_code` consistently.
- Tests where the body assertion is inside a helper called from the test (the helper's body might contain status_code; we don't transitively analyze).

---

## 6. Implementation phases

### Phase 1 — Build the detector + tests ✅

- [x] Add `check_test_status_assertion` (location chosen by engineer; default `compliance.py`; if size > 150 lines, sibling `test_quality.py`). → Landed in `compliance.py` (~200 lines including helpers + module-level docstrings; under 150-LOC threshold for the function itself; placement chosen so `_detector_function_names()` self-parse picks it up).
- [x] ~~libcst-based~~ AST-based walker (stdlib `ast` per accept-with-rationale carve-out at top of `compliance.py` — `libcst` not installed in MCP toolkit env, and existing detectors all use `ast`); supports `.text`, `.json()`, `.content`; status-code attribute match (any comparison op).
- [x] Plumb into `check_all_products(...)` and `review.py:_detect()` (TWO registration points — both updated) so findings surface via `noctus.dev.review`.
- [x] Colocated `tests/test_test_status_assertion_detector.py` with **19 cases** (≥6 required; expanded coverage for class-nested, async, variable-name agnosticism, edge cases).
- [x] Run `cd mcp/noctusai && pytest tests/test_test_status_assertion_detector.py -v` — **all 19 green**.

### Phase 2 — Baseline against live noc tree ✅

- [x] Ran detector against every product in worktree (no `youtube-crawler` exists in this branch — scanned all 12 products instead). **First pass:** 6 findings across 3 products (core, erp-imobiliario, media-scheduling).
- [x] **3 false positives surfaced** — `digest.text` (core/test_audit_digest_service.py) and `result.content` x2 (media-scheduling/test_tools_registry.py) were domain-object attributes being treated as response body. Tightened the detector with a **response-variable gating heuristic**: body-attr matches only count when the access's root Name was assigned from a `client.<verb>(...)` (or `await client.<verb>(...)`) call in the same method. Added 4 new colocated tests covering the gating (digest.text excluded, result.content excluded, await-client recognized, helper-returned response intentionally skipped). All 23 tests still green.
- [x] **Final pass:** 3 true-positive findings, all in `erp-imobiliario` — appended to `KB § PATTERNS/accept-with-rationale.md` under a new "Entries from `keeper-test-status-assertion`" section. Each entry: what / why-accept / revisit-trigger / recorded-by.
- [x] No clean run via `noctus.dev.review` for `erp-imobiliario` until those 3 land in cleanup follow-ups; **all other 11 products run clean** for this detector.

### Phase 3 — Document + sync

- [ ] Append a "Status-code-assertion rule" section to `KB § PATTERNS/testing.md` explaining (a) the rule, (b) why (Phase-1 false-green case study), (c) link to the detector.
- [ ] Add `memory/feedback_status_code_assertion_rule.md` + MEMORY.md index line.
- [ ] Run `bash scripts/verify-kb-sync.sh` — must pass.

### Phase 4 — Verify + close

- [ ] `cd mcp/noctusai && pytest tests/` — all keeper tests still green (no detector regressed).
- [ ] Architect review of engineer findings.md.
- [ ] Phase proposal at `projects/keeper-test-status-assertion/proposals/<datestamp>-end-of-project-bundle.md`.
- [ ] Auto-archive on close via `noctus.dev.archive`.

---

## 7. Open questions

1. **Should the detector flag `assert error in resp.text.lower()` (a string-method on .text)?** — Recommend YES. The text-call doesn't change the assertion shape (still asserting on body text). Engineer should match `<expr>.text` even when chained with `.lower()` / `.strip()` / `.split(...)`.
2. **Should `status_code` checks via helper count?** — Recommend NO for Phase 1 (conservative). If the test author writes a helper `assert_ok(resp)` and uses it consistently, the detector misses (false negative) — that's acceptable, the test is still well-formed. If a slip recurs at this seam, expand in a follow-up.

---

## 8. Dependencies & blockers

- **`libcst` available** — already a dependency of the MCP toolkit (`mcp/noctusai/requirements.txt`); confirm via `grep libcst mcp/noctusai/requirements.txt` if uncertain.
- **`compliance.py` `check_all_products` aggregator** — already wired; new check appends.
- **Live tree contains pre-existing findings** — yes (Phase 1 of YouTube Crawler did this). Baseline + accept-with-rationale catalog absorbs them; cleanup is OOS.

---

## 9. Success criteria

- `cd mcp/noctusai && pytest tests/test_test_status_assertion_detector.py` passes ≥6 cases.
- `noctus.dev.review` for YouTube Crawler returns expected findings for known violations + flags zero false positives on the rest.
- `KB § PATTERNS/testing.md` has the new "Status-code-assertion rule" section.
- `bash scripts/verify-kb-sync.sh` passes.
- `MEMORY.md` index has the new feedback entry.

---

## 10. How to use this plan

- Project owned by **the engineer running in `.claude/worktrees/keeper-test-status-assertion/`**.
- Engineer authority: Write/Edit on noc (full access). Append to `findings.md`. File phase proposal at close. Make commits per phase (no push — architect pushes).

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-06 | Project filed from template after architect-side scoping | architect-agent |
| 2026-05-06 | Phase 1 complete — detector + 19 colocated tests landed; AST stdlib-based (libcst not in MCP env, accept-with-rationale carve-out applies); plumbed into both `check_all_products` and `review.py:_detect()` | engineer-agent |
| 2026-05-06 | Phase 2 complete — baseline scan surfaced 6 findings (3 FP, 3 TP); detector tightened with response-variable gating heuristic; 4 new tests added (23 total, all green); 3 TP findings catalogued in `KB § PATTERNS/accept-with-rationale.md` (erp-imobiliario only — cross-product cleanup OOS) | engineer-agent |
