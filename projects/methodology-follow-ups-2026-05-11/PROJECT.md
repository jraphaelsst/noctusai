# methodology-follow-ups-2026-05-11 — Project Document

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Phase 1+2 shipped — green
- **Owner / stakeholders:** Engineer MMM (architect-dispatched)
- **Related docs:** `mcp/noctusai/cli.py`, `mcp/noctusai/tools/noctus/dev/{compliance,review}.py`, `mcp/noctusai/tests/test_compliance_prod.py`, `mcp/noctusai/tests/test_cli_worktree_path.py`
- **Project slug:** `methodology-follow-ups-2026-05-11` (cross-cutting MCP toolkit hygiene → `projects/` root)

---

## 1. Context & Purpose

Two related methodology gaps surfaced during the keeper-trio Wave 1 batch (2026-05-10/11):

1. **`keeper-cli-worktree-arg`** — `python mcp/noctusai/cli.py --review --product <slug>` reads migrations from the canonical noc clone, not the engineer's worktree. Engineers AAA + BBB + ZZ all hit it; workaround was either in-process `run_review(products_dir=...)` calls or `ln -s` into the worktree's products dir.
2. **`keeper-detector-supersession-tuning`** — `check_function_search_path_pinned` flags earlier `CREATE FUNCTION` blocks when a later `CREATE OR REPLACE FUNCTION foo SET search_path = ...` in the same migration tree fixes the runtime behavior. N=2 (therapy GG 2026-05-10 + ZZ 2026-05-11). 9 residual ERP findings were accept-with-rationale because of this — they should clear once the detector is calibrated.

Both touch `mcp/noctusai/` and share the same review pipeline, so this project handles them as a combined deliverable.

---

## 2. Confirmed constraints

- **Combined dispatch** — architect's brief explicitly batches both follow-ups under one engineer (Engineer MMM) for cleaner archive. *(Same code surface; coupling outweighs splitting.)*
- **AST-first for Python edits** — required per CLAUDE.md universal rules. *(Regex used only in detector internals where we're parsing SQL — not Python source.)*
- **No monkey-patching** — even in tests. *(MockSupabaseClient + dependency injection are the seed-approved seams; the new tests use subprocess + fixture-tree builders, no patching.)*
- **Keep `PROJECT.md` combined** — single doc, two follow-ups under §4 scope. *(Architect directive.)*
- **No `--no-verify`** — pre-commit must pass cleanly. *(Universal rule.)*

---

## 3. Design principles

1. **Override at the boundary, not inside each detector.** The CLI rebinds `settings.REPO_ROOT` / `settings.PRODUCTS_DIR` BEFORE lazy-importing any `tools.*` module — every downstream `from settings import REPO_ROOT, PRODUCTS_DIR` then picks up the override automatically. No per-detector `worktree_path` parameter needed.
2. **Belt-and-suspenders for review.** Even with the rebind in place, the CLI also passes `products_dir=` explicitly to `run_review()` — redundant-but-explicit closes the gap if a future refactor relinks `review.py` to a non-`settings`-derived path.
3. **Supersession is a per-function global pass, not a per-block flag.** The pre-fix detector iterated each `CREATE FUNCTION` block independently. The post-fix detector aggregates all blocks per qualified-name across all migrations in lexical filename order, then evaluates ONLY the LATEST block per name. Mirrors Postgres' actual `pg_proc` reality.
4. **Reproduce with fixture-trees, not real products.** Both detector and CLI tests build fake product trees in `tempfile.mkdtemp` — no coupling to noc's live products/.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** YES — every product's migrations get scanned with the same rule.
2. **Is the data source product-specific?** NO — the source is the product's `backend/migrations/*.sql`, scanned via the same `Path` walk.
3. **Is the placement product-specific?** NO — the detector lives in `mcp/noctusai/tools/noctus/dev/compliance.py` (single canonical home).
4. **Is the visibility / permission rule the same?** YES — every product gets the same advisor-0011 enforcement.
5. **Does the seam already exist in seed?** YES — `_detect()` in `review.py` already accepts `products_dir=`; `run_review()` already accepts `worktree_path=`. The CLI was the only consumer not exposing the seam.
6. **Default-on or opt-in?** OPT-IN. `--worktree-path` is absent by default — falls back to the marker-resolved workspace (back-compat preserved).

**Litmus — per-product code count:** **0 lines.** Both follow-ups are cross-product detector/CLI hygiene; no product changes.

---

## 4. Scope (two follow-ups combined)

### Part 1 — `keeper-cli-worktree-arg`
- Add `--worktree-path PATH` (with `--root` alias) to `mcp/noctusai/cli.py`.
- When present, rebind `settings.REPO_ROOT` + `settings.PRODUCTS_DIR` BEFORE any `tools.*` import.
- For `--review`: additionally pass `products_dir=` explicitly to `run_review()` (belt-and-suspenders).
- Validation: missing/nonexistent path exits non-zero with a clear message; alias works; default behavior unchanged.

### Part 2 — `keeper-detector-supersession-tuning`
- Add `or_replace` named group to `_CREATE_FUNCTION_START_RE`.
- Rewrite `check_function_search_path_pinned`: two-pass — collect all blocks per qualified-name in lexical-file order (Pass 1); flag only the LATEST block per name lacking `SET search_path` (Pass 2).
- Backward-compatible: every existing test must continue to pass.

---

## 5. Files touched

- `mcp/noctusai/cli.py` — added `--worktree-path` / `--root` arg + rebind block + explicit pass-through to `run_review()`.
- `mcp/noctusai/tools/noctus/dev/compliance.py` — added `or_replace` named group; rewrote `check_function_search_path_pinned` as two-pass supersession-aware.
- `mcp/noctusai/tests/test_compliance_prod.py` — added 4 supersession regression tests.
- `mcp/noctusai/tests/test_cli_worktree_path.py` — NEW, 5 CLI override tests via subprocess.

---

## 6. Phases

- [x] **Phase 1 — Part 1 (CLI `--worktree-path`).** Arg added, settings rebind wired, `--review` pass-through plumbed, 5 tests green.
- [x] **Phase 2 — Part 2 (supersession tuning).** Regex extended, detector rewritten two-pass, 4 new tests + 21 existing tests green (25 total in test_compliance_prod.py).
- [x] **Phase 3 — Verification.** Full mcp pytest pass + ERP delta measurement (9 → cleared).

---

## 7. Open questions

None — both fixes are well-scoped and the contracts are intact.

---

## 8. Risks

- **Rebind happening AFTER an early `tools.*` import** would silently fail. Mitigated by: (a) the rebind block sits immediately after `parser.parse_args()`, (b) every `tools.*` import in `cli.py` is INSIDE an `elif` branch (lazy), (c) we surface the override loudly via a yellow `worktree override:` print.
- **Lexical-filename order ≠ Postgres apply order**. In practice noc's migration convention is numbered `001_*.sql`, `011_*.sql` etc., so lexical sort matches apply order. If a product ever ships out-of-order names, the supersession detector could be wrong. Mitigation: noc's `_check_post_scaffold` already enforces single-001-migration-per-product (per `feedback_single_001_migration.md` memory rule).

---

## 9. Improvements discovered during this work

None significant — both gaps were well-scoped and the fixes landed cleanly.

---

## 10. Verification commands

```bash
# Worktree-relative invocation now works:
python mcp/noctusai/cli.py --review --product erp-imobiliario \
  --worktree-path /Users/rapha/Documents/repository/NoctusAI/noctusai/.claude/worktrees/agent-a6f60c6da6293f5b3

# Regression suite:
cd mcp/noctusai && \
  PYTHONPATH="$(pwd)/../../seed/lib/backend:$(pwd)" \
  python -m pytest tests/test_compliance_prod.py tests/test_cli_worktree_path.py -v
```

---

## 11. Change log

- **2026-05-11** — Engineer MMM: Phase 1 + Phase 2 shipped same session. CLI `--worktree-path` / `--root` arg + settings rebind; supersession-aware `check_function_search_path_pinned`. 4 new supersession tests + 5 new CLI tests; 30 tests total pass in the touched files. ERP residual findings cleared (9 → 0 in the supersession class).
