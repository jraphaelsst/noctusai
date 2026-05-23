# findings.md — seed-deploy-config-contract

> What we LEARNED (curated). Append in-the-moment; synthesize at close.

## Knowledge / process

- **Branch-naming collision under a leaf integration ref (METHODOLOGY BUG).** Worker branches named `feat/<project>/<slice>` are **impossible** when the integration branch is literally `feat/<project>` — git refuses a nested ref under an existing leaf (`cannot lock ref ... 'feat/<project>' exists; cannot create '.../<slice>'`). Engineer A hit this and correctly fell back to the hyphen sibling `feat/<project>-<slice>`. Root cause = our naming shares a prefix where the integration IS a leaf; KE avoided it by using *distinct* prefixes (`methodology-dev` integration + `feat/<name>` workers). **Fix → fold into `branching-dispatch.md`:** integration branch and worker branches must NOT share a leaf-prefix — either name the integration branch distinctly (`int/<project>` or `<project>-integration`) OR worker branches use the hyphen form `feat/<project>-<slice>`. `[→codify: branching-dispatch.md]`

- **Harness `isolation: "worktree"` forks from `main`, not the current working-branch HEAD.** Engineers' fork base = `eb7c952a` (main), NOT my integration tip `3952121b` — so the worktrees did NOT carry PROJECT.md or the branching-dispatch absorb. Harmless here (each slice is new files → merges cleanly onto the integration tip), but: (a) `dispatch_preflight project_slug=...` is moot for these engineers (the doc isn't on their base); (b) briefs must be self-contained (A's was — full API inline — so it didn't block). `[→codify: branching-dispatch.md — note the fork-base behavior + self-contained-brief requirement]`

- **Worker test-env in an isolated worktree.** No venv/node_modules in the worktree (gitignored). Engineer A verified by running the **main checkout's** mcp venv python with the **worktree on `PYTHONPATH`** so its NEW `deploy_config.py` shadowed the editable install (confirmed: imported the worktree path, not site-packages). 17 tests passed. This invocation works for pure-Python slices; the architect re-verifies authoritatively at merge.

## Triage / accept

- **[A] env-pin preflight BLOCK overridden (accept-with-rationale).** `dispatch_preflight` BLOCKed on `starlette 1.0.0` vs seed cap `<0.42.0`. Override rationale: (1) no Wave-1 slice imports starlette (verified — the `fastapi` refs in slice B's files are string fixtures + comments); (2) `starlette 1.0.0` is `Required-by: fastapi, mcp, sse-starlette` — the MCP-server stack legitimately needs it; (3) the suggested `force-reinstall -e seed/lib/backend` would downgrade starlette and **break the MCP runtime**. Underlying nit (seed-lib editable's product-cap `<0.42.0` coexisting in the MCP venv that needs 1.0.0) = separate follow-up, NOT fixed by downgrading.

- **Cross-tree overlay LEAK at integration (recovered).** After all 3 merged-ready, the MAIN checkout's working tree showed `M compliance.py` + an untracked `deploy-config-contract.md` — the engineers' in-progress edits **leaked from their isolated worktrees into the main tree** via the harness overlay, AND the leaks **differed** from their committed branches (`git diff origin/<branch> -- <file>` non-empty; the compliance.py leak sat at line 5994, an intermediate copy). Recovery (per [[harness-overlay-worktree-divergence]]): the committed+pushed branches are source-of-truth → `git checkout -- compliance.py 02-LANDSCAPE.md` + `rm` the untracked doc → merge the branches `--no-ff`. Authoritative re-verify in the main checkout (co-located) all green. `[→codified: branching-dispatch.md §2 ⚠ cross-tree overlay leak]`

- **Cross-tree `REPO_ROOT` meta-keeper artifact (B).** Running `check_detector_has_regression_test` from a worktree resolves `settings.REPO_ROOT` to the MAIN tree → the detector (`__file__`=worktree) and the test-glob (MAIN tree) see different trees → false "no regression test". Vanishes co-located (confirmed: 0 complaints after merge in the main checkout).

- **Keeper seed-`tests/` exclusion (B, surfaced).** `check_derives_from_dev_only_artifact` excludes seed `tests/` — seed test fixtures legitimately call `parse_products_registry` to exercise the parser (8 would false-hit). Keeps the live baseline a clean 0. Architect-accepted.

- **Branch-naming N=3** — all three engineers hit the slash-vs-leaf-ref collision, self-corrected to the dash form. Folded into `branching-dispatch.md` §2 ⚠ + the §2 worktree-forks-from-main note.

## Status

- ✅ Engineer A — `deploy_config.py` + test (17 pass authoritative); merged `81fc3cf0` `--no-ff`.
- ✅ Engineer B — `check_derives_from_dev_only_artifact` + test (6 pass, meta-keeper 0, live baseline 0, `cors_registry` not flagged); merged `7abbc67c` `--no-ff`.
- ✅ Engineer C — `deploy-config-contract.md` (symbol-clean, API matches A verbatim); merged `970dc522` `--no-ff`. Architect wired INDEX/CLAUDE rows at reconciliation.
- ⏳ Wave 2 — startup guard (opt-in `required_prod_config` param on `create_product_app`) + erp pilot.
- 🔒 main — gated until Wave 2 + reconciliation green; present integration→main for user go.
