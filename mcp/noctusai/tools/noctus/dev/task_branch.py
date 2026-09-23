"""noctus.dev.task_branch — the self-branching-mode per-task lifecycle as a tool.

Self-branching mode (KB § PATTERNS/self-branching-mode.md): in a multi-terminal
world there is no single architect on top — every terminal-agent is a *peer*,
and a peer can't cheaply know whether a sibling is active in the SAME checkout.
So the safe default for any **writing** task is to self-isolate: do the work in
a per-task `git worktree` off `origin/dev`, then integrate straight to
`origin/dev` — NEVER switching the shared primary checkout's branch out from
under a sibling (the §9a "2-days-of-chaos" failure mode). This tool runs that
lifecycle so it is one call, not a hand-typed ritual:

  • start     : fetch → `git worktree add <wt> -b feat/<slug> origin/dev`.
  • integrate : (in the worktree) fetch → rebase onto origin/dev → FF-push
                HEAD → origin/dev, with fetch-rebase-RETRY on the concurrent-
                push race. A rebase conflict is ABORTED (worktree restored
                clean) and surfaced loudly — never auto-resolved, never left
                half-rebased. This is KB § branching-and-merging § 10.2 Option A
                with `dev` substituted for the integration ref.
                After a successful rebase, if this branch introduces a
                migration file, `check_migration_number_collision` re-runs
                against the (now fresh-onto-dev) worktree and BLOCKS the push
                on any finding — the SECOND backstop for the migration-
                numbering hazard pre-commit only warns about (Leg B) or only
                catches once staged (Leg A). See § Migration-number collision
                safety in KB § PATTERNS/backend/database-rls.md.
                Known-benign refresh artifacts (cache refresh files that the
                pre-commit hook writes as side-effects: KNOWLEDGE-BASE/
                AGENT-CONTEXT.md, KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md,
                project-history/vector-costs.ndjson, project-history/
                auto-improvement.ndjson, project-history/worktree-salvage.ndjson,
                project-history/branch-tree.ndjson, .claude/cache/*) are
                auto-stashed before the rebase and restored after, so a clean
                FF rebase is never blocked by them. Only real
                conflicts surface. A rebase REFUSED before starting (hook chatter
                re-dirties after stash) is surfaced as status=dirty_blocked
                (not status=conflict) so the caller sees dirty files, not phantom
                merge-conflict markers.
  • cleanup   : SALVAGE-before-delete (KB § PATTERNS/storage-hygiene.md § 2.3 —
                the worktree analogue of archive's learn-before-archive) THEN
                `git worktree remove <wt>` (refuses if dirty — no --force) →
                prune → `git branch -d feat/<slug>` (refuses if unmerged — `-d`
                not `-D`). The salvage ritual: (1) LEARNINGS — extract durable
                knowledge → KB/memory (surfaced as a checkpoint; discipline leg);
                (2) RECOVERY POINTER — record branch+SHA to the tracked
                `project-history/worktree-salvage.ndjson` (MECHANICAL here, via
                the shared `_worktree_salvage` helper — the same leg mole-sweep /
                cleanup_stale_worktrees already carry, so a precise teardown can
                no longer skip it); (3) STORAGE HYGIENE — run a mole worktree-
                sweep before the delete. A precise teardown of ONE named task
                worktree; the heuristic bulk-sweep of stale agent worktrees is
                the sibling noctus.dev.cleanup_stale_worktrees.
  • status    : read-only — list the active self-branch worktrees + each one's
                ahead/behind vs origin/dev.

Safety model (mirrors release / deploy_pull):
  • INSPECT (always, read-only first): fetch refs, resolve origin/dev, compute
    ff-ability + the commit lists each hop would move.
  • confirm-GATE (412 pattern): every WRITE action returns the PLAN only
    without `confirm`; `confirm=True` executes. `status` never writes.
  • BY CONSTRUCTION it only runs a safe git allowlist and carries NO banned
    token (reset / checkout / switch / restore / clean / merge / --force /
    --force-with-lease / -f / -D). It can create a worktree+branch and delete a
    *merged* branch (`-d`), but can never force, reset, or rewrite history.
  • DEV-ONLY PUSH BOUNDARY (this tool's defining guard): every push destination
    MUST be `dev`. A refspec targeting main/prod (or anything else) is REFUSED,
    structurally — the tool can never touch the sacred release/prod lines, and
    never sets NOCTUS_ALLOW_MAIN_PUSH (a colocated test asserts both). Engineers
    and peer-agents land on `dev`; main/prod move only via noctus.dev.release.

IO is injectable (`run`) so the colocated test drives every path with zero real
git and asserts the allowlist, the dev-only-push boundary, and the rebase-retry.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tools.noctus.dev._benign_stash import (
    BENIGN_REFRESH_PATTERNS,
    classify_dirty as _shared_classify_dirty,
    commit_ledger_rows as _shared_commit_ledger_rows,
    partition_ledger as _shared_partition_ledger,
    pop_stash as _shared_pop_stash,
    stash_benign as _shared_stash_benign,
    # Reused by `_dirty_ledger_rel_paths`: porcelain lines must be parsed by the
    # ONE parser that already handles the rename form and the malformed-line
    # fallback — a second local parser is how a path gets silently truncated
    # into a different path.
    strip_status_code as _strip_status_code,
)
from tools.noctus.dev import toolkit_freshness as _toolkit_freshness

logger = logging.getLogger(__name__)

# git subcommands the tool may run. `worktree` (add/remove/list/prune) + `branch`
# (only `-d`, the merged-only delete) + `rebase` are what distinguish this from
# release's read-mostly set; force/reset/checkout stay OFF the list so a
# history-rewriting or branch-switching action is structurally impossible.
_ALLOWED_GIT = frozenset(
    {"fetch", "rev-parse", "merge-base", "rev-list", "log", "diff", "status",
     "worktree", "rebase", "push", "branch"}
)
_BANNED_TOKENS = (
    "reset", "checkout", "switch", "restore", "clean", "merge", "cherry-pick",
    "--hard", "--force", "--force-with-lease", "-f", "-D",
)

# Known-benign refresh artifacts — files the pre-commit / cache-refresh hooks
# write as side-effects inside the worktree. These appear in `git status
# --porcelain` and cause `git rebase` to refuse with a non-clean-worktree error,
# producing an empty `conflicted_files` + `status=conflict` even though the
# rebase would be a clean FF. The integrate precheck auto-stashes these before
# the rebase and pops the stash after. Patterns are fnmatch-style relative paths
# (as printed by `git status --porcelain`, XY-code stripped).
#
# All four project-history/*.ndjson ledger files are gitattributes merge=union
# append-only logs churned by post-checkout/post-merge cache-settle hooks
# (noc-graph/auto-improvement/worktree-salvage/branch-tree). They are
# reconstructable and never contain task work — so they are benign for the
# purpose of the rebase pre-check and should be auto-stashed rather than
# blocking integrate.
# Canonical home is now ``_benign_stash`` — the SAME patterns and the SAME
# stash/pop mechanism are used by ``_ledger_push``'s rebase leg, which had the
# identical bug and never got this fix. Re-exported here under the historical
# private name so this module's public surface is unchanged.
_BENIGN_REFRESH_PATTERNS = BENIGN_REFRESH_PATTERNS


def _default_run_local(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run `cmd`; (rc, stdout, stderr). `cwd` targets a worktree for the
    worktree-local ops (rebase / push / status); None ⇒ repo root for the
    repo-global ops (fetch / worktree add|remove|list|prune / branch -d).
    REPO_ROOT is imported lazily so module import stays light and the test
    (which injects `run`) never pays the settings import cost."""
    # LEDGER_ROOT (never REPO_ROOT): repo-global ops must run against the
    # PRIMARY checkout even when the MCP server booted with cwd inside a
    # worktree. See workspace.get_ledger_root() docstring.
    from settings import LEDGER_ROOT  # lazy: avoids import-time noctusai_lib cost

    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or str(LEDGER_ROOT))
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _assert_push_targets_dev(args: tuple[str, ...], dev_branch: str) -> None:
    """A push refspec's DESTINATION must be `dev` — the tool's defining safety
    boundary. Refuses main/prod/any-other dst, structurally."""
    if not args or args[0] != "push":
        return
    for tok in args:
        if ":refs/heads/" in tok:
            dst = tok.split(":refs/heads/", 1)[1]
            if dst != dev_branch:
                raise ValueError(
                    f"task_branch: push destination '{dst}' is not '{dev_branch}'. "
                    "This tool integrates ONLY to dev; main/prod move via noctus.dev.release."
                )


def _git(runner, *args, cwd: str | None = None, dev_branch: str = "dev") -> tuple[int, str, str]:
    """Run a git subcommand — ONLY if on the safe allowlist AND carrying no
    banned token AND (for a push) targeting `dev`. The structural guarantee the
    tool can never force/rewrite/switch, and can never push off `dev`."""
    sub = args[0] if args else ""
    if sub not in _ALLOWED_GIT:
        raise ValueError(
            f"task_branch: git '{sub}' is not on the safe allowlist {sorted(_ALLOWED_GIT)}"
        )
    for tok in args:
        if tok in _BANNED_TOKENS:
            raise ValueError(f"task_branch: banned token '{tok}' in git {list(args)}")
    _assert_push_targets_dev(args, dev_branch)
    return runner(["git", *args], cwd=cwd)


def _resolve(git, ref: str) -> str | None:
    rc, out, _e = git("rev-parse", ref)
    return out.strip() if rc == 0 and out.strip() else None


def _is_ancestor(git, a: str, b: str) -> bool:
    """True iff commit `a` is an ancestor of (or equal to) `b`."""
    rc, _o, _e = git("merge-base", "--is-ancestor", a, b)
    return rc == 0


def _commits(git, a: str, b: str, cwd: str | None = None) -> list[str]:
    rc, out, _e = git("log", "--oneline", f"{a}..{b}", cwd=cwd)
    return [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []


def _parse_worktrees(porcelain: str) -> list[dict[str, str]]:
    """Parse `git worktree list --porcelain` into [{path, head, branch}]."""
    blocks: list[dict[str, str]] = []
    cur: dict[str, str] = {}
    for line in porcelain.splitlines():
        if not line.strip():
            if cur:
                blocks.append(cur)
                cur = {}
            continue
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree "):].strip()}
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD "):].strip()
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch "):].strip()
    if cur:
        blocks.append(cur)
    return blocks


def _branch_for_path(porcelain: str, wt_path: str) -> str | None:
    """Resolve the ACTUAL branch checked out at `wt_path` from `git worktree list
    --porcelain`, keyed by the dir (the stable identity). Robust to a reused /
    renamed worktree whose branch ≠ feat/<slug> — without this the cleanup slug→
    branch assumption resolves a nonexistent branch, so the recovery-pointer leg
    silently no-ops and `branch -d` fails (the 2026-05-25 dogfood gap). Returns the
    short branch name (refs/heads/ stripped) or None (detached HEAD / not found)."""
    base = os.path.basename(wt_path.rstrip("/"))
    for wt in _parse_worktrees(porcelain):
        p = wt.get("path", "")
        if p == wt_path or p.endswith("/" + wt_path) or os.path.basename(p.rstrip("/")) == base:
            br = wt.get("branch", "")
            return br[len("refs/heads/"):] if br.startswith("refs/heads/") else None
    return None


def _is_dirty_excluding_gitignored(runner, wt_path: str) -> bool:
    """True iff the worktree has uncommitted changes that are NOT gitignored.

    ``git status --porcelain`` (without ``--ignored``) lists only tracked-modified
    + untracked non-ignored files. Gitignored files (e.g. ``.claude/cache/*.sqlite``)
    are never shown ⇒ a worktree that is "dirty" only because of gitignored files
    is clean by this predicate. Pure git plumbing, no banned tokens.
    """
    rc, out, _e = runner(["git", "status", "--porcelain"], cwd=wt_path)
    if rc != 0:
        # If git status itself fails, conservatively report dirty.
        return True
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return bool(lines)


def _classify_dirty_files(
    runner, wt_path: str
) -> tuple[list[str], list[str]]:
    """Classify dirty files in the worktree into (benign, real).

    `benign` = files matching ``_BENIGN_REFRESH_PATTERNS`` (known pre-commit /
    cache-refresh side-effects that block rebase but carry no task work).
    `real`   = everything else (actual conflicts, task-in-progress changes).

    Returns two lists of relative paths (as `git status --porcelain` reports them,
    XY-code stripped). A git-status failure → ([], ["<git-status-failed>"]) so the
    caller treats it conservatively as a real conflict.
    """
    return _shared_classify_dirty(lambda *a: runner(["git", *a], cwd=wt_path))


def _rebase_in_progress(runner, wt_path: str) -> bool:
    """True iff a rebase is currently in-progress in the worktree.

    git creates ``rebase-merge/`` (interactive/merge rebase) or ``rebase-apply/``
    (apply-based rebase) inside the worktree's git directory as soon as the
    rebase begins applying patches. If NEITHER exists after a ``git rebase``
    rc≠0, the rebase was REFUSED before it started (e.g. "error: cannot rebase:
    You have unstaged changes") — hook chatter re-dirtied the worktree after our
    auto-stash. Distinguishing "refused" from "conflicted" is Bug B's fix: a
    refused rebase must NOT produce ``status=conflict`` with empty
    ``conflicted_files`` (the phantom conflict).

    Uses ``git rev-parse --git-dir`` (allowlisted) to resolve the git dir path,
    then checks the filesystem. Falls back to True (conservative — treat as
    in-progress) if rev-parse fails.
    """
    rc, out, _e = runner(["git", "rev-parse", "--git-dir"], cwd=wt_path)
    if rc != 0:
        # Cannot determine git dir — be conservative (caller will abort + surface).
        return True
    git_dir = out.strip()
    # git-dir may be relative to wt_path
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(wt_path, git_dir)
    return (
        os.path.isdir(os.path.join(git_dir, "rebase-merge"))
        or os.path.isdir(os.path.join(git_dir, "rebase-apply"))
    )


def _push_salvage_ledger_from_primary(
    runner,
    *,
    root: str,
    rel_ledger: str,
    dev_branch: str,
    remote: str = "origin",
    verbose: bool = False,
) -> dict[str, Any]:
    """Commit the dirty salvage ledger from the PRIMARY ``dev`` checkout + FF-push
    it to dev — the robust ``fetch → divergence-guard → rebase-onto-origin/dev →
    FF-push`` idiom (mirrors ``branch_pointer._push_ledger_to_dev``).

    Why primary-not-worktree (the 2026-06-30 drift fix): the previous leg
    committed the salvage row on the WORKTREE's feature-branch HEAD and pushed
    ``HEAD:dev``. When ``origin/dev`` had advanced past the branch's base (the
    normal case after later work landed on dev), that push was non-FF → rejected;
    the single fetch+retry re-pushed the SAME non-FF commit → still rejected. The
    salvage commit was then orphaned on the (rebase-integrated) feature branch,
    which the operator force-deletes (``branch -D``) → the recovery row was LOST
    for every rebase-integrated slug. Recording to the PRIMARY ledger + pushing
    from the primary ``dev`` checkout makes the push a clean rebase-onto-dev FF and
    leaves the WORKTREE untouched (so ``git worktree remove`` needs no worktree-side
    commit, and NOTHING lands on the to-be-deleted branch).

    Stages ``add``/``commit`` to the ledger file (plus whatever a pre-commit hook
    additionally stages mid-commit — see ``_ledger_push``'s module docstring for
    why that is NOT actually excludable, and why it is safe: the divergence
    guard tolerates known-benign riders and still blocks on anything else). The
    divergence-guard REFUSES to push when any commit ahead of ``origin/<dev>``
    touches a REAL non-ledger, non-benign path (never leak real work onto dev) —
    in that case the row stays committed on local dev and ships with the next
    dev push. The ``project-history/*.ndjson`` files carry a ``merge=union``
    gitattribute + are append-only, so the rebase is conflict-free. BEST-EFFORT:
    a failure never raises; cleanup always proceeds (the row is already on disk
    + idempotent next time).

    All git IO goes through the injected ``runner`` directly (NOT ``_git``): the
    leg needs ``add``/``commit``/``diff-tree`` which are intentionally off the
    safe allowlist; the push destination is hard-pinned to ``dev_branch`` so the
    dev-only-push boundary holds by construction.

    The ``commit → fetch → divergence-guard → rebase-onto-origin/dev → FF-push``
    idiom is the shared :func:`commit_and_ff_push_ledger` helper (the N=3 DRY
    lift); this leg just supplies the salvage commit message. Returns the FULL
    structured result (``{"ok", "status", "pushed", "error", ...}``) rather than
    collapsing it to a bare bool — a caller that only reads ``pushed`` still
    gets the same True/False signal, but a caller that surfaces the result (as
    ``task_branch`` cleanup now does) can say WHY a push failed instead of a
    silent ``salvage_pushed: false`` (no-silent-errors).
    """
    from tools.noctus.dev._ledger_push import commit_and_ff_push_ledger  # lazy import

    msg = (f"chore(salvage): record {rel_ledger} recovery pointer\n\n"
           "task_branch action=cleanup salvage-ledger entry (branch+SHA → "
           "worktree-salvage.ndjson, the tracked recovery-pointer ledger). "
           "Recorded + committed on the PRIMARY dev checkout (not the worktree) "
           "+ rebase-onto-dev FF-pushed so the row lands on origin/dev even when "
           "dev advanced past the branch base (2026-06-30 rebase-integrated-slug "
           "lost-row fix); leaves the worktree clean for remove.")
    return commit_and_ff_push_ledger(
        runner=runner,
        root=root,
        rel_paths=[rel_ledger],
        dev_branch=dev_branch,
        remote=remote,
        commit_msg=msg,
        already_committed=False,
        _log_prefix="task_branch.cleanup",
    )


def _resolve_primary_root(primary_root: str | None) -> str:
    """The PRIMARY checkout root — injected in tests, `REPO_ROOT` in production.

    Extracted because THREE call sites needed it and two of them had a subtly
    different guard: `cleanup` resolved it only inside `if head:`, so a
    head-less teardown left it `None`, and `integrate` never bound it at all.
    A `None` reaching `str()` becomes the literal path "None", which git then
    reports as a missing directory rather than as the programming error it is.
    """
    if primary_root is not None:
        return primary_root
    # LEDGER_ROOT (never REPO_ROOT): must resolve to the PRIMARY checkout
    # even when the MCP server booted with cwd inside a worktree. See
    # workspace.get_ledger_root() docstring.
    from settings import LEDGER_ROOT  # lazy: keeps the injected test path settings-free
    return str(LEDGER_ROOT)


def _dirty_ledger_rel_paths(runner, root: str) -> list[str]:
    """Every DIRTY append-only ledger under ``project-history/``, derived.

    🔴 DERIVED FROM GIT + THE GLOB, NEVER A HAND-KEPT FILENAME LIST. The whole
    class of bug this function closes is "a new ledger was added and nobody
    updated the list" — the exact anti-pattern CLAUDE.md §1 names for
    hand-maintained coverage. ``project-history/*.ndjson`` is already the
    invariant (``.gitattributes`` carries `merge=union` for the same glob,
    because every ledger there is an append-only structured log written by an
    MCP tool and never hand-edited), so asking git which of them are dirty
    covers a ledger added tomorrow with no edit here.
    """
    rc, out, _err = runner(
        ["git", "-C", root, "status", "--porcelain", "--", "project-history"]
    )
    if rc != 0:
        return []
    paths: list[str] = []
    for raw in (out or "").splitlines():
        if not raw.strip():
            continue
        path = _strip_status_code(raw)
        if path.startswith("project-history/") and path.endswith(".ndjson"):
            paths.append(path)
    return sorted(set(paths))


def _drain_ledgers_from_primary(
    runner,
    *,
    root: str,
    dev_branch: str,
    remote: str = "origin",
    verbose: bool = False,
) -> dict[str, Any]:
    """Ship every dirty ``project-history/*.ndjson`` from the PRIMARY checkout.

    🔴 WHY THIS EXISTS — THE RECURRENCE THIS CLOSES (4+ incidents, ~4 months).
    Two append-only ledgers are written to the primary tree by tooling, and
    until now only ONE of them had a way to reach the repo:

        worktree-salvage.ndjson  cleanup Leg 2b commits + FF-pushes it
        auto-improvement.ndjson  `log()` appends … and NOTHING ever commits it

    `auto_improvement.refresh()` only READS the ndjson into its sqlite mirror,
    so every `auto_improvement_log` call left permanent dirt in the primary
    checkout until a human noticed and hand-drained it (see
    `a615d761 chore(ledger): drain the rows stranded on the primary checkout`,
    which diagnosed this correctly on 2026-08-22 and shipped a drain rather
    than the fix). Every previous attempt looked for an ORDERING bug; there was
    none to find, because the stage was missing entirely.

    🔴 AND IT RUNS **AFTER** ``cache_settle``, WHICH IS THE OTHER HALF.
    `_settle_structural_caches` is the LAST thing both integrate and cleanup
    do — after their only commit. Today its two legs only read, so nothing
    leaks; but any future leg that writes would be dirt by construction with no
    stage left behind it. Draining after the settle removes that trap instead
    of leaving it armed for the next person.

    Best-effort by construction: a failure NEVER fails a completed
    integrate/cleanup — the rows are on disk, append-only and idempotent, so
    the next run ships them. `status` says which outcome happened rather than
    collapsing to a silent bool (no-silent-errors).
    """
    from tools.noctus.dev._ledger_push import commit_and_ff_push_ledger  # lazy

    rel_paths = _dirty_ledger_rel_paths(runner, root)
    if not rel_paths:
        return {"ok": True, "status": "already_clean", "pushed": False, "ledgers": []}

    if verbose:
        logger.debug("task_branch: draining %d dirty ledger(s) from primary %s: %s",
                     len(rel_paths), root, rel_paths)

    msg = (
        "chore(ledger): ship the append-only ledger rows written this run\n\n"
        + "\n".join(f"  {p}" for p in rel_paths)
        + "\n\nDrained from the PRIMARY checkout after the structural-cache "
        "settle, so rows the settle itself writes are shipped too. Derived from "
        "`git status -- project-history` + the *.ndjson glob, never a "
        "hand-kept filename list — a ledger added later is covered on arrival."
    )
    result = commit_and_ff_push_ledger(
        runner=runner,
        root=root,
        rel_paths=rel_paths,
        dev_branch=dev_branch,
        remote=remote,
        commit_msg=msg,
        already_committed=False,
        _log_prefix="task_branch.drain",
    )
    result["ledgers"] = rel_paths
    # 🔴 NORMALISE `pushed` — `commit_and_ff_push_ledger` sets it on the success
    # and already_clean paths but OMITS it on every failure path (see its own
    # result table), so a caller doing `result["pushed"]` KeyErrors exactly when
    # something went wrong. This helper guarantees the key is always present and
    # boolean, so "did the rows ship?" is answerable without knowing which
    # internal branch produced the dict.
    result["pushed"] = bool(result.get("pushed"))
    if not result["pushed"]:
        logger.warning(
            "task_branch.drain: ledger rows NOT pushed (%s) — they stay on disk "
            "and ship next run: %s",
            result.get("error") or result.get("status"), rel_paths)
    return result


def _stash_benign_artifacts(
    runner, wt_path: str, benign: list[str], verbose: bool = False
) -> str | None:
    """Stash the known-benign refresh artifacts before a rebase so the worktree
    is clean. Uses ``git stash push -- <paths>`` (bypasses ``_git()`` since stash
    is not on the safe allowlist — this is an intentional, controlled carve-out
    for known-safe paths only, mirroring the force-remove carve-out in cleanup).

    Returns the stash entry's COMMIT SHA, or None if there was nothing to stash
    or the stash failed (caller falls back to surfacing the files as blocking).
    The SHA — not a flag — because `.git/refs/stash` is one stack shared by every
    worktree, so `stash@{0}` at restore time may be a PEER's entry (see
    `_benign_stash.stash_benign`; it cost a cross-session near-loss on 2026-09-09).

    `label_hint=wt_path` folds THIS worktree's path into the stash message
    (alongside a content fingerprint) so a shared stack carrying 10+ of these
    entries reads as distinguishable per-worktree in `git stash list` — a
    purely cosmetic/operator-legibility improvement; restore/drop stay
    SHA-addressed regardless (see `_benign_stash.stash_message`).
    """
    return _shared_stash_benign(
        lambda *a: runner(["git", "-C", wt_path, *a]),
        benign,
        log_prefix="task_branch.integrate",
        label_hint=wt_path,
    )


def _pop_stash(runner, wt_path: str, ref: str | None, verbose: bool = False) -> None:
    """Restore the auto-stash created by ``_stash_benign_artifacts``, BY SHA.
    Best-effort: a failure is logged but never raises (the integrate already
    completed). A falsy ``ref`` restores nothing — deliberately: a positional
    pop here is the cross-worktree swap this contract exists to prevent."""
    _shared_pop_stash(
        lambda *a: runner(["git", "-C", wt_path, *a]),
        ref,
        log_prefix="task_branch.integrate",
    )


def _commit_ledger_rows_in_worktree(
    runner, wt_path: str, ledger: list[str], verbose: bool = False
) -> str | None:
    """Commit — never stash — dirty ``project-history/*.ndjson`` rows before the
    rebase. The shared stash stack (`.git/refs/stash`, one stack across every
    worktree of this repo) is loss-shaped for append-only ledger data — see
    ``_benign_stash.is_ledger_ndjson``'s docstring for the 2026-09-16 near-loss
    this closes. A ledger row is `is_benign()` too, so without this split it
    silently rode along in the SAME stash as `.claude/cache/*` — safe for a
    cache file (a rebuild), not for the only copy of an append-only fact."""
    return _shared_commit_ledger_rows(
        lambda *a: runner(["git", "-C", wt_path, *a]),
        ledger,
        log_prefix="task_branch.integrate",
    )

# ── env auto-wire (the §5a verification-env recipe, mechanized) ──────────────
# A fresh worktree is a clean git checkout: node_modules/ is gitignored ⇒ ABSENT,
# so a vite build / vitest run inside the worktree fails for want of deps. The
# §5a recipe mirrors the PRIMARY tree's per-package node_modules INTO the
# worktree, then re-points the `@noctusai/{lib,seed}` file:-deps at the WORKTREE's
# own seed copies (the crux — else worktree lib edits are invisible to the build).
# These are all gitignored paths ⇒ the symlinks never get staged (intended).
#
# PRIMARY-CONTAMINATION FIX (2026-07-16 bug, closed 2026-07-20): seed-frontend
# node_modules (nothing ever nests inside them) stay a whole-dir symlink to
# primary — safe. Per-PRODUCT node_modules do NOT: the old scheme whole-dir
# symlinked `wt/products/<slug>/frontend/node_modules` → primary's real
# directory, then created `@noctusai/{lib,seed}` *inside* that path — which,
# because the path resolves THROUGH the symlink, physically wrote the entry
# into the PRIMARY's shared node_modules, re-pointing EVERY worktree fleet-wide
# at whichever worktree wired last. Fix: a product's `node_modules` is now a
# REAL directory *in the worktree*, populated with one symlink per top-level
# primary package (cheap — a symlink, not a copy) EXCEPT the `@noctusai` scope,
# which is always worktree-owned and points at the worktree's own seed copies.
# All writes land inside `wt_root`; the primary directory is read-only input,
# never a write target. A pre-existing STALE whole-dir symlink at the product's
# node_modules path (left over from a worktree wired before this fix, or a
# not-yet-wired peer) is converted to a real directory first (`ensure_real_dir`)
# so nothing lands through it.
#
# The filesystem ops are injected (`FsOps`) so the colocated test drives the
# planner over a tmp_path fixture tree with zero real node_modules. Planning is
# pure (read-only); application happens ONLY under `confirm` and is best-effort —
# every skip is REPORTED (never silent), and a real (non-symlink) node_modules
# already in the worktree is left untouched (never nested, never clobbered).

# FALLBACK ONLY — today's known seed-frontend / @noctusai-repoint pair. The
# live source of truth is DERIVED per product from its own `package.json`
# (`_derive_product_repoints` below): a `file:../../../seed/X/frontend`
# dependency IS the declaration of "this product needs X's node_modules
# mirrored + re-pointed". Hardcoding this list and applying it to every
# product blindly is exactly the "hand-maintained lists drift" anti-pattern
# (§1) — a product that adds a THIRD seed frontend dependency, or one that
# genuinely doesn't need one of the two, would silently mis-wire. These two
# tuples are used ONLY when a product's `package.json` is absent/unreadable/
# malformed (a fixture tree without one, or a product mid-migration) so
# behavior degrades gracefully instead of wiring nothing.
_SEED_FRONTENDS = ("seed/lib/frontend", "seed/framework/frontend")
_NOCTUSAI_REPOINTS = (
    ("@noctusai/lib", "seed/lib/frontend"),
    ("@noctusai/seed", "seed/framework/frontend"),
)


def _derive_product_repoints(primary_root: str, rel_fe: str, fs: "FsOps") -> list[tuple[str, str]]:
    """This product's `@noctusai/*` seed re-points, DERIVED from its OWN
    `package.json` `file:` dependencies — never assumed. A dependency value
    of `file:../../../seed/X/frontend` resolves (relative to `rel_fe`) to
    the repo-relative target `seed/X/frontend`; only deps landing under the
    top-level `seed/` tree are re-pointed (a product's other `file:` deps,
    if any, are none of wire_env's business).

    Falls back to the static `_NOCTUSAI_REPOINTS` default when the
    `package.json` is absent/unreadable/malformed, or declares no seed
    `file:` dep at all — see the module-level comment above these
    constants. `noctus.dev.task_branch`'s own colocated test
    (`test_derive_product_repoints_matches_real_products`) runs THIS
    function against the real repo tree so a future drift between the
    convention and the fallback is caught by CI, not discovered by hand.
    """
    raw = fs.read_text(os.path.join(primary_root, rel_fe, "package.json"))
    if raw is None:
        return list(_NOCTUSAI_REPOINTS)
    try:
        manifest = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return list(_NOCTUSAI_REPOINTS)
    deps: dict[str, Any] = {}
    for section in ("dependencies", "devDependencies"):
        section_val = manifest.get(section) if isinstance(manifest, dict) else None
        if isinstance(section_val, dict):
            deps.update(section_val)
    out: list[tuple[str, str]] = []
    for name, value in sorted(deps.items()):
        if not isinstance(value, str) or not value.startswith("file:"):
            continue
        target = os.path.normpath(os.path.join(rel_fe, value[len("file:"):]))
        if target.split(os.sep)[0] != "seed":
            continue  # a file:-dep outside seed/ is not wire_env's concern
        out.append((name, target))
    return out or list(_NOCTUSAI_REPOINTS)


def _derive_seed_frontends(primary_root: str, fs: "FsOps") -> list[str]:
    """The set of seed-frontend packages whose `node_modules` gets whole-dir
    mirrored into the worktree — DERIVED as the union of every product's
    `_derive_product_repoints` targets, never a hand-maintained slug list.
    Falls back to the static `_SEED_FRONTENDS` default when no product
    yields any (an empty/product-less tree has nothing to derive FROM)."""
    found: set[str] = set()
    for slug in fs.list_product_frontends(primary_root):
        rel_fe = f"products/{slug}/frontend"
        for _dep, seed_rel in _derive_product_repoints(primary_root, rel_fe, fs):
            found.add(seed_rel)
    return sorted(found) if found else list(_SEED_FRONTENDS)


class FsOps:
    """Filesystem seam for env-wiring — real `os`/`pathlib` by default; the test
    injects a fixture-backed instance so the planner runs over a tmp tree."""

    def exists(self, p: str) -> bool:
        return os.path.lexists(p)

    def is_dir(self, p: str) -> bool:
        return os.path.isdir(p) and not os.path.islink(p)

    def is_symlink(self, p: str) -> bool:
        return os.path.islink(p)

    def list_product_frontends(self, primary_root: str) -> list[str]:
        """slugs of products/<slug>/frontend that exist on the PRIMARY tree."""
        products = os.path.join(primary_root, "products")
        if not os.path.isdir(products):
            return []
        out = []
        for name in sorted(os.listdir(products)):
            if os.path.isdir(os.path.join(products, name, "frontend")):
                out.append(name)
        return out

    def list_dir(self, p: str) -> list[str]:
        """Top-level entry names under `p` (sorted). Used to enumerate a
        primary `node_modules` for the per-entry overlay — see module doc."""
        return sorted(os.listdir(p))

    def symlink(self, target: str, link: str) -> None:
        os.symlink(target, link)

    def read_text(self, p: str) -> str | None:
        """`p`'s text content, or `None` if it does not exist / cannot be
        read — used to derive a product's `@noctusai/*` seed re-points from
        its OWN `package.json` (see `_derive_product_repoints`) instead of
        assuming every product wants the same hand-maintained pair."""
        try:
            return Path(p).read_text(encoding="utf-8")
        except OSError:
            return None


def _plan_env_wiring(primary_root: str, wt_root: str, fs: FsOps) -> tuple[list[dict], list[dict]]:
    """Pure (read-only) planner. Returns (wire, skipped): `wire` = symlink/dir
    specs {link, target, kind} the recipe WOULD create; `skipped` = {link,
    reason} for anything best-effort skipped (absent primary source / a real
    dir already in the worktree). Order is deterministic: seed node_modules
    (whole-dir symlink — safe, see module doc), then per-product node_modules
    (per-entry overlay — the primary-contamination fix, see module doc) + the
    two @noctusai re-points. The repo-root `.env` is planned FIRST — see
    `_link_root_dotenv`."""
    wire: list[dict] = []
    skipped: list[dict] = []

    def _link_root_dotenv() -> None:
        """The repo-root `.env`, which every product frontend AND backend reads.

        WHY THIS IS PART OF wire_env. `.env` is gitignored, so a fresh worktree
        never has one. `createViteConfig` sets `envDir` to the TREE ROOT
        (`seed/framework/frontend/vite.config.factory.ts`), so a product SPA
        started from an unwired worktree gets no `VITE_SUPABASE_*` and
        `createProductSupabase` THROWS INSIDE A MODULE — before React mounts.
        The result is a blank white page with nothing in the console, which
        reads as "the app is broken" rather than "the env is missing". Cost
        ~15 min to diagnose during the igig e2e sweep (2026-09-01).

        Symlinked rather than copied so a later edit to the real `.env` is
        picked up everywhere, and because a COPY of a secrets file into a
        worktree is a second place for it to leak from. Gitignored at both ends
        ⇒ it can never be staged, so it cannot cause the divergence the
        self-branching gate exists to prevent."""
        src = os.path.join(primary_root, ".env")
        link = os.path.join(wt_root, ".env")
        if not fs.exists(src):
            skipped.append({"link": link, "reason": f"primary .env absent: {src}"})
            return
        if fs.is_dir(link):
            skipped.append({"link": link, "reason": "real directory at .env path"})
            return
        wire.append({"link": link, "target": src, "kind": "dotenv"})

    def _link_toolkit_node_modules() -> None:
        """`mcp/noctusai/node/node_modules` — the ts-morph runtime the
        lying-loading-state detector's Mode-B AST scan shells out to.

        Same class as `.env`: gitignored, so absent from every fresh worktree,
        and its absence degrades to a WARNING finding rather than an error —
        `test_negative_correct_gate_not_flagged` fails with
        `ts_morph_not_installed` and reads like a detector regression. Nothing
        nests inside it, so a whole-dir symlink is safe.
        """
        rel = os.path.join("mcp", "noctusai", "node", "node_modules")
        src = os.path.join(primary_root, rel)
        link = os.path.join(wt_root, rel)
        if not fs.exists(src):
            skipped.append({"link": link, "reason": (
                f"primary toolkit node_modules absent: {src} — the PRIMARY "
                f"checkout itself was never provisioned; run `npm install` "
                f"in {os.path.join(primary_root, 'mcp', 'noctusai', 'node')} first")})
            return
        if fs.is_dir(link) and not fs.is_symlink(link):
            skipped.append({"link": link, "reason": "real node_modules already present in worktree"})
            return
        wire.append({"link": link, "target": src, "kind": "node_modules"})

    _link_root_dotenv()
    _link_toolkit_node_modules()

    def _link_whole_node_modules(rel_pkg: str) -> None:
        """Seed-frontend node_modules ONLY. Nothing ever nests inside these
        (unlike products, no `@noctusai` re-point targets them) so a whole-dir
        symlink to primary carries no write-through hazard."""
        src = os.path.join(primary_root, rel_pkg, "node_modules")
        link = os.path.join(wt_root, rel_pkg, "node_modules")
        if not fs.exists(src):
            skipped.append({"link": link, "reason": (
                f"primary node_modules absent: {src} — the PRIMARY checkout "
                f"itself was never provisioned; run `npm install` in "
                f"{os.path.join(primary_root, rel_pkg)} first")})
            return
        if fs.is_dir(link):  # a REAL node_modules already in the worktree — never clobber/nest
            skipped.append({"link": link, "reason": "real node_modules already present in worktree"})
            return
        wire.append({"link": link, "target": src, "kind": "node_modules"})

    def _link_product_node_modules(rel_fe: str) -> bool:
        """Per-entry overlay (the primary-contamination fix). `link_dir`
        becomes a REAL directory in the worktree; every primary top-level
        package gets its own symlink EXCEPT `@noctusai`, wired separately
        below (always worktree-owned) — so no write ever lands through a
        shared symlink into the primary tree.

        Returns whether the worktree will end up with a REAL, populated
        `node_modules` for this product — either overlaid here, or already
        present. `False` means nothing is installed anywhere, and the
        caller must NOT then wire the `@noctusai` re-points (see there)."""
        src = os.path.join(primary_root, rel_fe, "node_modules")
        link_dir = os.path.join(wt_root, rel_fe, "node_modules")
        if not fs.exists(src):
            skipped.append({"link": link_dir, "reason": (
                f"primary node_modules absent: {src} — the PRIMARY checkout "
                f"itself was never provisioned; run `npm install` in "
                f"{os.path.join(primary_root, rel_fe)} first")})
            return False
        if fs.is_dir(link_dir):  # a REAL node_modules already in the worktree
            # (genuine local install, OR an already-overlaid worktree) — never
            # clobber/nest/re-sync.
            skipped.append({"link": link_dir, "reason": "real node_modules already present in worktree"})
            return True
        if fs.is_symlink(link_dir):
            # A stale whole-dir symlink — either left over from the pre-fix
            # scheme, or from a not-yet-re-wired worktree. Convert to a REAL
            # directory FIRST (planned before any entry below, so applied
            # first) so the per-entry links land in the WORKTREE, never
            # write-through into whatever the symlink currently targets.
            wire.append({"link": link_dir, "target": None, "kind": "ensure_real_dir"})
        for entry in fs.list_dir(src):
            if entry == "@noctusai":
                continue  # worktree-owned; wired below via the derived repoints
            wire.append({"link": os.path.join(link_dir, entry),
                        "target": os.path.join(src, entry), "kind": "node_modules_entry"})
        return True

    # seed packages first (the @noctusai re-points below point INTO the WORKTREE's
    # own copies of these, never through the product node_modules symlink).
    # DERIVED from what products actually declare (`_derive_seed_frontends`),
    # not a hand-maintained slug list.
    for rel_pkg in _derive_seed_frontends(primary_root, fs):
        _link_whole_node_modules(rel_pkg)

    # every product/<slug>/frontend with a primary node_modules → overlay + re-point,
    # each product's OWN `package.json` deciding which seed package(s) it re-points
    # (`_derive_product_repoints`) — never a single fleet-wide assumption.
    for slug in fs.list_product_frontends(primary_root):
        rel_fe = f"products/{slug}/frontend"
        has_node_modules = _link_product_node_modules(rel_fe)
        nm = os.path.join(wt_root, rel_fe, "node_modules")
        if not has_node_modules:
            # 🔴 Do NOT wire the @noctusai re-points into a node_modules that
            # does not exist. `_apply_env_wiring` does `os.makedirs` on each
            # link's parent, so planning them here CREATES
            # `node_modules/@noctusai/{lib,seed}` and nothing else — a
            # directory that LOOKS installed while holding two symlinks and
            # zero packages. Measured 2026-09-20: that partial dir satisfied
            # gate_sweep's `node_modules` precondition, so
            # `vite_build:academia-de-reciclagem` ran and failed on
            # `Cannot find module 'tailwindcss'` — a red about the wiring
            # wearing the clothes of a red about the code. Manufacturing a
            # half-state that reads as a whole one is the silent-error shape;
            # skipping loudly is the honest half.
            for dep, _seed_rel in _derive_product_repoints(primary_root, rel_fe, fs):
                skipped.append({"link": os.path.join(nm, dep), "reason": (
                    f"no node_modules to re-point into for {rel_fe} — wiring "
                    f"{dep} alone would manufacture a partial node_modules "
                    f"that reads as installed; run `npm ci` in "
                    f"{os.path.join(primary_root, rel_fe)} first")})
            continue
        for dep, seed_rel in _derive_product_repoints(primary_root, rel_fe, fs):
            link = os.path.join(nm, dep)
            target = os.path.join(wt_root, seed_rel)
            if not fs.exists(target):
                skipped.append({"link": link, "reason": f"worktree seed pkg absent: {target}"})
                continue
            wire.append({"link": link, "target": target, "kind": "@noctusai"})

    return wire, skipped


def _apply_env_wiring(wire: list[dict], fs: FsOps) -> tuple[list[dict], list[dict]]:
    """`ln -sfn` semantics, best-effort: create each planned symlink; if the link
    path is an existing symlink, replace it (force); if it is a real dir, SKIP
    (never clobber — should already be filtered by the planner, defensive here);
    any OS error is captured into `failed`, never raised. Returns (created, failed).
    `ensure_real_dir` specs (a stale whole-dir symlink being converted to a real
    worktree-owned directory — see `_plan_env_wiring`) are applied in list order
    BEFORE the entry/@noctusai symlinks planned to land under them, so every
    subsequent write lands in a REAL worktree directory — never written through
    a symlink into a shared target (the primary-contamination bug this fixes)."""
    created: list[dict] = []
    failed: list[dict] = []
    for spec in wire:
        link = spec["link"]
        try:
            if spec.get("kind") == "ensure_real_dir":
                if fs.is_symlink(link):
                    os.unlink(link)
                os.makedirs(link, exist_ok=True)
                created.append(spec)
                continue
            if fs.is_dir(link):
                failed.append({**spec, "reason": "real directory at link path — skipped"})
                continue
            if fs.is_symlink(link):
                os.unlink(link)  # `ln -sfn`: replace an existing symlink
            os.makedirs(os.path.dirname(link), exist_ok=True)
            fs.symlink(spec["target"], link)
            created.append(spec)
        except OSError as e:
            failed.append({**spec, "reason": f"{type(e).__name__}: {e}"})
    return created, failed


def _compact_wire_list(items: list[dict], *, sample_n: int = 5) -> dict[str, Any]:
    """Compact a `would_wire`/`wired`/`skipped` list to `{count, sample}`.

    A real repo's `wire_env` run enumerates every top-level package in every
    product frontend's `node_modules` — ~18,840 entries / ~1.2MB on the
    live fleet — which overflows the caller's tool-result budget on EVERY
    `action='start' wire_env=True` call, dry-run or not. The full list
    survives on disk (see `_write_wire_env_report`) so nothing is actually
    lost; pass `verbose=True` on the tool to get the full lists back inline
    instead of this compact form."""
    return {"count": len(items), "sample": items[:sample_n]}


def _write_wire_env_report(primary_root: str, slug: str, report: dict[str, Any]) -> str:
    """Persist the FULL wire_env plan/result to a gitignored per-repo file —
    `.claude/cache/wire-env-reports/<slug>.json` (the same `.claude/cache/`
    gitignore leg the keeper-mirror caches already use) — so the compact
    tool-result stays small without losing the detail. Overwritten on each
    call for that slug (last-run-only; the point is recoverability, not
    history). Returns the absolute path written."""
    out_dir = os.path.join(primary_root, ".claude", "cache", "wire-env-reports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{slug}.json")
    payload = {**report, "written_at": datetime.now(timezone.utc).isoformat()}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return out_path


def _settle_structural_caches(verbose: bool = False) -> dict[str, Any]:
    """Settle the Tier-1 SHARED structural caches against the at-rest primary
    tree at the end of a cross-tree integrate/cleanup.

    ``noc-graph`` lives in the worktree-shared ``.git/noctusai/cache/``
    (cache-portable-architecture); ``auto-improvement`` is per-tree since
    2026-09-22 (Tier 1a), so settling it here only refreshes the PRIMARY's
    own slot and can no longer flip a worktree's. During the
    worktree↔primary handoff the SAME shared cache is written from two working
    trees, so its stored ``aggregate_source_sha`` can briefly reflect a
    transient tree-state the at-rest primary tree does not match — surfacing as
    a noc-graph-stale warning right after a clean integrate. Both refreshes are
    ONLY-STALE (source-sha guarded ⇒ a no-op when already coherent) and
    BEST-EFFORT (a failure NEVER fails the integrate/cleanup; the
    ``check_all_cache_freshness`` keeper stays the net). Returns a small report
    for observability. See the s1 surface "noc-graph Tier-1 shared-cache
    coherence after cross-tree integrate/cleanup" (2026-05-30).
    """
    report: dict[str, Any] = {}
    try:
        from tools.noctus.dev import noc_graph_cache as _ng
        r = _ng.refresh(force=False)
        report["noc_graph"] = {"ok": True, "status": r.get("status"),
                               "source_sha": r.get("source_sha") or r.get("aggregate_source_sha")}
    except Exception as e:  # best-effort: never block teardown on a cache refresh
        if verbose:
            logger.debug("task_branch settle: noc-graph refresh skipped: %s", e)
        report["noc_graph"] = {"ok": False, "error": str(e)}
    try:
        from tools.noctus.dev import auto_improvement as _ai
        r = _ai.refresh(force=False)
        report["auto_improvement"] = {"ok": True, "status": r.get("status"),
                                      "source_sha": r.get("source_sha")}
    except Exception as e:
        if verbose:
            logger.debug("task_branch settle: auto-improvement refresh skipped: %s", e)
        report["auto_improvement"] = {"ok": False, "error": str(e)}
    return report


def _default_migration_collision_check(abs_wt_path: str) -> list[dict]:
    """Production default for the `action='integrate'` migration-collision
    gate — the REAL, unmodified keeper, scoped to the worktree that just
    rebased. Lazy import (mirrors `_settle_structural_caches` / the
    `REPO_ROOT` import elsewhere in this file) so a plain `status`/`start`
    call never pays the compliance-module import cost."""
    from .compliance import check_migration_number_collision
    return check_migration_number_collision(repo_root=Path(abs_wt_path))


class PointerOps:
    """The branch-tree pointer lifecycle, owned by the git lifecycle.

    `task_branch` is the one tool that KNOWS when a branch is forked, landed on
    dev, and torn down, so it writes the pointer transitions itself:

        start     → append `on_going` (the collision-zone claim)
        integrate → update `integrated-worktree-live` + the POST-REBASE commit
        cleanup   → update `shipped`

    Before 2026-09-23 none of these ran: every session appended and closed
    pointers by hand, forgot, and `check_branch_tree_mirror` (pre-push) or the
    ship-consent manifest caught it later: a gate standing in for a missing
    mechanism. Worse, `integrate` rebases, so a hand-recorded `commit` never
    lands on dev, and `session_end_sweep`'s healer could never prove the branch
    integrated. Pointers stayed `on_going` for months.

    Best-effort by construction: a pointer failure is REPORTED in the result
    (`pointer` key), never raised. The git lifecycle succeeding is the primary
    outcome, and the keeper `check_stale_branch_pointers` is the safety net if
    this mechanism ever misses. Writes use push_dev=False except `start`: the
    trailing `_drain_ledgers_from_primary` ships integrate/cleanup rows, while
    a claim must be visible on dev immediately.
    """

    def latest(self, branch: str) -> dict | None:
        from tools.noctus.dev import branch_pointer as bp
        return bp._latest_per_branch(bp._read_dev_ledger()).get(branch)

    def append(self, **kw: Any) -> dict[str, Any]:
        from tools.noctus.dev import branch_pointer as bp
        return bp.append(**kw)

    def update(self, **kw: Any) -> dict[str, Any]:
        from tools.noctus.dev import branch_pointer as bp
        return bp.update(**kw)


_TERMINAL_POINTER_STATUSES = frozenset({"shipped", "canceled", "stale"})


def _pointer_transition(
    ops: "PointerOps | None", *, branch: str, status: str,
    commit: str | None = None, notes: str,
) -> dict[str, Any]:
    """Move an existing non-terminal pointer to `status`. Never raises."""
    if ops is None:
        return {"status": "skipped", "reason": "no pointer ops (test/custom runner)"}
    try:
        prev = ops.latest(branch)
        if prev is None:
            return {"status": "no_pointer",
                    "reason": f"{branch} has no branch-tree pointer to transition"}
        if prev.get("status") in _TERMINAL_POINTER_STATUSES:
            return {"status": "already_terminal", "pointer_status": prev.get("status")}
        res = ops.update(branch=branch, status=status, commit=commit,
                         notes=notes, push_dev=False)
        if res.get("ok"):
            return {"status": "updated", "pointer_status": status,
                    "commit": (res.get("row") or {}).get("commit")}
        return {"status": "error", "error": res.get("error", "update failed")}
    except Exception as e:  # noqa: BLE001 — reported, never blocks the git lifecycle
        logger.warning("task_branch: pointer transition for %s failed: %s", branch, e)
        return {"status": "error", "error": str(e)[:300]}


def _pointer_claim(
    ops: "PointerOps | None", *, branch: str, base_ref: str, commit: str,
    wt_path: str, slug: str, project: str | None, brief: str | None,
    paths: list[str] | None, agent: str | None, role: str | None, parent: str | None,
) -> dict[str, Any]:
    """Append the `on_going` claim for a fresh branch unless one is already live."""
    if ops is None:
        return {"status": "skipped", "reason": "no pointer ops (test/custom runner)"}
    try:
        prev = ops.latest(branch)
        if prev is not None and prev.get("status") not in _TERMINAL_POINTER_STATUSES:
            return {"status": "already_claimed", "pointer_status": prev.get("status")}
        res = ops.append(
            branch=branch, base=base_ref, commit=commit, worktree=wt_path,
            role=role or "orchestrator", agent=agent or "self-branch",
            parent=parent or "dev", paths=list(paths or []), status="on_going",
            brief=brief or f"self-branch {slug}", project=project, push_dev=True,
        )
        if res.get("ok"):
            row = res.get("row") or {}
            return {"status": "claimed", "project": row.get("project"),
                    "pushed": bool((res.get("push") or {}).get("ok"))}
        return {"status": "error", "error": res.get("error", "append failed")}
    except Exception as e:  # noqa: BLE001 — reported, never blocks the fork
        logger.warning("task_branch: pointer claim for %s failed: %s", branch, e)
        return {"status": "error", "error": str(e)[:300]}


def _task_branch_is_write(bound_args: dict) -> bool:
    """`task_branch`'s REFUSE predicate (2026-09-18, the incident tool
    itself): only the MUTATING actions — `start` / `integrate` / `cleanup`
    — with `confirm=True` are a write. `action='status'` is always a read
    regardless of `confirm` (it never inspects the flag)."""
    return (
        bound_args.get("action") in {"start", "integrate", "cleanup"}
        and bool(bound_args.get("confirm", False))
    )


@_toolkit_freshness.refuse_gate("task_branch", write_predicate=_task_branch_is_write)
def task_branch(
    action: str = "status",
    slug: str | None = None,
    confirm: bool = False,
    remote: str = "origin",
    dev_branch: str = "dev",
    worktrees_dir: str = ".claude/worktrees",
    branch_prefix: str = "feat/",
    max_retries: int = 5,
    wire_env: bool = True,
    primary_root: str | None = None,
    run: Callable[..., tuple[int, str, str]] | None = None,
    fs: FsOps | None = None,
    salvage_recorder: Callable[..., Any] | None = None,
    settle: Callable[..., dict[str, Any]] | None = None,
    migration_check: Callable[[str], list[dict]] | None = None,
    pointer_ops: "PointerOps | None" = None,
    project: str | None = None,
    brief: str | None = None,
    paths: list[str] | None = None,
    agent: str | None = None,
    role: str | None = None,
    parent: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """`action` ∈ {status, start, integrate, cleanup}.

    Branch-tree pointer lifecycle (see `PointerOps`): `start` claims an
    `on_going` pointer (`project`/`brief`/`paths`/`agent`/`role`/`parent` fill
    it; `project` omitted ⇒ inherited from `parent`'s pointer), `integrate`
    records the post-rebase commit as `integrated-worktree-live`, `cleanup`
    closes it `shipped`. `pointer_ops` is the test seam; the production default
    runs only on the real runner (same rule as `settle`). Writes are dry-run unless
    `confirm`. Returns a structured plan/result; never raises on a refusal — it
    returns it (the refusal IS the safety net).

    `verbose=True` emits debug-level logging for each step of integrate/cleanup
    so future debugging is one re-run away (no code changes needed).

    `migration_check` (test seam; production default is the real
    `check_migration_number_collision`, scoped to the just-rebased worktree)
    — the `action='integrate'` migration-number-collision gate: a SECOND
    backstop, additional to pre-commit, that BLOCKS (not warns) when this
    branch's own migration collides with something the fresh rebase onto
    `origin/dev` just revealed. See the gate's inline comment in the
    `integrate` branch below for why blocking here is safe (no legitimate
    first-mover casualty, unlike pre-commit Leg B).

    `wire_env` (only meaningful on `action='start'`; DEFAULTS TO TRUE — a
    fresh worktree must come ready to run gates, `KB § PATTERNS/common/
    self-branching-mode.md § 5a`) auto-wires the §5a verification-env recipe
    into the fresh worktree AFTER it exists: symlink the PRIMARY tree's
    per-package `node_modules` into the worktree + re-point each product
    frontend's `@noctusai/*` file:-deps (DERIVED from that product's own
    `package.json`, never a hardcoded pair — see `_derive_product_repoints`)
    at the WORKTREE's own seed copies, so a vite build / vitest run inside
    the worktree sees the worktree's edits — and so `noctus.dev.
    predeploy_check` / the MCP toolkit's own pytest suite don't false-red on
    a missing local install (the 2026-09-17 four-incidents-one-session
    recurrence this formalizes). Pass `wire_env=False` to skip it (e.g. a
    doc-only slice on a large repo where the symlink pass is pure overhead).
    All target paths are gitignored ⇒ never staged. Honors dry-run: without
    `confirm` it REPORTS the plan (the symlinks it WOULD create) without
    touching the filesystem. Best-effort: missing primary node_modules (the
    reason names the exact `npm install` to run) / a real node_modules
    already in the worktree are REPORTED in `skipped`, never silent, never
    clobbered."""
    runner = run or _default_run_local
    fsops = fs or FsOps()
    # End-of-integrate/cleanup structural-cache settle (see _settle_structural_caches).
    # Explicit `settle` wins (test seam); otherwise run the real settle ONLY in the
    # production path (default runner) — an injected `run` means a test/custom context
    # that must not touch the real shared caches.
    settle_fn = settle if settle is not None else (
        _settle_structural_caches if run is None else None)
    # Same "production default ONLY on the real runner" rule as settle_fn —
    # an injected `run` means a test/custom context that must not shell out
    # to a real `check_migration_number_collision` filesystem scan.
    migration_check_fn = migration_check if migration_check is not None else (
        _default_migration_collision_check if run is None else None)
    # wire_env defaults True (KB § self-branching-mode.md § 5a — "a fresh
    # worktree must come ready to run gates"), but ONLY in the real
    # production path OR when the caller supplies an explicit primary_root.
    # Same "production-only" rule as settle_fn/migration_check_fn just
    # above: an injected `run` (a test/custom context) with no explicit
    # primary_root means the "worktree" this call reasons about doesn't
    # physically exist on disk — silently falling back to the REAL repo
    # tree here would write REAL symlinks into the caller's actual
    # `.claude/worktrees/<slug>` as a side effect of running a unit test.
    wire_env = wire_env and (primary_root is not None or run is None)
    # Same production-only rule: an injected `run` must never write the REAL
    # branch-tree ledger as a side effect of a unit test.
    pointer_fn = pointer_ops if pointer_ops is not None else (
        PointerOps() if run is None else None)

    def git(*args, cwd: str | None = None):
        return _git(runner, *args, cwd=cwd, dev_branch=dev_branch)

    if action not in {"status", "start", "integrate", "cleanup"}:
        return {"ok": False, "status": "error", "exit_code": 1,
                "error": f"unknown action '{action}' (expected status|start|integrate|cleanup)"}

    wt_path = f"{worktrees_dir}/{slug}" if slug else None
    branch = f"{branch_prefix}{slug}" if slug else None
    base: dict[str, Any] = {"ok": True, "action": action, "remote": remote,
                            "slug": slug, "branch": branch, "worktree": wt_path}

    # ── STATUS ── read-only: list active self-branch worktrees + ahead/behind
    if action == "status":
        git("fetch", remote, "--quiet")
        dev = _resolve(git, f"{remote}/{dev_branch}")
        rc, out, _e = git("worktree", "list", "--porcelain")
        mine: list[dict[str, Any]] = []
        for wt in _parse_worktrees(out if rc == 0 else ""):
            br = wt.get("branch", "")
            if worktrees_dir not in wt.get("path", ""):
                continue
            if not br.startswith(f"refs/heads/{branch_prefix}"):
                continue
            head = wt.get("head")
            ahead = len(_commits(git, dev, head)) if (dev and head) else None
            behind = len(_commits(git, head, dev)) if (dev and head) else None
            mine.append({
                "slug": br[len(f"refs/heads/{branch_prefix}"):],
                "branch": br[len("refs/heads/"):], "path": wt.get("path"),
                "head": head, "ahead": ahead, "behind": behind,
            })
        return {**base, "status": "status", "exit_code": 0, "dev_sha": dev,
                "active": mine,
                "message": f"{len(mine)} active self-branch worktree(s) vs {remote}/{dev_branch}."}

    if not slug:
        return {**base, "status": "error", "exit_code": 1,
                "error": f"action '{action}' requires slug=."}

    # ── START ── fetch → worktree add -b feat/<slug> origin/dev [→ wire_env]
    if action == "start":
        git("fetch", remote, "--quiet")
        dev = _resolve(git, f"{remote}/{dev_branch}")
        if not dev:
            return {**base, "status": "error", "exit_code": 1,
                    "error": f"cannot resolve {remote}/{dev_branch} (fetch failed?)."}
        plan = {**base, "base_sha": dev, "would_create": f"worktree {wt_path} on {branch} @ {dev[:9]}"}

        # resolve absolute PRIMARY tree + worktree roots for env-wiring (lazy:
        # only import settings when we actually need REPO_ROOT — keeps the
        # test path, which always injects primary_root, settings-free).
        def _roots() -> tuple[str, str]:
            root = primary_root
            if root is None:
                # LEDGER_ROOT (never REPO_ROOT): must be the PRIMARY checkout.
                # See workspace.get_ledger_root() docstring.
                from settings import LEDGER_ROOT  # lazy: avoids import cost otherwise
                root = str(LEDGER_ROOT)
            return root, os.path.join(root, worktrees_dir, slug)

        if not confirm:
            plan_extra: dict[str, Any] = {}
            if wire_env:
                proot, wt_root = _roots()
                would, skipped = _plan_env_wiring(proot, wt_root, fsops)
                if verbose:
                    plan_extra = {"wire_env": True, "would_wire": would, "skipped": skipped}
                else:
                    report_path = _write_wire_env_report(
                        proot, slug, {"wire_env": True, "would_wire": would, "skipped": skipped})
                    plan_extra = {
                        "wire_env": True,
                        "would_wire": _compact_wire_list(would),
                        "skipped": _compact_wire_list(skipped),
                        "full_report": report_path,
                    }
            return {**plan, **plan_extra, "status": "planned", "exit_code": 0,
                    "message": f"will fork {branch} off {remote}/{dev_branch} ({dev[:9]}) at "
                               f"{wt_path}{' + auto-wire the §5a verification env' if wire_env else ''}. "
                               "Pass confirm=True. Then work THERE + commit; "
                               "integrate with action='integrate'."}
        rc, out, err = git("worktree", "add", wt_path, "-b", branch, f"{remote}/{dev_branch}")
        already_existed = False
        if rc != 0:
            # Idempotent retrofit (the "worktree created outside task_branch"
            # edge case): a worktree that ALREADY EXISTS on exactly THIS
            # branch — forked by a bare `git worktree add`, or `start` being
            # re-run after `wire_env` shipped — is not a failure to surface;
            # `start` becomes "ensure this worktree exists + is wired", so
            # the retrofit path is a real re-runnable command, not a dead
            # end that sends the caller to a manual symlink recipe. Any
            # OTHER failure (path exists on a DIFFERENT branch, a genuine
            # git error) still surfaces as an error, unchanged.
            _rc_list, list_out, _e = git("worktree", "list", "--porcelain")
            existing_branch = _branch_for_path(list_out if _rc_list == 0 else "", wt_path)
            if existing_branch == branch:
                already_existed = True
            else:
                return {**plan, "status": "error", "exit_code": 1,
                        "error": f"worktree add failed: {err.strip() or out.strip()}"}
        wired_extra: dict[str, Any] = {}
        wired_count = 0
        if wire_env:
            proot, wt_root = _roots()
            would, skipped = _plan_env_wiring(proot, wt_root, fsops)
            created, failed = _apply_env_wiring(would, fsops)
            wired_count = len(created)
            all_skipped = skipped + failed
            if verbose:
                wired_extra = {"wire_env": True, "wired": created, "skipped": all_skipped}
            else:
                report_path = _write_wire_env_report(
                    proot, slug, {"wire_env": True, "wired": created, "skipped": all_skipped})
                wired_extra = {
                    "wire_env": True,
                    "wired": _compact_wire_list(created),
                    "skipped": _compact_wire_list(all_skipped),
                    "full_report": report_path,
                }
        pointer_result = _pointer_claim(
            pointer_fn, branch=branch, base_ref=f"{remote}/{dev_branch}@{dev[:9]}",
            commit=dev[:9], wt_path=wt_path, slug=slug, project=project, brief=brief,
            paths=paths, agent=agent, role=role, parent=parent)
        return {**plan, **wired_extra, "status": "started", "exit_code": 0,
                "already_existed": already_existed, "pointer": pointer_result,
                "message": f"{'reused already-existing' if already_existed else 'created'} "
                           f"{wt_path} on {branch}"
                           f"{' + wired %d env symlink(s)' % wired_count if wire_env else ''}. "
                           f"Work there (cd {wt_path}), commit on {branch}, then "
                           f"noctus.dev.task_branch action='integrate' slug='{slug}'."}

    # ── INTEGRATE ── rebase onto origin/dev → FF-push HEAD→dev (retry on race)
    if action == "integrate":
        git("fetch", remote, "--quiet")
        dev = _resolve(git, f"{remote}/{dev_branch}")
        head = _resolve(git, branch)
        if not dev or not head:
            return {**base, "status": "error", "exit_code": 1,
                    "error": f"cannot resolve {remote}/{dev_branch} or {branch}."}
        # Migration files THIS branch introduces relative to dev, BEFORE the
        # rebase moves anything — used below to scope the post-rebase
        # collision gate to directories this integrate actually touches (so
        # an unrelated product's migration collision elsewhere in the repo
        # never false-blocks an integrate that has nothing to do with it).
        _rc_mig, _mig_diff_out, _mig_diff_err = git("diff", "--name-only", f"{dev}...{head}")
        introduced_migrations = sorted({
            ln.strip() for ln in _mig_diff_out.splitlines()
            if ln.strip().endswith(".sql") and "/backend/migrations/" in ln.strip()
        })
        introduced_migration_dirs = {
            p.rsplit("/", 1)[0] for p in introduced_migrations
        }
        ahead = _commits(git, dev, head)
        if not ahead and _is_ancestor(git, head, dev):
            return {**base, "status": "up_to_date", "exit_code": 0, "dev_sha": dev,
                    "message": f"{branch} has nothing {remote}/{dev_branch} lacks — nothing to integrate."}
        behind = _commits(git, head, dev)
        plan = {**base, "dev_sha": dev, "branch_sha": head,
                "ahead": len(ahead), "behind": len(behind), "incoming_commits": ahead[:20]}
        if not confirm:
            return {**plan, "status": "planned", "exit_code": 0,
                    "message": (f"will rebase {branch} onto {remote}/{dev_branch} "
                                f"(behind {len(behind)}) then FF-push {len(ahead)} commit(s) → "
                                f"{dev_branch} (retry on concurrent-push race). Pass confirm=True.")}
        # ACT — auto-stash known-benign refresh artifacts, then rebase-then-push
        # loop; fetch fresh each iteration (the race).
        #
        # ROOT-CAUSE FIX (2026-05-28, N=5+ observed): pre-commit / cache-refresh
        # hooks write side-effect files into the worktree (KNOWLEDGE-BASE/
        # AGENT-CONTEXT.md, project-history/vector-costs.ndjson, etc.). These
        # appear in `git status --porcelain` ⇒ `git rebase` refuses ("error:
        # cannot rebase: You have unstaged changes") ⇒ tool returns rc≠0 ⇒ tool
        # surfaces status=conflict with empty conflicted_files. The actual rebase
        # would be a clean FF — there are no real conflicts. Fix: classify dirty
        # files into benign (the known patterns) vs real (actual task work);
        # auto-stash benign files before the rebase, pop stash after success.
        # Only if REAL dirty files exist (not just benign ones) do we block.
        benign_stashed = False
        if verbose:
            logger.debug("task_branch.integrate: classifying dirty files in %s", wt_path)
        benign_files, real_files = _classify_dirty_files(runner, wt_path)
        # `project-history/*.ndjson` ledger rows are benign but must NEVER be
        # stashed — the stash stack is shared with every other worktree of
        # this repo (see `_benign_stash.is_ledger_ndjson`; 2026-09-16 near-loss,
        # recovered by hand at `3789fefc`). Commit them instead; only the
        # genuinely-derived remainder (`.claude/cache/*`, KB-count docs) is
        # still stash-and-popped below.
        ledger_files, stash_files = _shared_partition_ledger(benign_files)
        if ledger_files:
            if verbose:
                logger.debug("task_branch.integrate: committing %d ledger row(s) "
                             "instead of stashing: %s", len(ledger_files), ledger_files)
            if _commit_ledger_rows_in_worktree(runner, wt_path, ledger_files, verbose) is None:
                # Best-effort fell through (e.g. a pre-commit hook already staged
                # the identical content moments earlier, leaving a git index
                # quirk with nothing real left to commit) — fall back to the
                # historically-safe stash rather than leaving these paths
                # unresolved and blocking the rebase.
                stash_files = ledger_files + stash_files
        if real_files and not stash_files:
            # Real dirty files with no stashable benign files — block before even
            # trying to rebase (saves one rebase attempt + abort cycle).
            if verbose:
                logger.debug("task_branch.integrate: real dirty files block rebase: %s",
                             real_files)
        elif stash_files:
            if verbose:
                logger.debug("task_branch.integrate: found %d benign artifact(s) to stash: %s",
                             len(stash_files), stash_files)
            benign_stashed = _stash_benign_artifacts(runner, wt_path, stash_files, verbose)
            if benign_stashed and verbose:
                logger.debug("task_branch.integrate: benign artifacts stashed; "
                             "proceeding with rebase")

        for attempt in range(1, max_retries + 1):
            if verbose:
                logger.debug("task_branch.integrate: attempt %d/%d — fetch + rebase",
                             attempt, max_retries)
            git("fetch", remote, "--quiet")
            rc, out, err = git("rebase", f"{remote}/{dev_branch}", cwd=wt_path)
            if rc != 0:
                # Rebase failed — distinguish "refused" (worktree still dirty after
                # stash, rebase never started) from "conflicted" (rebase started and
                # hit content conflicts). The discriminator is the presence of the
                # `.git/rebase-merge` (or `.git/rebase-apply`) directory: git creates
                # this directory as soon as the rebase begins applying patches; if it
                # is ABSENT after a rc≠0, the rebase was REFUSED before it started
                # (e.g. "error: cannot rebase: You have unstaged changes") — likely
                # hook chatter re-dirtying the worktree after our stash. A "refused"
                # rebase has no `--abort` state and `diff --diff-filter=U` returns
                # nothing, producing the phantom status=conflict with empty
                # conflicted_files. In that case surface as dirty-block, not conflict.
                rebase_in_progress = _rebase_in_progress(runner, wt_path)
                _rc2, cout, _ce = git("diff", "--name-only", "--diff-filter=U", cwd=wt_path)
                conflicted = [ln.strip() for ln in cout.splitlines() if ln.strip()]
                if rebase_in_progress:
                    git("rebase", "--abort", cwd=wt_path)
                # Restore the stash even on failure so the worktree is clean.
                if benign_stashed:
                    _pop_stash(runner, wt_path, benign_stashed, verbose)
                    benign_stashed = False
                # Re-classify after the abort (or refused) to give accurate diagnostics.
                _, real_after = _classify_dirty_files(runner, wt_path)
                if not rebase_in_progress and not conflicted:
                    # Rebase was REFUSED (never started) — hook chatter re-dirtied the
                    # worktree after we stashed. Surface as a dirty-block, not a conflict,
                    # so the caller knows to inspect the worktree's dirty files rather
                    # than looking for merge conflicts. This is Bug B's phantom conflict.
                    refused_msg = (err or out or "").strip()
                    if verbose:
                        logger.debug(
                            "task_branch.integrate: rebase was REFUSED (no rebase-merge dir), "
                            "not conflicted. stderr: %s", refused_msg)
                    return {**plan, "status": "dirty_blocked", "exit_code": 1,
                            "conflicted_files": [],
                            "blocked_by_dirty": real_after,
                            "rebase_refused": True,
                            "message": (
                                f"rebase of {branch} onto {remote}/{dev_branch} was REFUSED "
                                f"(the worktree is dirty after auto-stash — likely post-checkout "
                                f"hook chatter re-dirtied files). No conflict markers present. "
                                f"Dirty files: {real_after}. "
                                f"git output: {refused_msg or '(none)'}. "
                                f"Run `git status` in the worktree, resolve the dirty files "
                                f"(commit or stash), then re-run integrate.").strip()}
                detail = (f"Dirty files present before rebase: benign={benign_files} "
                          f"real={real_files}; conflicted after rebase: {conflicted}. "
                          f"If conflicted_files is empty, check for uncommitted "
                          f"non-benign files in the worktree."
                          if not conflicted else "")
                return {**plan, "status": "conflict", "exit_code": 1,
                        "conflicted_files": conflicted,
                        "blocked_by_dirty": real_after,
                        "message": (f"rebase of {branch} onto {remote}/{dev_branch} hit conflicts "
                                    f"in {conflicted or 'unknown files'}; aborted to keep the "
                                    "worktree clean. Resolve manually in the worktree, then re-run "
                                    f"integrate. {detail}").strip()}
            if verbose:
                logger.debug("task_branch.integrate: rebase succeeded; pushing to %s", dev_branch)
            # ── Migration-number collision gate — the SECOND backstop ──
            #
            # Reuses `check_migration_number_collision` UNCHANGED (Leg A
            # stays high/blocking, Leg B stays warning at pre-commit — this
            # does NOT touch that). The worktree just rebased onto FRESH
            # origin/dev, so Leg A's plain directory scan now sees BOTH
            # origin/dev's migrations AND this branch's new one(s) together —
            # a real on-disk duplicate needs no new detection logic here.
            #
            # WHY block here when pre-commit Leg B only warns: at pre-commit
            # time neither of two parallel branches has "lost" yet, so
            # blocking would punish whichever happens to commit first for
            # something not their fault (see check_migration_number_collision's
            # own docstring). At INTEGRATE time that ambiguity is gone — by
            # definition, whoever calls integrate right now is the one about
            # to land on dev, i.e. always the "merges second" party relative
            # to any still-unmerged sibling. Blocking here has no legitimate-
            # first-mover casualty; it just moves today's incident's discovery
            # from "the tech-lead's eventual commit, after all the work is
            # done" to "the moment THIS branch tries to land."
            #
            # Scoped to directories THIS branch's own migrations touch, so an
            # unrelated collision elsewhere in the repo never false-blocks an
            # integrate that has nothing to do with it.
            if introduced_migration_dirs and migration_check_fn is not None:
                # LEDGER_ROOT (never REPO_ROOT): must be the PRIMARY checkout.
                # See workspace.get_ledger_root() docstring.
                from settings import LEDGER_ROOT as _LEDGER_ROOT  # lazy, mirrors _default_run_local
                abs_wt_path = str((_LEDGER_ROOT / wt_path).resolve())
                try:
                    mig_findings = migration_check_fn(abs_wt_path)
                except Exception as exc:  # never let the checker crash integrate
                    mig_findings = []
                    if verbose:
                        logger.debug("task_branch.integrate: migration_check_fn raised: %s", exc)
                relevant = [
                    f for f in mig_findings
                    if str(f.get("file", "")).rstrip("/") in introduced_migration_dirs
                ]
                if relevant:
                    if benign_stashed:
                        _pop_stash(runner, wt_path, benign_stashed, verbose)
                        benign_stashed = False
                    return {**plan, "status": "blocked", "exit_code": 1,
                            "introduced_migrations": introduced_migrations,
                            "migration_collision_findings": relevant,
                            "reason": (
                                f"{branch} introduces a migration-number collision "
                                f"({len(relevant)} finding(s)) — renumber before "
                                "integrating. This is the SAME check pre-commit "
                                "runs (check_migration_number_collision); it fires "
                                "here too because a rebase onto fresh origin/dev "
                                "is exactly the moment a latent (pre-commit "
                                "warning-only) collision becomes real."),
                            "message": (
                                f"rebase of {branch} onto {remote}/{dev_branch} succeeded, "
                                "but the resulting tree carries a migration-number "
                                "collision this branch introduced. Not pushed."
                            )}
            rc, out, err = git("push", remote, f"HEAD:refs/heads/{dev_branch}", cwd=wt_path)
            if rc == 0:
                # Pop stash AFTER the push so the worktree ends clean (the benign
                # files reappear but that's fine — they're tracked + committed elsewhere).
                if benign_stashed:
                    _pop_stash(runner, wt_path, benign_stashed, verbose)
                    benign_stashed = False
                new_dev = _resolve(git, f"{remote}/{dev_branch}")
                new_head = _resolve(git, branch)
                result = {**plan, "status": "integrated", "exit_code": 0, "attempts": attempt,
                          "new_dev_sha": new_dev, "verified": new_dev == new_head,
                          "message": (f"integrated {len(ahead)} commit(s) to {dev_branch} "
                                      f"(attempt {attempt}). Tear down: action='cleanup' slug='{slug}'.")}
                # Record the POST-REBASE sha: the pre-rebase commit a hand
                # pointer carried is never on dev, which is why pointers could
                # not be proven integrated and stayed on_going for months.
                result["pointer"] = _pointer_transition(
                    pointer_fn, branch=branch, status="integrated-worktree-live",
                    commit=(new_head or "")[:9] or None,
                    notes=f"task_branch integrate → {dev_branch}@{(new_dev or '')[:9]}")
                if settle_fn is not None:
                    try:
                        result["cache_settle"] = settle_fn()
                    except Exception as e:  # best-effort — never fail a clean integrate
                        result["cache_settle"] = {"ok": False, "error": str(e)}
                # 🔴 AFTER the settle AND the pointer write, deliberately — see
                # `_drain_ledgers_from_primary`. Both dirty ledgers, so a drain
                # placed before them could never ship what they write.
                try:
                    result["ledger_drain"] = _drain_ledgers_from_primary(
                        runner, root=_resolve_primary_root(primary_root),
                        dev_branch=dev_branch, remote=remote, verbose=verbose)
                except Exception as e:  # best-effort — never fail a clean integrate
                    result["ledger_drain"] = {"ok": False, "error": str(e)}
                return result
            # non-FF: a peer pushed between rebase and push → loop, re-fetch+rebase
            if verbose:
                logger.debug("task_branch.integrate: push rejected (concurrent peer push) "
                             "on attempt %d — re-fetching + rebasing", attempt)
        # All attempts exhausted — restore stash so we don't leave the worktree stashed.
        if benign_stashed:
            _pop_stash(runner, wt_path, benign_stashed, verbose)
        return {**plan, "status": "error", "exit_code": 1,
                "error": f"could not FF-push to {dev_branch} after {max_retries} attempts "
                         "(persistent concurrent pushes). Retry integrate."}

    # ── CLEANUP ── SALVAGE-before-delete → remove worktree (refuse-if-dirty) →
    #               prune → delete merged branch.
    # A worktree delete is the worktree analogue of archiving a project (KB §
    # PATTERNS/storage-hygiene.md § 2.3) ⇒ it mirrors archive's learn-before-
    # archive. THREE legs at this sanctioned single-worktree teardown — the bulk
    # sweeps (mole / cleanup_stale_worktrees) already carry leg 2; this path was
    # the gap (a precise teardown could silently skip salvage; a manual `git
    # worktree remove` skips all three — that's the 2026-05-25 drift):
    #   1 LEARNINGS  (discipline, surfaced as a checkpoint): extract durable
    #     knowledge → KB/memory before the lossy delete.
    #   2 RECOVERY POINTER (MECHANICAL, below): branch+SHA → the tracked ledger.
    #   3 STORAGE HYGIENE (sequenced): a mole worktree-sweep before the delete.
    if verbose:
        logger.debug("task_branch.cleanup: starting for slug=%s wt_path=%s", slug, wt_path)
    git("fetch", remote, "--quiet")
    # Resolve the worktree's ACTUAL branch from the worktree list (the dir is the
    # stable key) — robust to a reused/renamed worktree whose branch ≠ feat/<slug>.
    # Without this the slug→branch assumption resolves a nonexistent branch, so the
    # recovery-pointer leg silently no-ops + branch -d fails (2026-05-25 dogfood
    # gap, fixed on contact).
    rc_wl, wl_out, _wl = git("worktree", "list", "--porcelain")
    actual = _branch_for_path(wl_out if rc_wl == 0 else "", wt_path)
    if actual and actual != branch:
        branch = actual
        base["branch"] = branch
    dev = _resolve(git, f"{remote}/{dev_branch}")
    head = _resolve(git, branch)
    merged = bool(dev and head and _is_ancestor(git, head, dev))
    if head and not merged:
        return {**base, "status": "blocked", "exit_code": 1, "dev_sha": dev, "branch_sha": head,
                "reason": f"{branch} has commit(s) not on {remote}/{dev_branch} — integrate first "
                          "(refusing to delete unintegrated work)."}
    ritual = {
        "1_extract_learnings": (
            "BEFORE deleting, extract durable knowledge from this worktree → "
            "KB/memory (findings.md, return-notes, bugs found, follow-ups). The "
            "delete is LOSSY for anything not on dev or already in KB/memory "
            "(learnings leg — discipline; mirrors archive's learn-before-archive)."),
        "2_record_recovery_pointer": (
            f"branch+SHA → project-history/worktree-salvage.ndjson "
            "(MECHANICAL — recorded below; commit the ledger like ledger.ndjson)."),
        "3_mole_sweep_before_delete": (
            "Run noctus.dev.mole(mode='sweep', scope='worktrees') for storage "
            "hygiene BEFORE confirming the delete."),
        "4_remove": "git worktree remove (refuse-if-dirty) + branch -d (merged-only).",
    }
    plan = {**base, "branch_merged": merged, "cleanup_ritual": ritual,
            "learnings_checkpoint": ritual["1_extract_learnings"]}
    if not confirm:
        return {**plan, "status": "planned", "exit_code": 0,
                "message": (f"will SALVAGE then remove worktree {wt_path}: record the recovery "
                            f"pointer ({branch}+SHA) to the tracked salvage ledger + surface the "
                            f"learnings checkpoint, then remove (refuses if dirty) + delete merged "
                            f"branch {branch}. Extract learnings + run a mole worktree-sweep first. "
                            "Pass confirm=True.")}
    # Leg 2 — MECHANICAL recovery pointer: record branch+SHA to the TRACKED ledger
    # BEFORE removal (best-effort; the recorder never raises ⇒ never blocks teardown).
    # Shared `_worktree_salvage.record_sweep` — one source of truth with the bulk
    # sweeps (no parity drift). Injectable for tests (zero real IO).
    #
    # Record to the PRIMARY checkout's ledger (root), NOT the worktree's: the bulk
    # mole / cleanup_stale_worktrees sweeps already canonicalize on the primary
    # ledger (mole.py passes `root`), and writing it here keeps the WORKTREE clean
    # so Leg 2b needs no worktree-side commit + nothing lands on the to-be-deleted
    # branch (the 2026-06-30 rebase-integrated-slug lost-row fix).
    salvage_ledger = None
    root = primary_root
    if head:
        recorder = salvage_recorder
        if recorder is None:
            from tools.noctus.dev import _worktree_salvage as _wsv  # lazy import
            recorder = _wsv.record_sweep
        if root is None:
            # LEDGER_ROOT (never REPO_ROOT): the recovery-pointer ledger must
            # land in the PRIMARY checkout. See workspace.get_ledger_root()
            # docstring.
            from settings import LEDGER_ROOT  # lazy: only when not injected
            root = str(LEDGER_ROOT)
        rec_path = recorder(Path(root), [{
            "path": wt_path, "branch": branch, "sha": head,
            "reason": "task_branch cleanup (learn-before-delete)"}])
        salvage_ledger = str(rec_path) if rec_path else None
    # Leg 2b — commit & FF-push the ledger entry FROM THE PRIMARY dev CHECKOUT
    # BEFORE remove. The row was recorded to the PRIMARY ledger (Leg 2), so the
    # WORKTREE stays clean (`git worktree remove` needs no worktree-side commit)
    # and NOTHING lands on the to-be-deleted feature branch. The push uses the
    # robust fetch → divergence-guard → rebase-onto-origin/dev → FF-push idiom
    # (shared with branch_pointer): when origin/dev advanced past the branch base
    # the rebase replays the ledger-only commit cleanly (union-merge), so the row
    # reliably lands on origin/dev — the 2026-06-30 lost-row fix for rebase-
    # integrated slugs (the old worktree-HEAD:dev push was non-FF → orphaned the
    # commit on the force-deleted branch). Best-effort: a push failure is reported
    # (salvage_pushed=False, salvage_push_reason=<why>) but cleanup proceeds — the
    # row is on local dev (ships with the next dev push) + idempotent next-time,
    # and the bulk-sweep keepers still find it. `salvage_push_reason` is the
    # no-silent-errors fix for the 2026-08-31 divergence-loop incident: a bare
    # `salvage_pushed: false` gave the caller no way to tell "genuinely diverged,
    # needs a human" apart from "will self-heal next run" — see
    # `_push_salvage_ledger_from_primary` / `_ledger_push.commit_and_ff_push_ledger`
    # for the possible `status` values (dirty_blocked / non-ledger-ahead / rebase
    # conflict / push-failed-after-retry).
    salvage_pushed = False
    salvage_push_reason: str | None = None
    if salvage_ledger:
        rel_ledger = "project-history/worktree-salvage.ndjson"
        if verbose:
            logger.debug("task_branch.cleanup: committing + FF-pushing salvage ledger "
                         "from primary checkout %s: %s", root, rel_ledger)
        salvage_push_result = _push_salvage_ledger_from_primary(
            runner, root=str(root), rel_ledger=rel_ledger,
            dev_branch=dev_branch, remote=remote, verbose=verbose)
        salvage_pushed = bool(salvage_push_result.get("pushed"))
        if not salvage_pushed:
            salvage_push_reason = (
                salvage_push_result.get("error")
                or f"push not attempted (status={salvage_push_result.get('status')!r})"
            )
            logger.warning("task_branch.cleanup: salvage ledger push did not land: %s",
                           salvage_push_reason)
    # Attempt the remove. If it fails, check whether the only "dirty" files
    # are gitignored (e.g. `.claude/cache/*.sqlite`). If so, the refusal is
    # spurious — git considers those files non-blocking. We force-remove via
    # a direct subprocess call (intentionally bypassing _git() whose banned-
    # token list guards history-rewriting ops, not clean-worktree teardown).
    rc, out, err = git("worktree", "remove", wt_path)
    if rc != 0:
        if _is_dirty_excluding_gitignored(runner, wt_path):
            return {**plan, "status": "error", "exit_code": 1, "salvage_ledger": salvage_ledger,
                    "error": f"worktree remove refused (has real uncommitted changes — "
                             f"integrate or discard first): {err.strip() or out.strip()}"}
        # Only gitignored files present — safe to force-remove (verified clean).
        # LEDGER_ROOT (never REPO_ROOT): must be the PRIMARY checkout. See
        # workspace.get_ledger_root() docstring.
        from settings import LEDGER_ROOT  # lazy: only when not injected
        abs_wt = wt_path if os.path.isabs(wt_path) else os.path.join(str(LEDGER_ROOT), wt_path)
        rc2, _o2, err2 = runner(["git", "worktree", "remove", "--force", abs_wt])
        if rc2 != 0:
            return {**plan, "status": "error", "exit_code": 1, "salvage_ledger": salvage_ledger,
                    "error": f"worktree force-remove failed (gitignored-only path): "
                             f"{err2.strip() or _o2.strip()}"}
    git("worktree", "prune")
    rc, out, err = git("branch", "-d", branch)
    if rc != 0:
        return {**plan, "status": "partial", "exit_code": 1, "worktree_removed": True,
                "salvage_ledger": salvage_ledger,
                "error": f"worktree removed but branch -d refused (unmerged?): "
                         f"{err.strip() or out.strip()}"}
    result = {**plan, "status": "cleaned", "exit_code": 0, "worktree_removed": True,
              "branch_deleted": True, "salvage_ledger": salvage_ledger,
              "salvage_pushed": salvage_pushed,
              "salvage_push_reason": salvage_push_reason,
              "message": f"removed {wt_path} + deleted {branch} (recovery pointer → "
                         f"{salvage_ledger or 'ledger'}). Back on {dev_branch} baseline."
                         + ("" if salvage_pushed or not salvage_ledger else
                            f" NOTE: salvage row committed locally but NOT pushed — "
                            f"{salvage_push_reason}")}
    # Merged (checked above) + worktree removed ⇒ the lifecycle is over.
    result["pointer"] = _pointer_transition(
        pointer_fn, branch=branch, status="shipped",
        notes=f"task_branch cleanup: merged into {dev_branch}, worktree removed")
    if settle_fn is not None:
        try:
            result["cache_settle"] = settle_fn()
        except Exception as e:  # best-effort — never fail a completed teardown
            result["cache_settle"] = {"ok": False, "error": str(e)}
    # 🔴 AFTER the settle, deliberately — see `_drain_ledgers_from_primary`.
    # Leg 2b above already shipped the salvage row; this ships everything ELSE
    # that is dirty (auto-improvement rows logged during the session, and
    # anything the settle just wrote), which is the half that had no stage.
    try:
        result["ledger_drain"] = _drain_ledgers_from_primary(
            runner, root=_resolve_primary_root(primary_root),
            dev_branch=dev_branch, remote=remote, verbose=verbose)
    except Exception as e:  # best-effort — never fail a completed teardown
        result["ledger_drain"] = {"ok": False, "error": str(e)}
    return result


def register(server) -> None:
    @server.tool(
        name="noctus.dev.task_branch",
        description=(
            "Run the self-branching-mode per-task git lifecycle (KB § PATTERNS/"
            "self-branching-mode.md): a peer terminal-agent self-isolates any "
            "WRITING task in a per-task worktree off origin/dev, then integrates "
            "straight to origin/dev — never switching the shared checkout under a "
            "sibling (§9a). action='status' (default) lists active self-branch "
            "worktrees + ahead/behind vs origin/dev (read-only); action='start' "
            "slug= forks a worktree on feat/<slug> off origin/dev; action="
            "'integrate' slug= rebases onto origin/dev then FF-pushes to dev "
            "(retry on the concurrent-push race; a rebase conflict is aborted + "
            "surfaced, never auto-resolved; a migration file this branch "
            "introduces is re-checked for a number collision AFTER the rebase "
            "and BLOCKS the push if found); action='cleanup' slug= SALVAGES "
            "before deleting (learn-before-delete, KB § storage-hygiene § 2.3): "
            "records the branch+SHA recovery pointer to the tracked worktree-"
            "salvage ledger (MECHANICAL — same leg the bulk sweeps carry) + "
            "surfaces the learnings-extraction checkpoint + sequences a mole "
            "worktree-sweep, THEN removes the worktree (refuses if dirty) + "
            "deletes the merged branch. Writes are "
            "DRY-RUN by default — pass confirm=True. Pushes ONLY to dev (main/"
            "prod move via noctus.dev.release); FF/rebase-only, never force/reset/"
            "switch. action='start' wire_env DEFAULTS TO TRUE — every fresh "
            "worktree auto-wires the §5a verification env by construction "
            "(symlink the PRIMARY tree's per-package node_modules in + re-point "
            "each product frontend's @noctusai/* deps, DERIVED from that "
            "product's own package.json, at the worktree's seed copies) so a "
            "vite build / vitest / noctus.dev.predeploy_check can run THERE "
            "without false-redding on a missing local install (pass "
            "wire_env=False to skip for a doc-only slice); all gitignored ⇒ "
            "never staged; best-effort (missing/real-dir paths reported in "
            "skipped — a missing PRIMARY node_modules names the exact `npm "
            "install` to run — never clobbered) and dry-run-honored (reports "
            "would_wire without confirm). wire_env's would_wire/wired/skipped "
            "default to a COMPACT {count, sample} shape + a full_report path (a "
            "real repo enumerates ~18,840 symlink entries there, which "
            "overflows the tool-result budget) — pass verbose=True for the "
            "full inline lists instead. TOOLKIT-STALENESS GUARD (2026-09-18, "
            "the incident this tool caused): a confirm=True call on a "
            "MUTATING action (start/integrate/cleanup) REFUSES (status="
            "'refused_stale_toolkit', exit_code=1) when this MCP server's "
            "own module graph has drifted from disk since it was imported "
            "— a stale task_branch once silently stopped provisioning "
            "worktrees while still reporting status='started', exit 0. "
            "action='status' and any confirm=False plan call are only "
            "warned (toolkit_stale + a warnings entry), never refused. "
            "allow_stale_toolkit=True is the escape hatch (almost always "
            "wrong). See noctus.dev.toolkit_freshness. "
            "BRANCH-TREE POINTER LIFECYCLE (2026-09-23, owned here so nobody closes pointers "
            "by hand): start claims an on_going pointer (project/brief/paths/agent/role/parent "
            "fill it; project omitted => inherited from parent's pointer), integrate records "
            "the POST-REBASE commit as integrated-worktree-live, cleanup closes it shipped; the "
            "outcome rides on result['pointer'] and never blocks the git lifecycle. "
            "status: status|planned|started|integrated|conflict|up_to_date|"
            "cleaned|partial|blocked|refused_stale_toolkit|error."
        ),
    )
    def _task_branch(
        action: str = "status",
        slug: str | None = None,
        confirm: bool = False,
        wire_env: bool = True,
        verbose: bool = False,
        allow_stale_toolkit: bool = False,
        project: str | None = None,
        brief: str | None = None,
        paths: list[str] | None = None,
        agent: str | None = None,
        role: str | None = None,
        parent: str | None = None,
    ) -> dict:
        return task_branch(action=action, slug=slug, confirm=confirm,
                           wire_env=wire_env, verbose=verbose,
                           allow_stale_toolkit=allow_stale_toolkit,
                           project=project, brief=brief, paths=paths,
                           agent=agent, role=role, parent=parent)


__all__ = ["task_branch", "_ALLOWED_GIT", "_BANNED_TOKENS", "_BENIGN_REFRESH_PATTERNS",
           "_assert_push_targets_dev", "_parse_worktrees", "_branch_for_path",
           "_is_dirty_excluding_gitignored", "_classify_dirty_files",
           "_rebase_in_progress", "_stash_benign_artifacts", "_pop_stash",
           "_commit_ledger_rows_in_worktree",
           "_plan_env_wiring", "_apply_env_wiring",
           "_compact_wire_list", "_write_wire_env_report",
           "FsOps", "register"]
