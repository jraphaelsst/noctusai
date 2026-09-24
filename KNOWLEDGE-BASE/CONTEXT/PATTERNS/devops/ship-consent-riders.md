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

- an **approved** commit touches a file (outside `project-history/`) that an **earlier unshipped** rider changed — shipping it alone would ship a state that never existed on dev (approve that rider's project, or wait);
- a cherry-pick conflicts;
- nothing is approved.

An exempt (docs) commit in that position is `deferred`, not refused. Finalizing re-checks the pushed `release/*` branch: every commit must be a cut of a CURRENTLY-approved commit (hand-added commit or consent revoked since ⇒ blocked), `main` must still be its ancestor, and CI must be green on its sha. `.github/workflows/test.yml` runs on `release/**` pushes (full suite, never scoped down).

## Backmerge

After a cut, `main` holds cherry-picks `dev` lacks, so the next bless cannot FF. `stage=backmerge` builds `Merge main into dev` (merge-tree + commit-tree, no checkout) and pushes it to `dev` (a race ⇒ re-run; a conflict ⇒ resolve on a `task_branch`). Riders already shipped read `on_main` in the meantime, so a second cut never re-picks them.

## Composes with

`KB § PATTERNS/devops/prod-exposure-consent.md` (same verified-transcript evidence layer; per-product exposure, orthogonal to per-project shipping) · `KB § PATTERNS/devops/dev-main-ci-gates.md` (the CI-green bless precondition, now also on the cut sha) · `KB § PATTERNS/architect/branch-tree-tracking.md` (the `project` field) · `KB § PATTERNS/architect/git-branch-model.md` (bless is no longer "the whole dev tip" when riders are unapproved) · skill `noc-ship`.
