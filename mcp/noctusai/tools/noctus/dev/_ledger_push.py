"""Shared ledger FF-push helper — the N=3 DRY lift of the ``commit a
``project-history/*.ndjson`` ledger row on the primary ``dev`` checkout, then
fetch → divergence-guard → rebase-onto-origin/dev → FF-push (best-effort, one
retry on the concurrent-push race)`` idiom.

Two ledger writers hand-replicated this before the lift:
  * ``branch_pointer._ff_or_rebase_push_to_dev`` — pushes an ALREADY-committed
    HEAD (the branch-tree pointer ledger + its mirror).
  * ``task_branch._push_salvage_ledger_from_primary`` — path-scoped commits the
    worktree-salvage ledger row THEN pushes it.

Both now delegate to :func:`commit_and_ff_push_ledger` so a future 3rd ledger
inherits the idiom instead of hand-replicating it a fourth time.

Why the idiom is safe (and conflict-free): the ``project-history/*.ndjson``
ledgers carry a ``merge=union`` gitattribute + are append-only, so a
behind/diverged local ``dev`` base replays cleanly on rebase. They are ALSO the
only cache-exempt paths — a push that changes only ledger files must never
trigger a cache refresh. The divergence guard enforces the flip side: it
REFUSES to push when any NON-ledger commit is ahead of ``origin/<dev>``, so
delegating the push from the primary checkout can never leak unrelated work
onto dev.

KB § PATTERNS/architect/branch-tree-tracking.md · KB § PATTERNS/common/self-branching-mode.md
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from tools.noctus.dev._benign_stash import (
    classify_dirty,
    dirty_blocked_result,
    pop_stash,
    stash_benign,
)

logger = logging.getLogger(__name__)

# (rc, stdout, stderr) subprocess runner — the injected git seam. Both call
# sites pass a runner taking ``(cmd, cwd=None)``; the helper always calls it
# with a single positional ``cmd`` (cwd defaults to the runner's repo root).
Runner = Callable[..., tuple[int, str, str]]


def _git(runner: Runner, root: str | None, *args: str) -> tuple[int, str, str]:
    """Run ``git [-C <root>] <args>`` through the injected runner.

    ``root`` present  → ``git -C <root> …`` (target the primary checkout even
    when the caller's cwd is a worktree — the task_branch salvage case).
    ``root`` None     → ``git …`` (the runner's own cwd is the repo root — the
    branch_pointer pointer case).
    """
    cmd = ["git", *(["-C", root] if root else []), *args]
    return runner(cmd)


def commit_and_ff_push_ledger(
    *,
    runner: Runner,
    rel_paths: list[str],
    dev_branch: str = "dev",
    remote: str = "origin",
    commit_msg: str | None = None,
    root: str | None = None,
    already_committed: bool = False,
    check_exists: Path | None = None,
    _fetch: bool = True,
    _log_prefix: str = "ledger_push",
) -> dict[str, Any]:
    """Commit (optionally) + FF-push a cache-exempt ledger row to ``dev``.

    Supports BOTH ledger-writer shapes:

    * ``already_committed=False`` (path-scoped commit + push) — stage + commit
      ONLY ``rel_paths`` on the current HEAD, then push. Unrelated working-tree
      state is never swept onto dev because the commit is path-scoped.
    * ``already_committed=True`` (push an existing HEAD ledger commit) — skip the
      commit leg entirely; just fetch → guard → rebase → FF-push the commit(s)
      already on HEAD.

    The push leg (shared by both) is: ``git fetch`` → **divergence guard**
    (every commit in ``origin/<dev>..HEAD`` must touch ONLY ``rel_paths``, else
    REFUSE — never leak non-ledger work onto dev) → ``git rebase origin/<dev>``
    (conflict-free on union-merge append-only ledgers) → FF-push ``HEAD:<dev>``,
    with a SINGLE retry on the concurrent-push (non-FF) race. A genuine rebase
    conflict aborts (``git rebase --abort``) and surfaces — NEVER ``-X``/force/
    auto-resolve.

    Best-effort by construction — never raises. Structured result:

    ==========================  ===========================================================
    outcome                     dict
    ==========================  ===========================================================
    success                     ``{"ok": True,  "status": "pushed",        "pushed": True}``
    nothing to commit (scoped)  ``{"ok": True,  "status": "already_clean",  "pushed": False}``
    missing ledger file         ``{"ok": False, "error": …}``
    add / commit failed         ``{"ok": False, "error": …}``
    non-ledger commit ahead     ``{"ok": False, "committed_locally": True, "retryable": False, "error": …}``
    rebase conflict             ``{"ok": False, "committed_locally": True, "retryable": False, "error": …}``
    push failed after retry     ``{"ok": False, "committed_locally": True, "error": …}``
    ==========================  ===========================================================
    """
    def g(*args: str) -> tuple[int, str, str]:
        return _git(runner, root, *args)

    ledger_set = set(rel_paths)
    dev_ref = f"{remote}/{dev_branch}"

    # ── Commit leg (skipped when the ledger commit is already on HEAD) ─────────
    if not already_committed:
        if check_exists is not None and not check_exists.exists():
            return {"ok": False, "error": f"{check_exists.name} does not exist; nothing to push"}
        if commit_msg is None:
            return {"ok": False, "error": "commit_msg is required when already_committed=False"}

        # Act ONLY when a ledger path is dirty (idempotent re-run → already_clean).
        rc_s, out_s, _ = g("status", "--porcelain", "--", *rel_paths)
        if rc_s != 0 or not (out_s or "").strip():
            return {"ok": True, "status": "already_clean", "pushed": False}

        rc_a, _, err_a = g("add", *rel_paths)
        if rc_a != 0:
            logger.warning("%s: git add failed (%s)", _log_prefix, (err_a or "").strip())
            return {"ok": False, "error": f"git add failed: {(err_a or '').strip()}"}

        rc_c, _, err_c = g("commit", "-m", commit_msg, "--", *rel_paths)
        if rc_c != 0:
            logger.warning("%s: git commit failed (%s)", _log_prefix, (err_c or "").strip())
            return {"ok": False, "error": f"git commit failed: {(err_c or '').strip()}"}

    # ── Push leg: fetch → divergence-guard → rebase → FF-push (one retry) ──────
    #
    # BENIGN-STASH PRE-CHECK (the divergence-loop fix). `git rebase` refuses on
    # ANY dirty file, and our own cost-log pre-commit hook dirties
    # project-history/vector-costs.ndjson on essentially every commit — including
    # the ledger commit made just above. That refusal made this leg return
    # committed_locally=True / pushed=False and leave the PRIMARY checkout
    # diverged from origin/<dev>: the recurring loop that was hand-fixed with
    # `git -c rebase.autoStash=true rebase origin/dev` once per session.
    # task_branch.integrate has stashed benign artifacts since 2026-05-28 ("Bug
    # C"); the same leg here never got it. Now both share _benign_stash.
    #
    # Only KNOWN-benign artifacts are stashed. Real in-progress work still
    # blocks — but as an explicit, named dirty_blocked that says which files and
    # what to do, instead of a generic failure that surfaces later as a mystery
    # divergence.
    benign, real = classify_dirty(g)
    if real:
        logger.warning("%s: real dirty file(s) block the rebase onto %s: %s",
                       _log_prefix, dev_ref, real)
        return dirty_blocked_result(real, dev_ref)
    benign_stashed = stash_benign(g, benign, log_prefix=_log_prefix) and bool(benign)

    try:
        return _push_leg(
            g=g, remote=remote, dev_branch=dev_branch, dev_ref=dev_ref,
            ledger_set=ledger_set, _fetch=_fetch, _log_prefix=_log_prefix,
        )
    finally:
        # Restore the benign artifacts whatever happened, so the tree is left as
        # we found it (a stashed-and-forgotten ledger row is its own drift).
        if benign_stashed:
            pop_stash(g, log_prefix=_log_prefix)


def _push_leg(
    *,
    g: Callable[..., tuple[int, str, str]],
    remote: str,
    dev_branch: str,
    dev_ref: str,
    ledger_set: set[str],
    _fetch: bool,
    _log_prefix: str,
) -> dict[str, Any]:
    """fetch → divergence-guard → rebase → FF-push, with a single retry on the
    concurrent-push race. Split out so the caller can guarantee the benign-stash
    pop in a ``finally`` regardless of which branch returns."""
    last_err = ""
    for _attempt in (1, 2):
        # 1. Fetch so origin/<dev> reflects any peer push (incl. a worktree's
        #    task_branch integrate that advanced origin/dev under us).
        if _fetch:
            g("fetch", remote)

        # 2. Divergence guard — EVERY commit ahead of origin/<dev> must touch
        #    ONLY the cache-exempt ledger paths, else pushing HEAD:<dev> would
        #    leak non-ledger work onto dev.
        rc_rl, out_rl, _ = g("rev-list", f"{dev_ref}..HEAD")
        ahead = [s.strip() for s in (out_rl or "").splitlines() if s.strip()]
        non_ledger: list[str] = []
        for sha in ahead:
            _rc_dt, out_dt, _ = g("diff-tree", "--no-commit-id", "--name-only", "-r", sha)
            changed = [f.strip() for f in (out_dt or "").splitlines() if f.strip()]
            if any(f not in ledger_set for f in changed):
                non_ledger.append(sha)
        if non_ledger:
            shas = ", ".join(s[:8] for s in non_ledger)
            logger.warning(
                "%s: non-ledger commit(s) ahead of %s (%s) — ledger row committed to "
                "local dev but NOT pushed (avoiding a non-ledger leak onto dev); it "
                "ships with the next dev push", _log_prefix, dev_ref, shas)
            return {
                "ok": False,
                "retryable": False,
                "committed_locally": True,
                "error": (
                    f"HEAD has non-ledger commit(s) ahead of {dev_ref} ({shas}) — "
                    "ledger commit landed locally but was NOT pushed, to avoid leaking "
                    "non-ledger work onto dev; reconcile the divergence then re-push"
                ),
            }

        # 3. Rebase the ledger-only ahead-commit(s) onto the freshly-fetched
        #    origin/<dev>. Conflict-free by construction (merge=union + append-
        #    only). A genuine conflict ⇒ abort + surface; NEVER -X/force.
        rc_rb, _, err_rb = g("rebase", dev_ref)
        if rc_rb != 0:
            g("rebase", "--abort")
            logger.warning(
                "%s: rebase onto %s conflicted (%s); aborted — row stays on local "
                "dev, ships with the next dev push", _log_prefix, dev_ref, (err_rb or "").strip())
            return {
                "ok": False,
                "retryable": False,
                "committed_locally": True,
                "error": (
                    f"git rebase onto {dev_ref} reported a conflict "
                    f"({(err_rb or '').strip()}); rebase aborted — manual resolution "
                    "needed before the ledger can push"
                ),
            }

        # 4. FF-push HEAD → dev.
        rc_p, _, err_p = g("push", remote, f"HEAD:{dev_branch}")
        if rc_p == 0:
            return {"ok": True, "status": "pushed", "pushed": True}
        last_err = (err_p or "").strip()
        # push rejected (concurrent-push race) → loop re-fetches + re-rebases.

    logger.warning(
        "%s: FF-push to %s failed after retry (%s); commit landed on local dev — "
        "manual reconciliation / next dev push clears it", _log_prefix, dev_branch, last_err)
    return {
        "ok": False,
        "committed_locally": True,
        "error": f"FF-push to {dev_branch} failed: {last_err}",
    }
