# Proposal: keeper-test-status-assertion — end-of-project bundle

**Agent:** claude-opus-4-7
**Origin:** project:keeper-test-status-assertion:close
**Generated:** 2026-05-06
**Severity:** medium
**Effort:** low (the cleanups are 3 one-line additions in erp-imobiliario)
**Affected products:** erp-imobiliario (cross-product cleanup) + platform (detector)
**Status:** pending

---

## 1. Context

Project `keeper-test-status-assertion` shipped a new keeper detector that flags pytest test methods asserting on response BODY (`.text` / `.json()` / `.content`) without a sibling assertion on response STATUS CODE in the same method. The slip this defends against is the YouTube Crawler Phase 1 false-green: a substring assertion on `resp.text.lower()` matched the wrong of two error entries in a 422 body, the test went green, but the endpoint was structurally unusable for any authed traffic. The detector closes that class of bug structurally.

Three phases shipped in this worktree (Phase 1 detector + 19 colocated tests; Phase 2 baseline + tightening + 4 more tests = 23 total; Phase 3 KB + memory three-way sync). This bundle proposal records the deferred items + cross-product cleanups that landed in the accept-with-rationale catalog.

---

## 2. Situation

- **Detector lives at:** `mcp/noctusai/tools/noctus/dev/compliance.py` — function `check_test_status_assertion(product_path)`. Plumbed into both `check_all_products()` and `tools/noctus/dev/review.py:_detect()` so findings surface via `noctus.dev.review`, `noctus.dev.validate`, and `cli.py --review --product <slug>`.
- **Colocated tests:** `mcp/noctusai/tests/test_test_status_assertion_detector.py` (23 tests, all green). Coverage: body-only flagged (text / JSON / content), body+status pass, helper functions skipped, class-nested + async walked, variable-name agnostic, status_code in tuple / inequality, chained `.text.lower()` detected, syntax-error-skip + non-test-file-skip + edge cases, response-variable gating (digest.text / result.content excluded; await-client recognized; helper-returned skipped).
- **Live findings (after detector tightening):** 3 true-positive cases, all in erp-imobiliario:
  1. `products/erp-imobiliario/backend/tests/routers/test_certidoes_router.py:114` — `test_paginacao_retorna_total` asserts on `resp.json()` body without status_code pin.
  2. `products/erp-imobiliario/backend/tests/routers/test_agenda_router.py:233` — `TestExcluirEvento::test_delete_message` asserts on `resp.json()["message"]` without status_code pin.
  3. `products/erp-imobiliario/backend/tests/routers/test_marketing_router.py:168` — `test_delete_message` asserts on `resp.json()["message"]` without status_code pin.
- **Catalog entries:** the 3 findings are catalogued in `KB § PATTERNS/accept-with-rationale.md` under a new "Entries from `keeper-test-status-assertion`" section. Each carries what / why-accept / revisit-trigger / recorded-by.
- **Other 11 products run clean** for this detector.
- **Frontend (Vitest) coverage is OOS** today — a follow-up `keeper-test-status-assertion-frontend` project will ship a ts-morph-based variant.

---

## 3. Recommendation

Two follow-ups — both deferred, no immediate-apply requirement:

1. **erp-imobiliario test-quality cleanup follow-up** (file as a new project when erp-imobiliario test maintenance comes up): apply `assert resp.status_code == <expected>` in the 3 catalogued tests (1-line additions; effort: trivial). Trigger conditions: erp-imobiliario test maintenance, OR localization changes affecting `"sucesso"` (the test will need to update either way).

2. **Frontend Vitest variant of the detector** (file as `keeper-test-status-assertion-frontend`): same rule, ts-morph-based, scans `products/*/frontend/src/**/*.{test,spec}.{ts,tsx}`. Trigger condition: after the Python detector beds in (≥2 weeks of clean runs in main).

---

## 4. Risks / open questions

- **None for the detector itself** — conservative gating + 23 colocated tests + 3 manually-verified live findings.
- **Cross-product cleanup risk = 0** — the rule is a structural test-quality nudge, not a behavioral change. Adding a status_code assertion can only fail (and would correctly surface a pre-existing bug). Removing one would only relax — not what's proposed.
- **Detector-meta-test is worktree-path-sensitive** — `tests/test_compliance.py::TestCheckDetectorHasRegressionTest::test_real_repo_passes` fails when run from this worktree because the venv installs from main repo path; my colocated test only exists in the worktree. Lands green when the branch merges to main. Verified: `check_detector_has_regression_test(repo_root=<worktree>)` returns `[]`.

---

## 5. Verification

- MCP tests (new detector): `cd mcp/noctusai && pytest tests/test_test_status_assertion_detector.py` — **23 / 23 pass**.
- Live scan: `python mcp/noctusai/cli.py --review --product erp-imobiliario` — **3 findings surface** (the catalogued ones).
- Live scan (other products): `python mcp/noctusai/cli.py --review --product personal-finance` — **0 findings** (clean).
- KB sync: `bash scripts/verify-kb-sync.sh` — **passes**.
- Pre-commit hooks: all phase commits passed `verify-kb-sync.sh` + `update-kb-counts.py` + `§6 ↔ §11 phase-state consistency`.

---

## 6. Files touched

- `mcp/noctusai/tools/noctus/dev/compliance.py` (+200 LOC: detector + helpers; plumbed into `check_all_products`).
- `mcp/noctusai/tools/noctus/dev/review.py` (+2 LOC: import + `_detect` plumbing).
- `mcp/noctusai/tests/test_test_status_assertion_detector.py` (NEW, 423 LOC, 23 tests).
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/testing.md` (+~70 LOC: Status-code-assertion rule section + table entry).
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md` (+33 LOC: 3 catalog entries).
- `projects/keeper-test-status-assertion/PROJECT.md` (phase ✅ flips + Change log entries).
- `~/.claude/projects/.../memory/feedback_status_code_assertion_rule.md` (NEW).
- `~/.claude/projects/.../memory/MEMORY.md` (+1 line, Testing / detectors section).
