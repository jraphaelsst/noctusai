# Ship-consent riders — a prod deploy never carries unapproved work

> **🔴 RELAXED 2026-09-24 (owner decision):** "no approval needed when I ask — the ask is the permission itself." The default `release stage=bless` (`mode=ff`) now fast-forwards `main` to the WHOLE CI-green `dev` tip with **no per-project ship-consent check**; a diverged `main` is refused until `stage=backmerge`. Consent rows and the manifest remain as an informational record of whose work ships. `mode=cut` / `mode=refuse` below are **explicit opt-ins** for shipping only approved work. Unchanged: CI green on the exact sha, `NOCTUS_ALLOW_MAIN_PUSH` discipline, and a NEW product's first prod exposure (`noctus.dev.prod_consent`, `KB § PATTERNS/devops/prod-exposure-consent.md`). The rest of this page describes the opt-in cut.
>
> **Original owner mandate (2026-09-22):** an agent deploying to prod must NOT carry other agents' in-flight / unapproved work. Root cause it closes: `noctus.dev.release stage=bless` fast-forwarded `main` to the WHOLE `dev` tip, so every commit any agent had integrated shipped with whoever pressed bless. Approval unit = the **PROJECT/ROADMAP**; on unapproved riders the default is to **CUT a release of approved work only**.

## The chain

`manifest` → consent → `bless` (FF, or cut → CI on the cut → FF) → `promote` → `backmerge`.

| step | call | writes |
|---|---|---|
| 1. who rides along? | `noctus.dev.release stage=manifest` | nothing |
| 2. approve a project | `noctus.dev.ship_consent action=challenge project=<p>` → the USER types the sentence → `action=author project=<p> session_id=<id>` | one row in `ship-consent.ndjson` on the orphan `origin/ledgers` branch (plumbing-written, never a dev commit, since 2026-09-24; `release` dual-reads it with dev's legacy copy — `KB § PATTERNS/common/ledger-store.md`) |
| 3a. all riders approved ∧ `main` is an ancestor of `dev` | `release stage=bless confirm=true` | FF `main` to the dev tip (unchanged behaviour, CI-green gate on the dev tip) |
| 3b. otherwise (default `mode=cut`) | `release stage=bless` (dry-run plans + test-applies) → `confirm=true` | pushes `release/<YYYYMMDD-HHMM>` only — `main` does not move |
| 3c. finalize the cut | `release stage=bless release_branch=release/<stamp> confirm=true` | FF `main` to the cut, once `Tests & Build` is GREEN on its exact sha |
| 4. promote | `release stage=promote` | unchanged |
| 5. restore dev contains main | `release stage=backmerge confirm=true` | merge commit (parents dev, main) pushed to `dev` |

`mode=refuse` blocks instead of cutting. `NOCTUS_ALLOW_MAIN_PUSH` stays sole-set by `release`, only on the `main`/`prod` pushes — never on the `release/*` or `dev` pushes.

## Attribution — commit → branch → project

1. **`Noc-Branch: <branch>` trailer** — appended by `scripts/hooks/commit-msg` (installed by `scripts/install-hooks.sh`, symlinked like every other hook, so all worktrees share it). Skips merges + detached HEAD; never rewrites an existing trailer, so it survives `task_branch integrate`'s rebase and a cut's cherry-pick (first author wins). Never blocks a commit.
2. **Legacy (no trailer)** — branch-tree pointer evidence, in order: pointer `commit` is a sha prefix → pointer `notes` equals the subject (the pointer protocol writes the commit subject there) → stable patch-id equals a pointer commit's (a pre-rebase sha).
3. **Nothing** ⇒ `unattributed` ⇒ treated as **unapproved** (refuse-not-null).

Branch → project: the branch-tree pointer's optional `project` field (`noctus.dev.branch_pointer … project=<p>`). An engineer omitting it inherits its PARENT's project (the parent branch's pointer, else the latest sibling dispatched by the same parent). **Default: an unmapped branch is its own project, named by the branch** (`feat/x` approves as project `feat/x`).

## Rider states

| state | meaning | ships in a cut? |
|---|---|---|
| `exempt` | touches only `*.md` / `project-history/` / `docs/` — the SAME classifier bless uses for its docs-only CI exception | ✅ (unless it depends on an unshipped rider ⇒ `deferred`) |
| `approved` | its project holds a verified consent whose recorded `dev_sha` reaches the commit | ✅ |
| `on_main` | `git cherry main dev` says an equal patch is already on main (a prior cut) | skipped |
| `unapproved` | attributed, no covering consent | ❌ stays on dev |
| `unattributed` | no trailer, no pointer evidence | ❌ stays on dev |

## Consent coverage — decision

A consent covers the project's commits **reachable from the `origin/dev` sha recorded at consent time**. A commit integrated after it needs a fresh `author` — the user approved what existed, not future work. `revoke reason=<why>` voids every earlier approval of that project (no transcript needed: withdrawing can only ship less). At release time every approval is **re-verified** against its session transcript (a hand-appended ledger row verifies nothing ⇒ project reads `unverified`), mirroring how `check_prod_exposure_consent` re-verifies `deploy/consent/*.prod.yml`. The phrase is exact-match only — `I approve shipping project <p> to production.` — no directive/intent tier (unlike prod-exposure consent): a ship approval recurs every release, so an operational "ship it" must never double as approval of a project's whole backlog.

## The cut — how, and when it refuses

Built with **no working tree**: per approved commit `git merge-tree --write-tree --merge-base=<C>^ <tip> <C>` (cherry-pick's exact 3-way merge; `.gitattributes` `merge=union` honoured) then `git commit-tree` with the original author + message + `(cherry picked from commit <C>)`. The dry-run already builds the chain (unreachable objects only), so `planned_cut` means "this applies cleanly". REFUSES, naming the dependency:

- an **approved** commit touches a file (outside `project-history/`, and outside a pure counts-refresh — see below) that an **earlier unshipped** rider changed — shipping it alone would ship a state that never existed on dev (approve that rider's project, or wait);
- a cherry-pick conflicts;
- nothing is approved.

An exempt (docs) commit in that position is `deferred`, not refused. Finalizing re-checks the pushed `release/*` branch: every commit must be a cut of a CURRENTLY-approved commit (hand-added commit or consent revoked since ⇒ blocked), `main` must still be its ancestor, and CI must be green on its sha. `.github/workflows/test.yml` runs on `release/**` pushes (full suite, never scoped down).

### Derived-file (kb-counts) dependency exemption (2026-09-23)

The pre-commit hook's `kb_sync --update-kb-counts` step folds an auto-regenerated counts refresh into nearly every commit that touches `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` / `06-AGENTS.md` / `AGENT-CONTEXT.md` (the 3 files `.gitattributes` declares `merge=kb-counts` for). Left unhandled, `plan_ship_set` treated that shared touch as a real code dependency — chaining an approved rider's cut to whatever unrelated project's commit last happened to regenerate the SAME counts block (3 cuts refused before this was root-caused).

The fix reads `.gitattributes` — the SAME declarative surface `scripts/hooks/merge-kb-counts.sh` already reads, never a hand-copied filename list — as the single source of "is this file derived", via `git check-attr --source=<sha> merge -- <path>` (pattern-aware: a future `.gitattributes` GLOB entry resolves correctly, not just today's 3 literal lines). For a `merge=kb-counts`-attributed file, a rider's specific touch to it is `regen_only` when the masked (marker-blocks-blanked) content is byte-identical before/after that commit — i.e. its ENTIRE diff to that file lives inside a `<!-- kb-counts:start -->…<!-- kb-counts:end -->` block. `plan_ship_set` then skips recording that unshipped touch as a dependency pointer, hopping over pure counts churn to the nearest REAL (or no) unshipped edit. Prose changed in the same file, or any touch to a non-attributed file, still couples exactly as before — the exemption is strictly per-(commit, file), never per-file. `mcp/noctusai/tools/noctus/dev/_release_riders.py::_kb_counts_attributed` / `_is_regen_only_touch` / `_mark_regen_only_files`.

### kb-counts regen commit — keeping `main` self-consistent

A cut ships only a SUBSET of dev's riders, so whichever cherry-picked rider happens to carry the counts blocks leaves `main` with a snapshot from ITS branch, not a fresh recount of what actually shipped. After `cherry_pick_chain` builds the cut tip, `regenerate_kb_counts_commit` appends ONE bookkeeping commit (marked `(kb-counts regen on <tip>)` in its body) that rewrites every `merge=kb-counts`-declared file's marker blocks — still **no working tree**: a THROWAWAY `GIT_INDEX_FILE` (`git read-tree` the cut's tree → `git hash-object -w` the new blob(s) → `git update-index --add --cacheinfo` → `git write-tree` → `git commit-tree`), never the real index. A no-op (nothing changed) adds no commit. The rendering itself is DI'd (`render_kb_counts` on `noctus.dev.release`, default `kb_sync.render_kb_counts` bound against the ambient checkout — the best available signal, since the cut itself has no working tree to walk); `_bless_release_branch`'s foreign-commit re-check recognizes the regen mark and does not flag it foreign, the same trust boundary as the cherry-picked commits (both are built by the tool itself, as part of this same cut).

## Backmerge

After a cut, `main` holds cherry-picks `dev` lacks, so the next bless cannot FF. `stage=backmerge` builds `Merge main into dev` (merge-tree + commit-tree, no checkout) and pushes it to `dev` (a race ⇒ re-run; a conflict ⇒ resolve on a `task_branch`). Riders already shipped read `on_main` in the meantime, so a second cut never re-picks them.

## Composes with

`KB § PATTERNS/devops/prod-exposure-consent.md` (same verified-transcript evidence layer; per-product exposure, orthogonal to per-project shipping) · `KB § PATTERNS/devops/dev-main-ci-gates.md` (the CI-green bless precondition, now also on the cut sha) · `KB § PATTERNS/architect/branch-tree-tracking.md` (the `project` field) · `KB § PATTERNS/architect/git-branch-model.md` (bless is no longer "the whole dev tip" when riders are unapproved) · skill `noc-ship`.
