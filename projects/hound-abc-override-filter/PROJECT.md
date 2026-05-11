# hound-abc-override-filter — calibrate `scan_cross_product_helpers` to skip ABC method overrides

**Status:** SHIPPED 2026-05-11
**Branch:** `hound-abc-override-filter-2026-05-11`
**Scope:** detector calibration (MCP-only)

## 1 · Context

`noctus.dev.scan_cross_product_helpers` (mcp/noctusai/tools/noctus/dev/recurrence.py:468) was flagging template-method ABC overrides as cross-product duplication. Surfaced earlier this session when the hound reported `_render_bodies` / `_aggregate` / `_build_subject` / `_build_summary` / `_fetch_window` / `_generate_narrative` as N=4-5 absorption candidates across `core` / `daily-life` / `mailing` / `personal-finance` (and `_render_bodies` also in `erp-imobiliario`).

Those methods are correctly-named overrides of `noctusai_lib.domain.digest.BaseDigestService` — a template-method ABC the seed already ships (KB § PATTERNS/digest-seed.md). The 4 narrative services inherit from it and *must* implement the abstract methods. The recurring NAMES are contract satisfaction, not absorption-shaped duplication.

## 2 · User intent

Dispatch brief: *"the detector should recognize them as legitimate overrides, not duplications."*

## 3 · Seed-first analysis (§3a)

The detector lives in MCP. Calibration is a detector concern, not a seed concern. The seed already ships the absorption (BaseDigestService); the detector was incorrectly flagging the SUCCESSFUL absorption as a NEW absorption candidate. No seed work needed.

## 4 · Approach

- Add `_KNOWN_ABC_BASES` set listing template-method ABCs whose method overrides are NOT absorption-shaped.
- Add `_extract_abc_override_names(path)` — stdlib `ast` walk: for each `ClassDef` inheriting a base in `_KNOWN_ABC_BASES`, collect direct-child `FunctionDef` / `AsyncFunctionDef` names.
- Track per-(name, product) whether occurrence was an override. If EVERY product's occurrence is an override → drop the finding. Mixed (some module-level + some override) → KEEP (the module-level ones may signal real absorption candidates).
- Use stdlib `ast` (not `libcst`) — mirrors the existing convention in this file (`import ast as _ast` at line 778 used by block-pattern detector) and keeps the MCP runtime dep-free. AST-first rule (CLAUDE.md §1) applies to EDITS; static analysis already uses `ast` here.

## 5 · Files

- `mcp/noctusai/tools/noctus/dev/recurrence.py` — `_KNOWN_ABC_BASES`, `_extract_abc_override_names`, `_class_inherits_known_abc`; integrated into `scan_cross_product_helpers`; stats now include `abc_override_filter_count` + `abc_override_filtered` + `known_abc_bases`.
- `mcp/noctusai/tests/test_recurrence.py` — new `TestScanCrossProductHelpersAbcOverrideFilter` class with 7 regression tests.

## 6 · Verification

### Before / after on real codebase (`--min-count 2`)

| Metric | Before | After |
|---|---|---|
| `total_findings` | 104 | 101 |
| `high_severity` | 20 | 17 |
| `warning_severity` | 84 | 84 |
| ABC-override-filtered names | — | 3 (`_build_subject`, `_build_summary`, `_generate_narrative`) |

### Digest names handled correctly

| Helper | Before (severity) | After | Reason |
|---|---|---|---|
| `_build_subject` | high (N=4) | FILTERED | All 4 products are ABC overrides; seed-formalized. |
| `_build_summary` | high (N=4) | FILTERED | All 4 products are ABC overrides; seed-formalized. |
| `_generate_narrative` | high (N=4) | FILTERED | All 4 products are ABC overrides; seed-formalized. |
| `_render_bodies` | high (N=5) | KEPT (mixed) | erp-imobiliario has it as MODULE-LEVEL — real absorption candidate. |
| `_aggregate` | high (N=4) | KEPT (mixed) | All 4 products have BOTH a module-level helper AND an override — module-level ones are real absorption candidates. |
| `_fetch_window` | high (N=4) | KEPT (mixed) | Same as `_aggregate`. |

The "mixed" outcome is a calibration win: those module-level helpers ARE absorption-shaped (they share window-fetch / aggregation shape across products) and were previously hidden by the noise of the false-positive override flags.

### Test counts

- Before: 35 tests (`test_recurrence.py`)
- After: 42 tests (35 + 7 new ABC-filter regression tests)
- Delta: +7

### Test scenarios (Phase 3)

| Scenario | Behavior | Test |
|---|---|---|
| 4 products with `class XService(BaseDigestService): def _render_bodies(...)` | NOT flagged | `test_abc_subclass_overrides_not_flagged` |
| 4 products with bare `def _render_bodies(...)` at module level | STILL flagged | `test_bare_module_level_helpers_still_flagged` |
| Mix of module-level + ABC overrides | STILL flagged (the bare ones matter) | `test_mixed_module_level_and_abc_overrides_still_flagged` |
| Method in a class NOT inheriting a known ABC | STILL flagged | `test_class_not_inheriting_abc_still_flagged` |
| `class Foo(digest.BaseDigestService):` (Attribute base, not Name) | NOT flagged | `test_abc_attribute_base_resolved` |
| `async def` override (BaseDigestService._fetch_window is async) | NOT flagged | `test_async_def_override_recognised` |
| Product file has a SyntaxError | Filter skips gracefully, no crash | `test_unparseable_file_does_not_crash_filter` |

## 7 · Extensibility

When the seed ships a NEW template-method ABC (e.g. `BaseChatbotService`, `BasePipelineService`), add the base-class name to `_KNOWN_ABC_BASES`. The filter then recognises method overrides of that ABC as contract satisfaction, not duplication.

## 8 · Constraints honored

- AST-first (stdlib `ast`, matching the file's existing convention).
- Co-located regression tests at `mcp/noctusai/tests/test_recurrence.py` (same file as the other helper-recurrence tests).
- No `--no-verify`.
- File-disjoint from in-flight SLOWAPI-PEP563-DETECTOR (different file: `mcp/noctusai/tools/dev/compliance.py`).

## 11 · Change log

- 2026-05-11: detector calibration complete; 3 false-positive findings removed from real-codebase scan; 7 regression tests added.
