"""Shared worktree-staleness predicate — the merged-base + is-merged core.

NOT an MCP tool (no ``@server.tool``; never added to ``register_all``). It is
the single source of truth for the "is this engineer worktree's branch merged
into the integration branch?" question, consumed by BOTH
``cleanup_worktrees.py`` (``noctus.dev.cleanup_stale_worktrees``) AND
``mole.py`` (``noctus.dev.mole``, worktree scope). It was extracted to kill the
documented N=2 DRY duplication where both tools hand-rolled the same
``merge-base --is-ancestor`` OR ``git cherry`` / ``git log`` predicate and
literally claimed to "exactly parity" each other — changing one drifted from
the other (a cleanup-only base-ref edit broke parity and had to be reverted).

What "merged" means (the orchestrator FFs an engineer branch into the
integration branch via cherry-pick → NEW sha, SAME patch):
  (a) the branch is reachable from the base by SHA ancestry (a true merge), OR
  (b) every commit on the branch is already on the base by PATCH-ID
      (``git cherry base branch`` reports ZERO ``+`` lines and the branch has
      ≥1 commit).
Unmerged work-in-progress branches are NOT merged (so worktrees holding them
are kept by both callers).

Base ref (the dev-integration model — KB § PATTERNS/branching-and-merging.md
§ 0): engineer worktrees fork from and integrate to ``dev``, NOT ``main`` (a
worktree merged-to-dev-but-not-yet-blessed-to-main was never swept under the
old ``origin/main`` keying → disk bloat). The base prefers ``origin/dev`` and
falls back to ``dev`` (mirrors the existing fallback shape).

Injectable runner: every git call goes through a ``run`` callable returning
``(returncode, stdout, stderr)`` — mirroring how ``release.py`` injects ``run``
— so the colocated unit test exercises every path with ZERO real git. The
default runner wraps ``subprocess.run`` at a given root.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable

# (rc, stdout, stderr)
GitRunner = Callable[..., tuple[int, str, str]]

# The base the engineer-integration model keys staleness off: prefer the
# integration tip, fall back to the local branch (mirrors the existing shape).
PREFERRED_BASE = "origin/dev"
FALLBACK_BASE = "dev"


def make_subprocess_runner(root: Path, *, timeout: int | None = None) -> GitRunner:
    """A ``run`` that executes ``git <args>`` at ``root`` and returns
    ``(rc, stdout, stderr)``. The default each consumer wires when it isn't
    injecting its own runner. ``timeout`` is forwarded to ``subprocess.run``
    when set (mole's git calls carry a per-call timeout)."""

    def _run(args: list[str]) -> tuple[int, str, str]:
        kwargs: dict = dict(cwd=str(root), capture_output=True, text=True)
        if timeout is not None:
            kwargs["timeout"] = timeout
        r = subprocess.run(args, **kwargs)
        return r.returncode, (r.stdout or ""), (r.stderr or "")

    return _run


def resolve_merged_base(run: GitRunner) -> str:
    """Resolve the comparison base: prefer ``origin/dev``, fall back to ``dev``.

    Mirrors the existing fallback shape (verify the preferred ref resolves;
    otherwise use the local branch name)."""
    rc, _out, _err = run(
        ["git", "rev-parse", "--verify", "--quiet", PREFERRED_BASE]
    )
    return PREFERRED_BASE if rc == 0 else FALLBACK_BASE


def is_ancestor(run: GitRunner, branch: str, base: str) -> bool:
    """``git merge-base --is-ancestor branch base`` — SHA ancestry (true merge)."""
    rc, _o, _e = run(["git", "merge-base", "--is-ancestor", branch, base])
    return rc == 0


def all_commits_cherry_picked(run: GitRunner, branch: str, base: str) -> bool:
    """Patch-id equivalence: every commit on ``branch`` is already on ``base``.

    The branch must have ≥1 commit and ZERO ``+`` lines in
    ``git cherry base branch`` (``+`` = genuinely unmerged; ``-`` = on base by
    patch-id). The orchestrator FFs via cherry-pick (new sha, same patch), so
    this catches branches whose work landed without a SHA-ancestry merge."""
    rc, out, _e = run(["git", "cherry", base, branch])
    if rc != 0:
        return False
    plus_lines = sum(1 for ln in out.splitlines() if ln.startswith("+"))
    _rc2, log_out, _e2 = run(
        ["git", "log", "--oneline", f"{base}..{branch}"]
    )
    total = len([ln for ln in log_out.splitlines() if ln.strip()])
    return total > 0 and plus_lines == 0


def is_merged(run: GitRunner, branch: str, base: str) -> bool:
    """The merged predicate both tools share: SHA-ancestry OR patch-id/cherry."""
    return is_ancestor(run, branch, base) or all_commits_cherry_picked(
        run, branch, base
    )


def has_trailer_commit_on(run: GitRunner, branch: str, base: str) -> bool:
    """True when ``base`` carries a commit stamped ``Noc-Branch: <branch>``.

    The ``commit-msg`` hook stamps every commit with its branch, and the
    trailer survives the rebase ``task_branch integrate`` performs. So it
    proves "this branch's work landed" after the branch ref is deleted AND the
    SHA the pointer recorded was rewritten. That rewrite is why pointer-SHA
    ancestry alone could never heal a rebased branch (2026-09-23)."""
    rc, out, _e = run(["git", "log", base, "--format=%(trailers:key=Noc-Branch,valueonly)"])
    if rc != 0:
        return False
    return any(line.strip() == branch for line in out.splitlines())


def pointer_branch_landed(
    run: GitRunner, branch: str, recorded_commit: str, base: str,
    fork_sha: str = "",
) -> tuple[bool, str]:
    """Did the branch a pointer names land on ``base``? → (landed, how).

    One predicate for the healer (session_end_sweep) and the safety-net keeper
    (check_stale_branch_pointers), so they can never disagree:
      1. branch ref exists → ``is_merged`` (ancestry or cherry equivalence),
         except a branch still sitting on its fork point (``fork_sha``, from
         the pointer's ``base`` "origin/dev@<sha>"): a fresh fork is trivially
         its own ancestor (the 2026-09-16 false positive documented below)
         and has landed nothing;
      2. recorded commit is an ancestor of ``base``;
      3. ``base`` carries a ``Noc-Branch: <branch>`` trailer commit (proves
         a rebased-and-deleted branch, whose recorded sha never reached dev).
    """
    rc, tip, _e = run(["git", "rev-parse", "--verify", "--quiet", branch])
    if rc == 0:
        tip = tip.strip()
        if fork_sha and tip.startswith(fork_sha.strip()):
            return (has_trailer_commit_on(run, branch, base), "branch trailer commit on base")
        return (is_merged(run, branch, base), "branch ref merged into base")
    if recorded_commit and is_ancestor(run, recorded_commit, base):
        return (True, "branch cleaned up; recorded commit is on base")
    if has_trailer_commit_on(run, branch, base):
        return (True, "branch cleaned up; its Noc-Branch trailer commit is on base")
    return (False, "unproven")


def fork_sha_from_pointer_base(base_field: str) -> str:
    """``"origin/dev@c6e9445e7"`` → ``"c6e9445e7"``; anything else → ``""``."""
    _ref, sep, sha = (base_field or "").partition("@")
    return sha.strip() if sep else ""


# ═══════════════════════════════════════════════════════════════════════════
# 🔴 2026-09-16 incident — the merged predicate is a FALSE POSITIVE for a
# freshly-created, actively-worked-in worktree.
#
# ``is_ancestor(run, branch, base)`` is ``git merge-base --is-ancestor branch
# base``, and a commit is trivially its OWN ancestor. A worktree created via
# ``git worktree add -b <branch> <path>`` off the current ``origin/dev`` tip
# starts with ZERO commits ahead — ``branch`` and ``base`` are the SAME sha.
# That makes ``is_ancestor`` return True on the very first call, before the
# engineer has committed anything, classifying the worktree as "merged" —
# and therefore "safe to remove" — while two engineers were actively working
# in it (``community-m1-backend`` / ``community-m1-frontend``, ~6 minutes
# old, 0 commits ahead, swept by ``cleanup_stale_worktrees force=True``,
# uncommitted work lost).
#
# ``is_merged`` itself is not wrong — "reachable from base by SHA ancestry"
# IS what a true merge looks like, and a 0-commit worktree genuinely has no
# unmerged patch to protect via ``git cherry``. The gap is that "merged" and
# "safe to remove right now" are two different questions; a worktree can be
# merged (in the trivial 0-commit sense) and still be somebody's live desk.
# Two independent guards close that gap — neither re-defines "merged":
#
#   1. pointer_blocks_removal — a LIVE branch-tree pointer (the global
#      git-tree × claude-tree map, ``project-history/branch-tree.ndjson``)
#      is a first-class claim: an engineer publishes ``status=on_going``
#      before touching a file (KB § PATTERNS/architect/branch-tree-tracking.md).
#      A non-terminal pointer means someone is claiming this branch RIGHT
#      NOW, independent of what git ancestry says. This is the STRONGER
#      signal and is NEVER bypassed, not even by ``force=True`` — force
#      only ever meant "skip the confirmation ritual", never "override an
#      explicit peer claim".
#   2. is_too_young — even absent a pointer (a raw ``git worktree add``, or
#      a stale/never-updated pointer), a worktree younger than
#      ``min_age_minutes`` is refused. This is what actually would have
#      caught the 2026-09-16 incident: a worktree ~6 minutes old is nowhere
#      near ``DEFAULT_MIN_AGE_MINUTES``. ``force=True`` MAY override this
#      one — an operator who explicitly asks to force-sweep a young-but-
#      merged worktree has made a deliberate call the pointer guard cannot
#      make for them.
#
# Both guards report WHY a candidate was skipped (the reason string / dict)
# rather than silently keeping it — a silent skip reads as "nothing to
# clean up here" and hides the exact signal an operator needs to decide
# whether to force past it.
# ═══════════════════════════════════════════════════════════════════════════

#: Reasoning: the incident worktrees were ~6 minutes old. A default in the
#: 30-120 minute range gives an engineer a full working session's worth of
#: "invisible to staleness heuristics" grace without meaningfully delaying
#: cleanup of worktrees that are genuinely abandoned (those are typically
#: hours-to-days old, not tens of minutes). 60 minutes is the midpoint of
#: that range and is overridable per-call via ``min_age_minutes``.
DEFAULT_MIN_AGE_MINUTES: float = 60.0


def _dir_creation_epoch(path: Path) -> float | None:
    """Best-effort worktree-directory creation time (epoch seconds).

    Prefers ``st_birthtime`` (macOS/BSD — genuine creation time) and falls
    back to ``st_ctime`` (inode change time — the closest POSIX-portable
    proxy on platforms without a birth time, e.g. most Linux filesystems).
    ``None`` when the path cannot be stat'd (already removed, permission
    error) — the caller treats an unresolvable age as "cannot prove this is
    old enough", never as "assume it's old".
    """
    try:
        st = path.stat()
    except OSError:
        return None
    birth = getattr(st, "st_birthtime", None)
    return float(birth) if birth is not None else float(st.st_ctime)


def _last_commit_epoch(run: GitRunner, branch: str) -> float | None:
    """Epoch seconds of the branch tip's commit time (``%ct``), or ``None``
    when the branch cannot be resolved (never treated as "old")."""
    rc, out, _err = run(["git", "log", "-1", "--format=%ct", branch])
    if rc != 0:
        return None
    lines = (out or "").strip().splitlines()
    if not lines:
        return None
    try:
        return float(lines[0].strip())
    except ValueError:
        return None


def worktree_age_seconds(
    run: GitRunner, wt_path: Path, branch: str, *, now: float | None = None
) -> float | None:
    """Age = ``now - max(worktree dir creation time, last commit time on
    branch)`` — the YOUNGEST of "when the directory appeared" and "when the
    branch last moved" is what actually measures how long ago someone could
    have started working here. ``None`` only when NEITHER source resolves —
    the caller must treat that as "cannot prove this is old enough" (see
    :func:`is_too_young`), never as a silent pass-through.
    """
    candidates: list[float] = []
    c1 = _dir_creation_epoch(wt_path)
    if c1 is not None:
        candidates.append(c1)
    c2 = _last_commit_epoch(run, branch)
    if c2 is not None:
        candidates.append(c2)
    if not candidates:
        return None
    ref_now = now if now is not None else time.time()
    return ref_now - max(candidates)


def is_too_young(
    run: GitRunner,
    wt_path: Path,
    branch: str,
    *,
    min_age_minutes: float = DEFAULT_MIN_AGE_MINUTES,
    now: float | None = None,
) -> tuple[bool, float | None, float]:
    """``(too_young, age_seconds, min_age_seconds)``.

    ``age_seconds`` unresolvable (``None``) is conservatively treated as
    too-young — "cannot prove old enough" refuses removal rather than
    silently assuming a safe age (no-silent-errors, CLAUDE.md §1).
    """
    min_age_seconds = min_age_minutes * 60.0
    age = worktree_age_seconds(run, wt_path, branch, now=now)
    if age is None:
        return True, None, min_age_seconds
    return age < min_age_seconds, age, min_age_seconds


def pointer_status_for_branch(branch: str, run: GitRunner) -> str | None:
    """The latest branch-tree pointer status for ``branch``, or ``None`` when
    no pointer row exists for it.

    Reuses ``branch_pointer.query``'s own latest-per-branch resolution
    (reads ``origin/dev``'s copy of ``project-history/branch-tree.ndjson``)
    rather than re-parsing the ndjson by hand here — one resolver, shared.
    ``run`` is passed straight through as ``branch_pointer.query``'s
    ``runner`` seam (same ``run(["git", ...]) -> (rc, out, err)`` shape
    :func:`make_subprocess_runner` already produces), so callers get the SAME
    repo-root binding they already use for the merge predicate — no second
    git-root resolution, no risk of asking about the wrong tree.
    """
    from tools.noctus.dev import branch_pointer as _bp

    rows = _bp.query(from_dev=True, branch=branch, runner=run)
    return rows[0].get("status") if rows else None


def pointer_blocks_removal(branch: str, run: GitRunner) -> tuple[bool, str | None]:
    """``(blocks, status)`` — ``blocks`` is True iff ``branch`` carries a live
    (non-terminal) branch-tree pointer, OR its liveness could not be
    resolved at all. This is the STRONGER guard: an explicit claim from a
    peer, never overridden by ``force=True``.

    🔴 2026-09-17 fail-open fix: this used to return ``blocks=False`` when
    the pointer query yielded nothing — an unknown branch (never
    published), an unreadable ledger, or the query itself raising. Absence
    of information is NOT permission to delete: a worktree the ledger has
    never heard of is exactly as unprovably-safe as one carrying a live
    ``on_going`` claim, so unknown liveness is now treated as BLOCKING, the
    same conservative-refusal shape :func:`is_too_young` already uses for an
    unresolvable age (no-silent-errors, CLAUDE.md §1). To unblock a branch
    with no pointer, publish one with a genuinely terminal status
    (``noctus.dev.branch_pointer action=append/update status=shipped|...``)
    — never a tool-side guess.
    """
    from tools.noctus.dev.branch_pointer import TERMINAL_STATUSES

    try:
        status = pointer_status_for_branch(branch, run)
    except Exception:  # noqa: BLE001 — a query failure is UNKNOWN liveness,
        # never permission to proceed as if it were terminal.
        return True, None
    if status is None:
        return True, None
    return status not in TERMINAL_STATUSES, status


def _rev_parse(run: GitRunner, ref: str) -> str | None:
    """Resolve ``ref`` to its full SHA, or ``None`` when it cannot be
    resolved (unknown ref, git failure) — never guessed."""
    rc, out, _err = run(["git", "rev-parse", ref])
    if rc != 0:
        return None
    line = (out or "").strip()
    return line or None


def merged_into_base_confirms_dead(run: GitRunner, branch: str, base: str) -> bool:
    """Second, POSITIVE liveness signal — consulted ONLY when the ledger has
    NO pointer for ``branch`` at all (``pointer_status_for_branch`` returned
    ``None``: never published, unreadable ledger, or the query itself
    failed — a LIVE non-terminal pointer is a peer claim and is NEVER
    overridden by this). 537 rows / 206 branches accumulated in
    ``project-history/branch-tree.ndjson`` since 2026-09-13, yet a branch
    that was simply never published a pointer for is otherwise IMMORTAL
    under :func:`pointer_blocks_removal`'s fail-closed "unknown ⇒ blocking"
    rule — this is the entire 6.4 GB worktree-debt incident (2026-09-20):
    36 of 37 stale worktrees on disk carried no pointer row whatsoever,
    every one of them verifiably merged into ``origin/dev`` by hand
    (``git merge-base --is-ancestor <branch> dev``).

    A branch that is a strict SHA ancestor of ``base`` **and has diverged
    from it** (``branch``'s tip SHA differs from ``base``'s) is, by
    definition, already fully represented in ``base``'s history — there is
    no unique commit content a removal could lose. This is deliberately
    narrower than :func:`is_merged` (which also accepts patch-id/cherry-pick
    equivalence, a weaker automated signal this fallback does not trust on
    its own, absent a ledger corroboration).

    🔴 The divergence check (``branch_sha != base_sha``) is what stops this
    from reintroducing the 2026-09-16 false positive documented above this
    function's siblings: a worktree freshly forked via
    ``git worktree add -b <branch>`` off the current base tip starts with
    ZERO commits ahead, so ``branch`` and ``base`` are the literal SAME sha
    — trivially "ancestors" of each other via ``merge-base --is-ancestor``
    — and that carries ZERO evidence of deadness (it could be someone's
    brand-new live desk mid-checkout). A branch that has genuinely diverged
    and is NOW reachable from ``base`` by true SHA ancestry, by contrast, IS
    positive evidence its content already lives in the integration branch —
    exactly the shape of the 36 ledger-less worktrees this closes (all
    verified via ``git merge-base --is-ancestor`` by hand).

    Known, deliberate limitation: a branch whose landing IS the base's
    current tip (e.g. `task_branch action=integrate` fast-forward-PUSHES an
    engineer branch's own commits onto dev, so immediately after that FF,
    branch-tip == base-tip even though real work landed) will NOT be
    confirmed by this check in that narrow window — it stays
    ``pointer_blocked`` until either a pointer is published for it or
    ``base`` advances again (near-certain in an active repo; not a
    correctness bug, just a deferred sweep). Erring toward a missed sweep
    over a false "confirmed dead" is the correct trade for a signal that
    NEVER force-bypasses the pointer guard's caller.

    Returns ``False`` (never "confirms dead") when either SHA cannot be
    resolved, when the two are identical (no divergence), or when ancestry
    itself cannot be determined — an indeterminate merge status is
    refusal, not permission (no-silent-errors, CLAUDE.md §1).
    """
    branch_sha = _rev_parse(run, branch)
    base_sha = _rev_parse(run, base)
    if branch_sha is None or base_sha is None:
        return False
    if branch_sha == base_sha:
        return False
    return is_ancestor(run, branch, base)


def pointer_block_reason(status: str | None) -> str:
    """Human-readable reason string for a pointer-blocked removal — shared by
    both consumers (``cleanup_worktrees.py``, ``mole.py``) so the wording
    never drifts between the two call sites (the exact DRY gap that let one
    caller's base-ref edit silently diverge from the other, pre-extraction)."""
    if status is None:
        return (
            "no branch-tree pointer could be resolved for this branch (never "
            "published, ledger unreadable, or the query failed) — liveness is "
            "UNKNOWN and is treated as blocking, never as permission to delete; "
            "force=True does NOT override this guard"
        )
    return (
        f"branch-tree pointer status={status!r} is not terminal — a live "
        "peer claim on this branch; force=True does NOT override this guard"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 🔴 2026-09-17 incident — the LEDGER said "shipped"; the FILESYSTEM said
# "somebody is still here". session_end_sweep's own auto-heal
# (`_autoheal_branch_pointers`) flipped a peer session's live
# ``ef-w8-models-worker`` pointer from ``on_going`` straight to the terminal
# ``shipped`` the moment its branch became integrated into ``origin/dev`` —
# without ever checking whether the ``.claude/worktrees/ef-w8-models-worker``
# directory (and the session using it) still existed. `pointer_blocks_removal`
# only ever reads the LEDGER; a terminal status there reads as "nobody's
# claiming this" even while the worktree is somebody's live desk. Two
# independent fixes close this, neither one alone sufficient:
#
#   1. A distinct NON-terminal status — `integrated-worktree-live` — for
#      "the branch landed, but a worktree is still checked out for it".
#      `session_end_sweep` writes this instead of `shipped` whenever the
#      worktree directory still exists (see that module). It is NOT added to
#      `branch_pointer.TERMINAL_STATUSES`, so `pointer_blocks_removal` keeps
#      refusing removal for it exactly like `on_going` — never bypassed by
#      `force=True` (this file's Leg-1 fix).
#   2. A filesystem-mtime liveness probe (`is_recently_active`, below),
#      INDEPENDENT of the ledger entirely — no pointer, no git-log call, a
#      raw directory walk. Even if a pointer is missing, wrong, or stale, a
#      worktree somebody touched a file in moments ago is not safe to
#      remove. This is Leg-2: defense-in-depth that does not depend on any
#      agent having correctly published or maintained a pointer at all.
# ═══════════════════════════════════════════════════════════════════════════

#: Directory names pruned from the mtime walk — regenerable / vendored /
#: cache content whose timestamps say nothing about whether a HUMAN (or
#: agent) touched this worktree recently.
IGNORED_DIR_NAMES: frozenset[str] = frozenset({
    ".git", "node_modules", "__pycache__", "dist", ".pytest_cache", "venv",
})

#: Reasoning: paired with DEFAULT_MIN_AGE_MINUTES (60) — the two guards
#: share a "give a working session its full grace period" default so an
#: operator tuning one has an obvious analog for the other. Overridable
#: per-call via ``window_minutes``.
DEFAULT_RECENT_MTIME_MINUTES: float = 60.0


def _latest_file_mtime(wt_path: Path) -> float | None:
    """Most recent mtime (epoch seconds) among files under ``wt_path``, with
    :data:`IGNORED_DIR_NAMES` pruned from the walk. Pure filesystem evidence
    — no git call at all, so it is independent of anything the branch-tree
    ledger claims (a stale/never-written/wrong pointer cannot hide a file
    that was touched a minute ago). ``None`` when the path is not a
    directory (already removed) or contains no readable files — the caller
    treats that as "cannot prove this is stale", never as a silent green
    light (mirrors :func:`worktree_age_seconds`'s ``None`` contract).
    """
    if not wt_path.is_dir():
        return None
    latest: float | None = None
    try:
        for dirpath, dirnames, filenames in os.walk(wt_path):
            dirnames[:] = [d for d in dirnames if d not in IGNORED_DIR_NAMES]
            for fname in filenames:
                try:
                    mtime = (Path(dirpath) / fname).stat().st_mtime
                except OSError:
                    continue
                if latest is None or mtime > latest:
                    latest = mtime
    except OSError:
        # Partial walk failure (permission error mid-tree, etc.) — return
        # whatever we found so far rather than silently discarding evidence.
        return latest
    return latest


def is_recently_active(
    wt_path: Path,
    *,
    window_minutes: float = DEFAULT_RECENT_MTIME_MINUTES,
    now: float | None = None,
) -> tuple[bool, float | None, float]:
    """``(recently_active, age_seconds, window_seconds)``.

    ``recently_active`` is True when the most recent file mtime under
    ``wt_path`` (noise dirs pruned) is younger than ``window_minutes``.
    ``age_seconds`` unresolvable (``None`` — path already gone, or genuinely
    empty of readable files) is conservatively treated as recently-active:
    "cannot prove this is stale" refuses removal rather than assuming a safe
    age (no-silent-errors, CLAUDE.md §1; mirrors :func:`is_too_young`'s
    identical contract for the git-side age signal).

    This guard is intentionally NEVER bypassed by ``force=True`` — evidence
    of current activity outranks an operator's blanket flag (unlike
    :func:`is_too_young`'s age guard, which force MAY override).
    """
    window_seconds = window_minutes * 60.0
    latest = _latest_file_mtime(wt_path)
    if latest is None:
        return True, None, window_seconds
    ref_now = now if now is not None else time.time()
    age = ref_now - latest
    return age < window_seconds, age, window_seconds


__all__ = [
    "GitRunner",
    "PREFERRED_BASE",
    "FALLBACK_BASE",
    "DEFAULT_MIN_AGE_MINUTES",
    "DEFAULT_RECENT_MTIME_MINUTES",
    "IGNORED_DIR_NAMES",
    "make_subprocess_runner",
    "resolve_merged_base",
    "is_ancestor",
    "all_commits_cherry_picked",
    "is_merged",
    "worktree_age_seconds",
    "is_too_young",
    "is_recently_active",
    "pointer_status_for_branch",
    "pointer_blocks_removal",
    "pointer_block_reason",
    "merged_into_base_confirms_dead",
]
