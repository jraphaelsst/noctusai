# Compliance regression-baseline gate

> Filed 2026-05-18 — Option A of `projects/platform-compliance-baseline`
> §7(A), locked by the user. Self-contained (durable-docs rule); references
> code paths + dated facts, never the project slug.

## The problem it solves

`check_all_products()` returns `(score, issues)` where each product's score
is `max(0, 100 − Σ severity-penalties)` averaged across the fleet. The
methodology-codification pipeline keeps *adding* keeper detectors (working
as designed), each retroactively surfacing **pre-existing** debt. So an
absolute `assert score == 100` gate is **aspirational, not a regression
detector** — it goes red the moment any new detector lands, independent of
whether the current change regressed anything. CI then either blocks every
unrelated PR ∨ gets `--no-verify`'d into noise.

## The pattern — regression semantics + informational score

s1 **GATE = no NEW high/critical issue vs a committed baseline.** A
fingerprint set of the current high/critical issues is committed
(`mcp/noctusai/tests/compliance_baseline.json`). The gate test computes the
live high/critical fingerprint set and asserts `live − baseline == ∅`. A
NEW high/critical issue (regression) fails; pre-existing debt does not.

s2 **Absolute score is INFORMATIONAL.** The gate test still calls
`check_all_products()`, but the absolute `score` is `print`ed (visible in
`-s` / CI logs), **never asserted**. It is a tracked metric, not a contract.

s3 **Fingerprint = line-churn-robust identity.**
`"<product>|<file>|<severity>|<symbol>"` where `<symbol>` is the backticked
``patches our own symbol `X` `` token when present, else the issue text's
first 80 chars with digits → `#`. Refactors that shift line numbers do not
flap the gate; a genuinely new violating site does.

s4 **Non-deterministic env-artifact classes are excluded** from BOTH the
baseline and the live set so the gate cannot flap on wall-clock / stamp-lag:
`Seed drift:` (seed-version stamp lag — pre-commit HEAD vs post-commit SHA),
`Archive entry` (archive-staleness, date-relative), `Dispatcher`
(dispatcher-staleness, date-relative). Single source of truth:
`is_env_artifact` / `ENV_ARTIFACT_PREFIXES` in
`mcp/noctusai/tests/refresh_compliance_baseline.py`, imported by the gate.

## Refresh contract

The baseline is **deterministic ∧ regenerable**:
`mcp/noctusai/.venv/bin/python mcp/noctusai/tests/refresh_compliance_baseline.py`
(from repo root) re-emits a byte-identical set from the real
`check_all_products()`. Refresh ONLY when:
- debt is intentionally **resolved** → baseline **shrinks** (good);
- a new pre-existing class is **triaged-and-accepted** → baseline **grows**,
  and the commit message MUST cite the triage decision ([A] entry).

Never refresh to silence a *regression* — that re-introduces the silent-error
shape the gate exists to prevent. The regenerator and the gate import the
same `fingerprint` / `is_env_artifact` so the fixture and the check can never
drift apart.

## Working-tree sensitivity — verify on a clean worktree before chasing

`check_all_products()` walks the **filesystem** (`PRODUCTS_DIR.iterdir()`),
**not** git's committed state. So this gate reads whatever is on disk —
including a **peer agent's uncommitted files** on a shared/busy checkout. On a
multi-terminal workspace that produces a **phantom regression**: the gate
reports a NEW high/critical fingerprint that is NOT in committed `origin/dev`
— it is a sibling's in-flight file. *(Bit 2026-05-25: an agent reported these
2 tests "failing"; on a clean `origin/dev` worktree both were green —
peer in-flight files on the busy primary checkout.)*

**Rule:** when this gate is red on a shared/busy checkout, before chasing it
as committed debt, **re-run it on a clean checkout of `origin/dev`** (an
isolated `task_branch` worktree gives one) **∨** confirm `git status` shows
no peer-uncommitted files under `products/`. The clean-worktree reading is
authoritative. This is one instance of the general worktree-sensitivity map —
see [[branching]] §2 (the tools that read the working tree + the safe
protocol).

## Baselined debt must carry a reason (2026-09-18)

Three rules, codified after the `validate_schema=False` inventory pass
(`erp-imobiliario` / `therapy-platform` / `adconnect` — the class behind
the erp.assinaturas.external_id / erp.tool_call_audits / erp.llm_preferences
production bugs: three real schema gaps hid behind the opt-out flag
precisely because nobody ever tried turning it back on and writing down
what happened):

1. **A baselined finding must carry a recorded reason.** A baseline entry
   with no reason is not accepted debt — it is forgetting with extra
   steps. For `validate_schema=False` specifically, `check_mock_schema_validation`
   makes this MECHANICAL, not just a documentation convention: the keeper
   scans the FULL `backend/tests/` tree (widened 2026-09-18 — the original
   scan covered only `conftest.py`) and flags any `validate_schema=False`
   site whose OWN file has no rationale comment naming
   `schema-drift`/`reconciliation`/`follow-up`/`TODO`. An unexplained
   opt-out fails compliance directly — there is no "baseline it silently"
   escape hatch for this specific class; the reason must be co-located in
   the file, not merely known to whoever wrote it. Other debt classes that
   lack an equivalent mechanical detector still rely on the discipline
   (cite the triage decision in the refresh commit, per § Refresh contract
   above) — say so plainly rather than implying this doc alone enforces it
   fleet-wide for every keeper.

2. **When re-enabling a suppressed check FAILS, that failure IS the
   finding — never force it green.** The correct response to "I flipped
   `validate_schema=True` and it broke" is: revert to `False`, record
   EXACTLY what broke (the real `MockSchemaError` — table + column +
   which code path hit it), and leave the opt-out with that now-verified
   reason. Do not paper over a genuine schema gap by adjusting the mock's
   seed data or loosening an assertion to make the flip "pass" — that
   converts a named, understood gap into a silent one, which is the exact
   erp-class failure mode this rule exists to prevent.

3. **Never sweep.** A single change across N products for one reason is
   the "no quick fixes / wrong level" shape (`KB § 01-PHILOSOPHY.md`).
   Flip one product's opt-out, run THAT product's own suite, decide
   (revert-with-reason or keep-remediated), THEN move to the next. The
   2026-09-18 pass did exactly this across 6 products serially — 3
   genuinely could not be re-enabled (adconnect, erp-imobiliario,
   therapy-platform — each confirmed by an empirical flip-and-observe,
   not by re-reading a stale comment) and 3 had NO real gap at all
   (agents, social-wiring, personal-finance — the opt-out was pure
   unexplained debt with zero cost to remove; social-wiring's additionally
   needed `schema="social_wiring"` added, since the mock was silently
   NOT validating at all — an unqualified schema is an unknown-table
   WARN+skip, not a real absence of drift).

## Where it lives

- Baseline fixture: `mcp/noctusai/tests/compliance_baseline.json`
- Regenerator + shared identity fns: `mcp/noctusai/tests/refresh_compliance_baseline.py`
- The 2 gate tests: `mcp/noctusai/tests/test_compliance.py`
  (`TestSeedCompliance::test_all_products_compliant`,
  `TestAIFeatureCompleteness::test_real_products_pass_validate`)

The two *remediation* conventions for draining the baseline (so it can
shrink) are formalized separately:
`§ CONTEXT/PATTERNS/backend/di-test-seam.md` (the `test_patch_target` /
self-monkeypatch class) and `§ CONTEXT/PATTERNS/backend/logging-at-except.md` (the
silent-except class).

## Keeper-delta gate — the integrate-budget slice of this baseline (2026-10-10)

`test_all_products_compliant` runs `check_all_products()`: every keeper over every product, ~4.5 min. No integrate merged-tip budget (~90s) fits that, so a NEW keeper that went red on EXISTING files elsewhere in the tree timed out unmeasured and landed. The case: `check_migration_number_refs_in_tests` vs a social-wiring test, plus its unregistered regression tests.

When `compliance.py` is in a diff, `gate_sweep` now schedules two seconds-scale gates FIRST, ahead of any long suite:

- **`keeper_meta`**: `TestCheckDetectorHasRegressionTest` (~5s). A new `check_*` must ship a `class TestCheck<Name>`.
- **`keeper_delta`** (`--check-keeper-delta`, `tools/noctus/dev/keeper_delta.py`, ~1s): this baseline's judgement, restricted to the keepers the diff can have affected.
  - Which keepers: those whose AST differs from the merge-base, plus keepers that call a changed helper.
  - How each is called: derived from `check_all_products()`'s own body (per-product vs global).
  - What fails: any high/critical, non-env-artifact fingerprint not in `compliance_baseline.json`. It uses the regenerator's own `fingerprint` / `is_env_artifact`.
  - A changed keeper that the aggregator never calls is reported as `not_aggregated`; it is never silently passed.

The full `test_all_products_compliant` still runs in CI and the full toolkit suite. `keeper_delta` is the early, budget-fitting proof, not a replacement.

Related: a non-`.py` file under `mcp/noctusai/tests/` (a fixture or a baseline .json) now maps to the test files that name it. It no longer forces the full toolkit suite, which was what pushed that integrate into its timeout.

## 2026-10-10 — environment-state keepers are excluded by construction

`test_all_products_compliant[<platform-global>]` flapped (red ~2 of 4 runs, identical trees): a cache-freshness keeper reported `<name> cache missing` (machine-local keeper-mirror cache, present or not depending on what peer sessions had refreshed), a text variant the `"cache STALE"` substring exclusion did not cover. Root fix, not another substring: keepers whose verdict is machine/shared-git/date/cache state (`*_cache_freshness`, `check_git_leftovers`, `check_branch_orphan`, `check_archive_staleness`, `check_dispatcher_staleness`, `check_prod_cache_reachable`) are wrapped in `@env_state_keeper`, which stamps `"env_state": True` on every issue; `is_env_artifact_issue` (baseline helper, used by the gate and the regenerator) honours it. A new machine-state keeper gets the decorator, never a new text entry. The keepers behave unchanged for CLI / pre-commit / `validate`.
