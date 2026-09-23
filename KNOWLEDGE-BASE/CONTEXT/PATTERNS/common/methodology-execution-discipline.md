# Methodology execution discipline — close the loop, work within the grain, learn from gating

> **The behavioral half of the prevention system.** The branch-hygiene + learn-before-archive *machinery* (keeper / sweep / salvage gate) is the safety net that catches drift after the fact. This discipline is how agents *behave* so the net rarely has to fire. One of a **complementary pair** with `KB § PATTERNS/common/product-dev-learning-ground.md` — see "The two axes" below.

Born 2026-05-30: ~330 dangling remote branches + an embedding-refresh tax + a history of `--no-verify` rationalizations had accumulated. Every one traced to a *behavioral* gap, not a missing tool. The tools were then built; this codifies the behavior.

## The principles

### 1. Close the loop — "works" ≠ "done"
A task is done only when **nothing dangles**: branch integrated-or-salvaged, `origin` branch deleted post-integration, worktree removed, docs + caches synced, no orphan ref / pointer / temp file. **Whoever pushes a branch owns its cleanup on integration** — pushing for durability without later deleting is the literal source of the orphan-branch pile-up. The close-out checklist:
- branch merged (or salvaged-then-deleted per learn-before-archive) ·
- `origin/<branch>` deleted once content is confirmed on `dev` ·
- worktree removed (`git worktree remove`) ·
- docs/KB/INDEX synced, caches fresh (the hooks handle most) ·
- no `NOC-REMEDIATE` left without a named destination.

Backstopped by `check_dangling_remote_branches` + `session_end_sweep` (remote section) + the guarded `delete_integrated_remote` tool — but the *default* is to close the loop yourself, not lean on the net.

### 2. Work within the grain — know the gates before you act
The gates are knowable, so anticipate them and execute cleanly instead of tripping them mid-flight:
- **CLAUDE.md word cap (~2500) + pointer-only §1** — check the budget before adding a §1 line; trim a verbose line if needed (its detail lives at its KB pointer). → `KB § PATTERNS/common/claude-md-router-discipline.md`
- **pre-commit keepers** — `kb_sync` (every KB doc indexed, pointers resolve), `check_claude_md_router`, `check_eight_way_sync`, cache refreshes. Author docs from the live keeper contract (`keeper_pattern_lookup`) before writing.
- **change-gated pre-push** — a delete-only / no-source push skips the embed refresh; a source change refreshes only the affected caches. Don't expect (or wait on) a full refresh that won't run. → `KB § PATTERNS/common/push-time-embedding-gate.md`
- **branch protection** — `main`/`prod` are gated; everyday work + pushes land on `dev`.

A gate you could have foreseen tripping is a **planning miss**, not bad luck.

### 3. A fired gate is a learning event, never a bypass target
When a keeper / budget / wall fires: **STOP → understand WHY → fix correctly OR surface to the tech-lead → codify if it is a recurring shape.** Never `--no-verify`, never fight the linter/budget, never blind-delete. This sharpens "safety nets capture failures → learnings → methodology evolves" into an *operating* rule: the firing is signal, and the response is to learn, not to route around. Worked example (2026-05-30): a recurring `vector-costs.ndjson` merge conflict was fixed at the root with a `merge=union` gitattribute rather than re-resolved by hand each time. → `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md` · `KB § PATTERNS/common/background-engineer-safety-discipline.md`

### 4. Prove the check can FAIL — a green that cannot go red proves nothing

Writing a guard is not the same as having one. Before trusting any new test, gate, assertion or
detector, **break the thing it guards and watch it fail**. If it still passes, it is not a guard —
it is decoration that will report success forever, including on the day the defect ships.

The negative control is one command and it is not optional for anything guard-shaped:
```
# 1. guard passes on healthy code           → expected
# 2. remove/corrupt the guarded property    → the guard MUST now FAIL
# 3. restore                                → guard passes again
```
Step 2 is the whole point. A guard that skips it has never been tested — only *run*.

**Worked example (2026-08-03).** An agent diagnosed a "silent false-green" (worktree tests
resolving another tree's seed lib), built a `pytest.ini` `pythonpath` pin, fanned it across 11
products + the seed template, and wrote 12 guard tests. All 12 passed. Then the negative control:
remove the pin → **the guard still passed**. That single red-that-wasn't exposed the truth — every
product's `tests/conftest.py` had solved this in May, the diagnosis was wrong (it came from a bare
`python -c` probe, which does not load conftest), and the entire mechanism was a duplicate. All of
it was reverted *before* commit. Without the negative control, a fork of an existing seed mechanism
would have shipped fleet-wide with a full green suite vouching for it.

⇒ **A passing new guard is a hypothesis until you have seen it fail on purpose.**

### 5. Search for prior art BEFORE designing a fix — source-of-truth applies to solutions

"Codebase is source of truth" is usually read as *verify facts against the tree*. It applies just as
hard to **solutions**: before designing a mechanism, grep for the one that already exists. The most
expensive bug is not a wrong fix — it is a *correct* fix for a problem someone already solved,
because it lands as a second mechanism doing the same job, i.e. a fork, and both drift from then on.

The check is ~30 seconds and precedes design, not review:
- `grep` the obvious host files (`conftest.py`, the seed lib, the product's own module) for the
  concept you are about to implement;
- `noctus.dev.code_search` / `find_reusable_component` for the fuzzy-intent version;
- read the sibling product that hit this first — fan-outs leave comments naming their origin
  (the May shim literally said *"mirroring ERP-P7's reference fix"*).

Trigger phrases that should stop you cold and send you grepping: *"this needs a mechanism"*,
*"I'll add this to every product"*, *"the seed should handle this"*. All three are
replication-to-seed-symmetry language — the right count of new mechanisms is usually **zero**.
→ `KB § PATTERNS/architect/project-execution.md` (replication-to-seed symmetry)

⇒ **Design starts with a grep, not a blank file.**

## The two axes (complementarity thesis)

This rule improves **how we WORK** (process). Its complement, `KB § PATTERNS/common/product-dev-learning-ground.md`, improves **how we BUILD** (product craft). Same core mindset — *friction is a learning event* — applied to two grounds:

> **Neither alone is enough: a perfect methodology building products with un-compounding technique still stagnates, and great technique on a leaky process still drifts. Together they make the system get better on BOTH axes every time we touch it.**

They are two flywheels; the org compounds only when both spin. Always read/codify them as a pair.

## Composes with
- `KB § PATTERNS/common/product-dev-learning-ground.md` — the craft-axis complement.
- `KB § PATTERNS/common/learn-before-archive.md` — the pre-delete salvage gate (close-the-loop's "salvage" leg).
- `KB § PATTERNS/common/drift-fix-on-contact.md` · `storage-hygiene.md` · `persistent-files-absorption.md` — the hygiene rules this operationalizes.
- Roadmap: `project-history/roadmaps/branch-hygiene-and-learn-before-archive-2026-05.md`.

### 6. Verdict-channel integrity — the exit code you READ must be the one you are JUDGING

Principle 4 says a green that cannot go red proves nothing. This is its
sibling failure: the check *did* go red, and the channel carrying the verdict
lied about it.

Every one of these was a real misread, not a hypothetical:

| Channel | What it reported | What was true |
|---|---|---|
| `cmd \| tail` | tail's status (always 0) | the command had failed |
| `gh run watch --exit-status` | `0` | the run was `completed failure` |
| a backgrounded compound command | the wrapper's exit (a trailing `grep`) | pytest inside had exited 1 |
| `deploy_image` timing out (2026-08-13) | nothing — the call went quiet | prod was still serving the old image |
| `noctus.dev.pytest` without `worktree_path` | "689 passed" | the WORKTREE's suite never ran |
| `migrate_product` dry-run (2026-09-17) | a confident pending-migrations list | the primary was 26 commits behind `origin/dev` and didn't even contain the migration being deployed — see `KB § PATTERNS/backend/migrate-product-mcp-tool.md` § Stale-tree refusal |
| "every gate green on the merged tip" (2026-09-17) | seed suite + both product suites, all green | `mcp/noctusai/tests/` was never run at all — CI then found 3 real failures there. Not a wrong RESULT; a claim about a SET made without checking the set was COMPLETE |
| `if git merge --no-edit -q "$b" 2>&1 \| tail -1; then` (2026-09-17) | "CONFLICT" | the merge had succeeded; the condition read `tail`'s exit status, not `git merge`'s |
| `npx tsc --noEmit 2>&1 \| tail -5 && echo "tsc-rc=$?"` (2026-09-17) | printed as the gate's result | `$?` there is `tail`'s — same session, an hour apart from the row above |
| `noctus.dev.task_branch payload={action:'start',…}` (2026-09-19) | `ok: true` + a 32-worktree listing | **no worktree was created.** `payload` is not a parameter of that tool; FastMCP registers its handler with `validate_input=False`, so the unknown key was dropped and every declared parameter fell back to its default — and that tool's default `action` is the READ-ONLY `"status"`. Four consecutive calls "succeeded" doing nothing. The messenger here is the **argument binder**: it answered a question nobody asked. Closed by `install_strict_tool_arguments()` (refuses unknown args) + keeper `check_mcp_tools_reject_unknown_args` |

The shape is constant: **a messenger's status was mistaken for the subject's
status.** A pipe, a wrapper, a watcher, a notification and a timeout are all
messengers. Two of the five above happened in a single session (2026-09-02),
by the same agent, an hour apart — which is what moved this from "be careful"
to a named rule.

**Silence is the sharpest case.** A call that times out or disconnects has
reported *nothing*, and nothing is not a pass. `noc-ship` states this
explicitly for `deploy_image` — "that is NOT success by default" — and the
same reading applies to any tool that goes quiet.

**In practice**
- `set -o pipefail`, or capture `rc=$?` immediately, before any formatting.
- Prefer a **structured runner** over a shell pipeline: `noctus.dev.pytest`
  returns a verdict object with `resolved_root`, so there is no status to
  misattribute. This is compliance-by-construction — removing the channel
  beats reading it carefully.
- For CI, read the **run conclusion** (`gh run view --json conclusion`), never
  a watcher's own exit.
- When a call goes quiet, get ground truth from an independent witness
  (`noctus.dev.deploy_verify` exists precisely for this) before concluding
  anything.
- **The SET is a channel too.** "Every gate green" is only true if the
  set of gates that ran is the set that was actually applicable — a
  remembered set silently drops the one nobody thought to run.
  `noctus.dev.gate_sweep` is the structural fix on THIS axis: it derives
  which gates apply from the diff (never from memory), runs each as its
  own subprocess with its own `.returncode`, and can only report
  `status="green"` when every applicable gate has `ran=True AND
  exit_code==0` — a gate that never ran forces `status="incomplete"`,
  never `"green"`. Same posture as `noctus.dev.deploy_verify` on the
  silence axis above: replace the remembered claim with a measured one.
- The statically-visible half of the piped-`$?`/`if`-on-a-filter shape —
  `check_piped_exit_code_pattern` (`--check-piped-exit-code-pattern`) —
  scans every `.sh`, the `scripts/hooks/` entrypoints, and
  `.github/workflows/*.yml` `run:` steps for exactly the two 2026-09-17
  rows above (`$?`/if/&&/\|\| read off a pipeline whose last stage is
  `tail`/`head`/`grep`/`sed`/`awk`/`cat`), and separately flags a script
  that has the shape with no effective `pipefail` backing it (severity
  escalates from "fragile" to "definitely wrong").

**2026-09-23 — the merged-tip re-run is now automatic, not a remembered
step.** Fifteen `fix(ci): green the merged tip` commits are the evidence
"per-branch green ≠ integration green" (§1) was routine to forget, not
exceptional: a branch green on its OWN base still broke once rebased onto
what everyone else had landed meanwhile. `noctus.dev.task_branch(action=
'integrate')` now calls `gate_sweep` itself, scoped (`base_ref=origin/dev`,
the exact ref it just rebased onto) and time-boxed (default ≤90s overall,
`merged_tip_timeout=`), AFTER the rebase and BEFORE the push. It refuses
the push ONLY on a gate that both (a) actually failed on a valid harness
(no `harness_suspect`) and (b) is plausibly CAUSED by this branch's own
diff — a product gate pulled in ONLY by this branch's own `seed/`-triggered
fleet-wide fan-out, on a product this branch never touched, does not block
(the same "the collision belongs to whoever merges second" reasoning
`check_migration_number_collision`'s Leg A/B split already applies one
layer up, for migrations). `inconclusive` / `incomplete` / a timed-out gate
push anyway, reported under the `merged_tip_check` result key — "cannot
measure" pushes, exactly like a pre-existing red does, because acting on an
unmeasurable red is the § 6 mistake at integrate time. Opt out with
`verify_merged_tip=False` for a doc-only slice. See
`mcp/noctusai/tools/noctus/dev/task_branch.py`'s module comment above
`_merged_tip_red_is_new`.

NOC-REMEDIATE[codify]: the piped-`$?`/pipe-into-filter half shipped as
`check_piped_exit_code_pattern` (2026-09-17, this row). `gh run watch
--exit-status` used as a gate remains deferred — a genuinely different
shape (a watcher's own wrapped exit, not a piped tail/head) worth its own
detector when an instance actually recurs, not force-fit into this one.
The live-agent half (a tool call in a session transcript, e.g. the `npx
tsc | tail -5 && echo "$?"` row above) stays out of a tree-walking
predicate's reach by construction — `gate_sweep` addresses that half
structurally (no channel to misread) rather than by detection. — 2026-09-17

### 7. A stale interpreter is verdict-channel integrity ONE LEVEL UP — the code you are JUDGING must be the code on disk

Principle 6 says the exit code you read must belong to what you are judging.
This is the same failure one layer down the stack: even a perfectly-read
exit code is worthless if the CODE that produced it was never asked the
current question.

`mcp/noctusai` is imported once, into `sys.modules`, by a long-lived MCP
server process. Python does not re-read a module's file after that — editing
a tool's `.py` on disk does nothing to the code already resident in memory.
The 2026-09-18 incident: a server had been running since 2026-09-16 18:45;
`task_branch.py` was last modified 2026-09-18 01:15. For ~30 hours every
`noctus.dev.*` call — including `predeploy_check`, `deploy_verify`,
`spa_smoke`, `migrate_product` and `task_branch` itself — executed two-day-
old code, and **nothing anywhere surfaced that.** Concretely:
`task_branch action=start` silently stopped provisioning worktrees (the
loaded code predated `wire_env`), so every worktree created that day lacked
`.env` / `node_modules`, which then made a colocated test fail in a way an
engineer reasonably — and wrongly — called "pre-existing."

The shape is identical to principle 6's table: a messenger's status was
mistaken for the subject's status. Here the messenger is the INTERPRETER
itself — its answer was read as current when the code producing it was not.

**In practice**
- `noctus.dev.toolkit_freshness` detects it: at server-startup completion it
  freezes `{path: (mtime, size)}` for every `mcp/noctusai` module actually
  loaded (`sys.modules`, not a blind filesystem walk — the question is "what
  did the process load," not "what exists on disk"), then re-stats on demand.
  TTL-cached (default 5s) so a burst of tool calls costs one stat pass, not
  one per call.
- **Refuse vs. warn is drawn at "can a stale version silently produce a
  plausible-looking wrong result?" — not "does this write to production."**
  "Writes to production" was the first-pass proxy and it was wrong: it would
  have left `task_branch` — the tool that CAUSED this incident — in the
  warn-only bucket, because a worktree/branch on `dev` isn't production. But
  a stale `task_branch action=start confirm=True` is the textbook case the
  rule exists for: it returned `status: "started"`, exit 0, and a worktree
  that LOOKED fine, while silently skipping the `.env`/`node_modules`
  provisioning — a full day of engineer dispatches ran against unprovisioned
  trees before anyone noticed, and it manufactured phantom red tests a
  competent engineer then reasonably mislabelled "pre-existing." Nobody knew
  there was anything to recover, so "recoverable via `mole`" was never the
  relevant axis either. So: `task_branch`'s MUTATING actions (`start` /
  `integrate` / `cleanup`, `confirm=True`) REFUSE when stale, same as
  `migrate_product` / `release` / `deploy_image`'s `confirm=True` write —
  `action='status'` (never inspects `confirm`) stays warn-only, as does any
  `confirm=False` preview across all four tools (a preview that never
  mutates anything is safe to still answer, loudly labelled, rather than
  refuse outright — refusing it would make "let me just check the plan"
  useless while stale). `predeploy_check` / `deploy_verify` / `spa_smoke`
  have no write path at all, so they are warn-only unconditionally. Every
  REFUSE case is `status='refused_stale_toolkit'` (mirroring
  `migrate_product`'s own `refused_stale_tree` vocabulary) unless the caller
  explicitly passes `allow_stale_toolkit=True` (recorded on the return,
  never silent); every WARN case carries `toolkit_stale: true` + a loud
  `warnings` entry naming the remedy (never silently as-if-current).
- **The remedy is always a restart, never a hot-reload.** Swapping code
  under a live module graph mid-call is a worse failure mode than reporting
  staleness — `/mcp` in Claude Code re-imports the toolkit from disk.
- A stale verdict must never be silently swallowed — same no-silent-errors
  posture as principle 6's "silence is the sharpest case," applied to the
  interpreter's own currency instead of a command's exit status.

See `mcp/noctusai/tools/noctus/dev/toolkit_freshness.py`. — 2026-09-18

### 8. Structure-green is not behaviour-green — a guard is verified only by observing it REFUSE

> Rebase note: this section was originally authored as §7, at which point
> §7 above ("a stale interpreter...") did not exist on any reachable ref —
> confirmed by fetching `origin/dev` at the time. It has since landed;
> this section is renumbered §8 on rebase, content otherwise unchanged.

Principle 4 says a green that cannot go red proves nothing; principle 6
says the channel carrying a verdict can lie even when the check itself is
sound. This is a third, distinct failure mode: the check confirms the
guarded OBJECT exists, and reports that as if it proved the object DOES
anything. It does not. A trigger, a CHECK constraint, an RLS policy — each
can be declared, migrated, and structurally scanned as "present" while
never once having been exercised.

**All four found in one day (2026-09-17), each independently:**

| Check | Reported | Reality |
|---|---|---|
| "RLS enabled, 17 policies on `storage.objects`" | green | the bucket was `public = true`; `/object/public/…` bypasses RLS entirely. 102 CPF-bearing certidões were world-readable. |
| `install-hooks.sh` allowlist in a keeper | green | shell variable indirection meant it matched nothing — the exemption was dead code |
| a migration test for a write-once trigger | green | it greps `pg_get_functiondef` for the RAISE text; it never fires the trigger |
| a docx assertion | green | `\n` renders as `<w:br/>`, so the asserted substring could never appear either way |

The honest root cause is not carelessness — for the database case
specifically, there is no dev/staging fleet to exercise a guard against
(`KB § PATTERNS/devops/dev-fleet-dormant.md`), so a migration test is
structural BY NECESSITY, and every reviewer has accepted that as the best
available proof. It is not: existence is not behaviour.

**The fix, not just the diagnosis.** `noctus.dev.verify_db_guards` runs the
EXACT operation a declared DB guard claims to refuse, against production,
inside a transaction that is rolled back by construction (not by
convention — see that tool's `wrap_rollback_only` for the three
independent reasons a probe run through it can never commit). The refusal
IS the pass; an operation that SUCCEEDS is the finding, at whatever
severity the guard's own rationale names. `noctus.dev.predeploy_check`'s
`db_guards` leg composes it, fail-closed like every sibling live-DB leg
(`schema_exposure` / `schema_drift` / `storage_bucket_public`) — "we
couldn't verify" is never read as "it's fine". The gate↔methodology-sync
backstop is `check_migration_guard_has_probe`: a migration that ships a
NEW trigger/CHECK/UNIQUE guard with no registered probe is blocked at
commit time, so this does not quietly regress the moment the next guard
ships.

⇒ **A structural check that a guard exists is a hypothesis about its
behaviour, not proof of it — proof requires watching it refuse.**
### 9. Resolve the root from the artefact under evaluation, never from the ambient cwd

`Path.cwd()` and "wherever this module's `__file__` happens to resolve"
both FEEL like reasonable defaults for "which tree am I working against,"
and both are wrong the moment the process running the check and the tree
being checked can differ — which a worktree fleet guarantees will happen
routinely, not exceptionally. This is the wrong-tree family
(`project-history/roadmaps/julia-agents-academia-2026-09.md` calls it
"tool drift (wrong-tree family, N≥5)" for a narrower slice of it); the
root-resolution shape specifically has now recurred at N≥4:

1. **`noctus.dev.migrate_product` / `tunnel_config check`** reading the
   MCP server's stale PRIMARY checkout regardless of which worktree the
   caller was actually standing in — `tunnel_config check` reported
   `in_sync` while the live tunnel lacked both hosts; `migrate_product`
   listed no agent `009`. Both tools now accept `worktree_path` and pin
   resolution to it explicitly rather than defaulting to cwd or the
   server's own location.
2. **`absorption_tracking`'s ledger path** — a DELIBERATE instance of the
   same shape, not a bug: `LEDGER_ROOT` (never `REPO_ROOT`) is pinned to
   land in the PRIMARY checkout "even when the MCP server booted with cwd
   inside a worktree," because the ledger is repo-global and append-only
   — a worktree-relative resolution would fork it. Named here because the
   FIX in both directions is the same discipline: decide, explicitly and
   in one place, which root a tool means, and never let it default to
   "wherever the process happens to be standing."
3. **`noctusai_lib.testing._schema_cache._find_repo_root`, round 1**
   (2026-08-23) — walked up from `Path(__file__)` first. A worktree's
   tests, invoked WITHOUT PYTHONPATH scoped at the worktree, imported the
   PRIMARY checkout's `noctusai_lib`, so `__file__` landed in the
   primary; a column that existed only in the worktree's migration was
   silently "unknown" to the mock schema validator instead of failing
   the test that depended on it.
4. **The same function, round 2** (2026-09-18) — the round-1 fix had
   swapped the order to prefer `Path.cwd()`. Invoke pytest with an
   absolute path into a worktree's test file while the shell's cwd is
   still the PRIMARY checkout, using the sanctioned worktree-scoped
   invocation (which correctly scopes PYTHONPATH, so `__file__` now
   lands in the worktree) — cwd, checked first, won anyway. The mock
   built its schema from the PRIMARY's migrations while validating the
   WORKTREE's code: `MockSchemaError: ... has no column ...` for a
   column that plainly existed. The tests were right; the invocation
   (cwd left pointing at the primary) was not — and the resolver could
   not tell the difference because it never SAID two candidates
   disagreed.

N≥3 formalizes per the DRY recurrence rule (`KB § PATTERNS/architect/
project-execution.md`); this is 4. The invariant, stated once instead of
rediscovered per-tool: **whichever candidate is a FACT about what is
actually executing/being-evaluated (an explicit `worktree_path` /
`module_file` parameter, or — failing that — the importing module's own
resolved location) outranks whichever candidate is merely AMBIENT
(`Path.cwd()`, the shell's location, unrelated to what got loaded or what
is under test).** And per instance 4 specifically: a fixed precedence
order between two ambient-ish candidates will eventually be wrong in
BOTH directions as invocation shapes vary, so the fix is never "pick an
order and stop" alone — a genuine disagreement between candidates must
also be LOGGED, not resolved in silence, so the next mismatch costs a
log line instead of an hour of confused debugging. See
`noctusai_lib.testing._schema_cache._find_repo_root` for the worked
implementation (explicit override → explicit `start`/`module_file` →
artefact-under-evaluation → ambient cwd, with a loud warning on
disagreement). — 2026-09-18/19

### 10. Harness validity — a red is evidence about your CODE only if the HARNESS was valid

§ 6 says: read the exit code that belongs to the thing you are judging.
This is the failure **one step earlier**, and it is the more dangerous one
because *reading more carefully does not fix it*. The exit code genuinely
belongs to the command you ran. The command genuinely failed. And the
failure is about the **harness**, not the subject.

All seven of these are from ONE Playwright investigation, 2026-09-20:

| # | What the harness was missing | What the verdict looked like |
|---|---|---|
| 1 | browser binary never installed | "the test fails on 1.62.1" |
| 2 | browser revision **pruned** by installing a second `@playwright/test` version | "erp fails on 1.62.1 too" |
| 3 | the tree was 41 commits stale (primary never FF'd after integrate) | "7/7 green baseline" |
| 4 | my own `tail -8` ate the summary line | "1 passed" (it was `1 passed, 11 failed`) |
| 5 | worktree's `seed/{lib,framework}/frontend` had no `node_modules`, so vite never resolved the app | "11 tests failed" |
| 6 | no `env_bootstrap`, so no `SUPABASE_ACCESS_TOKEN` | "predeploy blocked" |
| 7 | `start.sh` absent from a staged tree, so the dev server never booted | "it reproduces on Linux" |

Not one of those verdicts described the code under test. Every one of them
looked exactly like one that did. Three of them were written down as
findings, and one of them — a disproven mechanism ("1.63 stops firing
`onMouseEnter`") — was shipped to production as a version pin.

**The rule.** A failing measurement asserts something about the subject
only once its preconditions are known to have held. Until then the honest
verdict is `inconclusive`, never `red`. *A red you cannot trust is worse
than no red, because you act on it* — you pin a version, you write down a
mechanism, and the real bug stays hidden behind the protection you just
added.

**In practice** — `noctus.dev.gate_sweep` implements both legs:
- **Preflight** (definitive): each `GateSpec` carries `Precondition`s —
  `node_modules`, each `file:`-linked `@noctusai/*` seed dep, the
  interpreter, `@playwright/test`. Unmet ⇒ the gate is **not run at all**,
  so there is no exit code to misread; it is reported `harness_invalid`
  with the missing path and a remedy.

  🔴 **A precondition must probe the PROPERTY, not a proxy for it.** The
  `node_modules` check started as "the directory exists" and was wrong
  within a day: `task_branch`'s `wire_env` links
  `node_modules/@noctusai/{lib,seed}` into a product even when it SKIPPED
  the base `node_modules` (the primary had none), so the directory existed
  holding two symlinks and zero packages. Dir-exists passed,
  `vite_build:academia-de-reciclagem` ran, and it failed on `Cannot find
  module 'tailwindcss'` — the precondition had certified a harness that was
  not there. It now probes `node_modules/.package-lock.json`, which only
  `npm ci`/`npm install` writes. Both halves were fixed: the probe, and
  `wire_env`, which must not manufacture a half-state that reads as a whole
  one (`test_plan_env_wiring_does_not_manufacture_a_partial_node_modules`).
- **Signature** (advisory, for what preflight cannot know in advance): a
  non-zero gate whose output carries a known setup-failure fingerprint
  (`Executable doesn't exist at`, `Process from config.webServer was not
  able to start`, a **bare** specifier failing to resolve,
  `ModuleNotFoundError: noctusai_lib`) is marked `harness_suspect` and
  **carries the matched evidence line**, so a wrong guess is visible and
  overrulable rather than silently swallowing a real red.
- **Verdict:** any failure on a valid harness ⇒ `red` (a known real
  failure is still the headline). If **every** failure is suspect, or a
  precondition was unmet ⇒ `inconclusive`, `exit_code=1`. Not-measured is
  never a pass.

Signatures are deliberately conservative and tested **in both directions**
— `test_signature_matches_every_real_2026_09_20_harness_fault` (it can
fire, on the verbatim output) and `test_signature_does_not_fire_on_genuine_failures`
(it can stay silent, on real assertion failures). A signature that
swallowed a genuine red would be the identical harm pointed the other way.

#### 10a. A comparison needs DISCRIMINATING POWER — the null result is the trap

The sharpest instance, and the one no precondition catches.

To test "did Playwright 1.63 break this suite?", the suite was run on
1.62.1 and on 1.63.0 and the results compared: `sidebar.spec` passed 7/7
on **both**, so the versions were declared equivalent and the pin was
reverted. CI then went red on exactly that spec — and the version
correlation held across every conclusive run (`^1.63.0` red ×2,
`~1.62.1` green).

The comparison was worthless, and the tell was visible the whole time:
**that harness never produced a single `sidebar` failure in any
configuration** — not on either version, not at CI parity (`CI=true`,
`workers:1`, `retries:2`), not once. A harness that cannot exhibit the
phenomenon cannot tell you its cause. Its "no difference" was not evidence
of equivalence; it was **no evidence at all**, wearing the same clothes.

This is § 4 ("prove the check can FAIL") applied to comparison rather
than to a guard:

> Before believing "A and B behave the same", require the harness to have
> produced the behaviour **at least once**. If neither arm ever shows the
> phenomenon you are attributing, you have measured your harness, not the
> difference.

The fix was to build an arm that *could* fail: the same sha, in
`mcr.microsoft.com/playwright:v1.63.0-noble` (linux/amd64, as CI runs it)
rather than on macOS. It reproduced CI's exact two failures on the first
valid run — and the 1.62.1 image then became a real comparison instead of
a pair of vacuous greens. **When you cannot reproduce CI, the gap between
your box and CI is the bug to close first, not an excuse to reason
without it.** — 2026-09-20

#### 10b. A detector's blind spot is a harness-validity fault too — "I looked and it's absent" vs. "I could not read this shape"

§ 10 is about a *runtime* harness (browser/venv/dev-server) producing a red
that describes the setup, not the code. The identical failure mode exists
one layer down, in a *static* detector — and it is more dangerous there,
because it never even attempts a subprocess: a regex/AST scan either
matches a construct or it silently does not, with no exit code to be
suspicious of.

**The incident (2026-09-20, same session as § 10):** an audit agent grepped
migrations for the literal `ALTER TABLE x ENABLE ROW LEVEL SECURITY` and
reported **66 exposed tables, including 7 live-PII**. The live number was
**4**. This platform enables RLS on a batch of tables *dynamically* —
`DO $$ ... FOREACH t IN ARRAY ARRAY[...] LOOP EXECUTE format('ALTER TABLE
%I ENABLE ROW LEVEL SECURITY', t) ... END $$;` (`products/social-wiring/
backend/migrations/065_campanhas.sql`, `101_permutas_matching.sql`) — a
shape the literal grep structurally cannot see. It did not find "no RLS
enabled"; it found "no line matching this exact string", and reported the
second as if it were the first.

**The rule.** A detector has exactly two honest outcomes for a given
input, not one: *"I looked and the property is absent"* and *"I could not
parse this input's shape, so I don't know."* Collapsing the second into
the first — reporting "absent" when the true state is "unparseable" — is
`§ 10`'s harness-invalid failure with the runtime swapped for the parser.
The fix is never "write a cleverer regex and declare victory silently" —
it is to make the detector say **which** of the two outcomes it reached,
the same way `gate_sweep` says `harness_invalid` instead of guessing a
verdict from an unmet precondition.

**Two exemplars, same session, both already load-bearing:**
- `noctus.dev.compliance.check_table_has_rls` resolves BOTH dynamic-RLS
  forms this platform actually uses (the `FOREACH`/`EXECUTE format(...)`
  shape above, and `erp-imobiliario`'s `FOR t IN SELECT unnest(ARRAY[...])`
  shape) by correlating each loop's array literal with its `EXECUTE`
  call — closing the 66-vs-4 gap. It is still kept **advisory, not a
  blocking gate**, precisely because a regex scan is not a SQL parser: a
  *third* dynamic-batch shape it does not yet recognise would silently
  reproduce the identical bug it was built to fix, one shape later. See
  `KB § PATTERNS/backend/database-rls.md` § "Advisory (not blocking)
  sibling" for the full detector + its documented residual limitation.
- `noctus.dev.status` reports a dedicated `status_unparsed` field on a
  `PROJECT.md` whose `**Status:**` line matched no known pattern at all —
  never silently defaulting that project to "not started" or dropping it
  from the digest. A row you cannot classify must read as *unclassified*,
  not as whichever classification happens to be the code's fallback
  branch.

⇒ **A regex/AST scan that cannot recognize a construct has not proven the
construct absent — it has proven nothing about that input, and must say
so.** This composes with § 8 (existence ≠ behaviour) from the opposite
direction: § 8 is a check that CAN see the object and wrongly credits its
mere presence; § 10b is a check that CANNOT see the object at all and
wrongly credits its apparent absence. Both convert "I don't actually know"
into a confident wrong answer unless the detector is built to say
`unparsed`/`inconclusive`/advisory-only instead.
