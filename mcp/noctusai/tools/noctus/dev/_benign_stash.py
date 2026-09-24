"""Shared benign-refresh-artifact stash helper — the N=2 DRY lift of the
``classify dirty files into benign-vs-real → stash the benign ones → rebase →
pop`` idiom.

WHY THIS EXISTS. ``git rebase`` refuses outright when the working tree is dirty
("error: cannot rebase: You have unstaged changes") — it does not care WHICH
files are dirty. Our own pre-commit / cache-refresh hooks dirty a small, known
set of reconstructable files (``project-history/*.ndjson`` ledgers, the
agent-context mirrors, ``.claude/cache/*``) as a side effect of essentially every
commit. So a rebase that would be a clean fast-forward gets refused by artifacts
the tooling itself just wrote.

TWO CALL SITES HAD THE SAME REBASE LEG; ONLY ONE HAD THE FIX.

* ``task_branch.integrate`` (worktree side) — fixed 2026-05-28 after the failure
  was observed N=5+ times ("Bug C"): it classified dirty files and auto-stashed
  the benign ones before rebasing.
* ``_ledger_push.commit_and_ff_push_ledger`` (PRIMARY-checkout side) — same
  ``git rebase <dev_ref>`` leg, no stash. The cost-log pre-commit hook dirties
  ``project-history/vector-costs.ndjson`` on every commit, so this rebase was
  refused essentially every time it mattered. The helper then returned
  ``committed_locally=True, pushed=False`` and left the primary checkout DIVERGED
  from ``origin/dev`` — the recurring "primary/origin divergence" loop with 4+
  ledger entries against it, resolved by hand each session with
  ``git -c rebase.autoStash=true rebase origin/dev``.

The fix was never lifted, so the second site kept paying for it. This module is
that lift: one mechanism, both callers.

WHAT STAYS LOUD. Only the known-benign patterns are stashed. A genuinely dirty
working tree (real in-progress work) still blocks the rebase — but the callers
now surface it as an explicit ``dirty_blocked`` naming the files, instead of a
generic failure that reads as a mystery divergence later.

THE LIST ITSELF WAS THE THIRD BUG (fixed 2026-09-01). ``BENIGN_REFRESH_PATTERNS``
started life as four hand-copied ``project-history/*.ndjson`` filenames plus two
hand-copied KB paths. The pre-commit hook's own KB-counts regenerator
(``kb_sync.update_kb_counts`` / ``--update-kb-counts``, step 2) writes THREE
marker-block targets — ``KNOWLEDGE-BASE/AGENT-CONTEXT.md``,
``KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md``, AND
``KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md`` — and only two of the three ever made
it into the hand-copied list. ``branch_pointer.py`` wrote its ledger AND a
byte-identical mirror (``branch-tree.mirror.ndjson``) atomically, every time; only
the ledger name made it in. (Both ledgers left the dev checkout on 2026-09-24 —
they live on origin/ledgers now; the glob still covers a stale-code peer's
leftover writes until S4 of the ledgers-off-dev roadmap.) Both omissions are the exact anti-pattern CLAUDE.md
§1 names for hand-maintained coverage lists: correct the day they're written,
stale the day a sibling artifact is added. See the derivation helpers below —
the KB-counts half is now read straight from ``kb_sync``'s own manifest instead
of re-typed, and the ledger half is a directory-wide glob instead of one literal
per filename, so a FOURTH regenerated ``project-history/*.ndjson`` sibling (or a
FOURTH kb-counts region target) is covered on arrival, not on the next incident.

KB § PATTERNS/common/self-branching-mode.md · KB § PATTERNS/architect/branch-tree-tracking.md
"""
from __future__ import annotations

import fnmatch
import hashlib
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# A ``run_git(*args) -> (rc, stdout, stderr)`` closure. Each caller supplies one
# that already encodes HOW it reaches its repo (``-C <root>`` vs ``cwd=``), so
# this module never has to know.
RunGit = Callable[..., tuple[int, str, str]]


def _kb_counts_regenerated_rel_paths() -> tuple[str, ...]:
    """Repo-relative paths ``kb_sync.update_kb_counts()`` regenerates — and the
    pre-commit hook's step 2 auto-``git add``s when they were clean beforehand
    (see ``scripts/hooks/pre-commit`` § "auto-staged (machine count-refresh of a
    clean file)"). Read straight from ``kb_sync._regions()`` — the SAME manifest
    the regenerator itself walks to decide what to rewrite — instead of a
    hand-copied filename list.

    THE BUG THIS REPLACES: the hand-copied list carried
    ``KNOWLEDGE-BASE/AGENT-CONTEXT.md`` and ``KNOWLEDGE-BASE/CONTEXT/
    06-AGENTS.md`` (two of ``_regions()``'s three DISTINCT target files) but not
    ``KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md`` (the third — it carries TWO
    regions, "inventory" and "database"). ``02-LANDSCAPE.md`` gets rewritten by
    step 2 on essentially every commit that changes the product/schema/tool
    counts, was never classified benign, and refused the rebase every time —
    the identical shape as the ``vector-costs.ndjson`` bug this module already
    fixed once, one file over.

    ``kb_sync`` has no reverse dependency on this module (or on ``_ledger_push``
    / ``branch_pointer`` / ``task_branch``), so importing it here — even at
    module-load time — cannot form an import cycle. A failure importing it is
    logged and degrades to an EMPTY tuple: conservative, because the caller
    then blocks the rebase loudly on what turns out to be a benign file rather
    than silently believing the working tree needs no stashing (see
    "no silent errors", CLAUDE.md §1).
    """
    try:
        from pathlib import Path as _Path

        from settings import REPO_ROOT as _REPO_ROOT
        from tools.kb_sync import _regions as _kb_regions
    except Exception:
        logger.warning(
            "benign_stash: could not import tools.kb_sync to derive the "
            "KB-counts regenerated-path set; the KB-counts docs it would have "
            "covered will now block a rebase they dirty (conservative — see "
            "the derivation docstring)", exc_info=True)
        return ()
    repo = _Path(_REPO_ROOT)
    rels: set[str] = set()
    for _region, (path, _renderer) in _kb_regions(repo).items():
        try:
            rels.add(str(path.relative_to(repo)))
        except ValueError:
            continue  # a region target outside the repo root — not our concern
    return tuple(sorted(rels))


# Known-benign refresh artifacts — files our own pre-commit / cache-refresh hooks
# write as side effects. They appear in ``git status --porcelain``, block a
# rebase, and carry no task work.
#
# ``project-history/*.ndjson`` IS the invariant, not a coincidence of four
# filenames — .gitattributes already carries the SAME glob
# (``project-history/*.ndjson merge=union``) for the whole directory, because
# every ledger there is an append-only structured log written by an MCP tool,
# never hand-edited prose. The glob covers every ledger the directory holds
# TODAY (vector-costs / auto-improvement / worktree-salvage / branch-tree /
# branch-tree's own mirror) and every ledger a FUTURE writer drops in — no
# per-filename entry required. The five literal entries below are kept
# alongside it ONLY because ``task_branch``'s test suite
# (``test_task_branch.py::test_benign_patterns_contains_worktree_salvage`` and
# its siblings) pins specific SUBSTRINGS inside ``_BENIGN_REFRESH_PATTERNS``
# itself — a glob string doesn't contain the literal filename as a substring,
# so the pin needs the literal alongside the glob. Functionally the glob alone
# already covers all five (`is_benign` matches via ``fnmatch``, not substring).
#
# ``project-history/PROJECT-HISTORY.md`` (this pre-commit hook's step 3b
# target, ``history.render_project_history``) is a literal entry for a
# DIFFERENT reason: it has no importable single-source constant the way the
# KB-counts docs and the ledgers do (its output path is a local default
# inside ``render_project_history``, not a module-level name), so — unlike
# the two derived groups above — it genuinely cannot be derived without
# reaching into that function's internals. Discovered in-flight while
# investigating this same recurrence class (regenerated + auto-staged by the
# SAME hook, same failure shape); documented here rather than left for a
# fifth incident to find it.
BENIGN_REFRESH_PATTERNS: tuple[str, ...] = (
    "project-history/*.ndjson",
    "project-history/vector-costs.ndjson",
    "project-history/auto-improvement.ndjson",
    "project-history/worktree-salvage.ndjson",
    "project-history/branch-tree.ndjson",
    "project-history/branch-tree.mirror.ndjson",
    "project-history/PROJECT-HISTORY.md",
    ".claude/cache/*",
) + _kb_counts_regenerated_rel_paths()

STASH_MESSAGE = "task_branch auto-stash: benign refresh artifacts"


def stash_message(benign: list[str], *, label_hint: str | None = None) -> str:
    """Build the message for THIS stash entry: the fixed prefix (so
    ``git stash list | grep <STASH_MESSAGE>`` keeps working, and so the
    error-path log line above stays correct) plus a short content
    fingerprint of the exact benign-path set plus, when given, a caller
    hint (the worktree path).

    WHY. With every entry carrying the byte-identical generic message,
    ``git stash list`` gives a human (or the tech-lead, triaging the shared
    stack) NO way to tell 10+ entries apart at a glance — every one of them
    reads as "task_branch auto-stash: benign refresh artifacts" regardless
    of which worktree or which files it holds. Restore/drop were NEVER
    positional (see :func:`stash_benign` / :func:`pop_stash` — always by
    SHA), so this is purely an operator-legibility fix, not a correctness
    one: the message string plays no role in which entry gets applied or
    dropped.
    """
    digest = hashlib.sha1(
        "\n".join(sorted(benign)).encode("utf-8")
    ).hexdigest()[:8]
    hint = f" [{label_hint}]" if label_hint else ""
    return f"{STASH_MESSAGE}{hint} #{digest}"


def is_benign(path: str, patterns: tuple[str, ...] = BENIGN_REFRESH_PATTERNS) -> bool:
    """True iff ``path`` matches one of the known-benign refresh patterns."""
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


# ``project-history/*.ndjson`` — same glob as the first entry of
# ``BENIGN_REFRESH_PATTERNS`` above, named separately because it drives a
# DIFFERENT decision (commit vs stash) than "is this benign at all".
_LEDGER_NDJSON_GLOB = "project-history/*.ndjson"


def is_ledger_ndjson(path: str) -> bool:
    """True iff ``path`` is one of the append-only ``project-history/*.ndjson``
    ledgers.

    🔴 WHY THESE ARE NEVER STASHED (2026-09-16 — a real cross-session
    near-loss, recovered by hand in ``dev`` at ``3789fefc``). A ledger row is
    ``is_benign()`` too (it matches the SAME glob in
    ``BENIGN_REFRESH_PATTERNS``), so the naive read is "benign ⇒ safe to
    stash-and-pop, same as a cache file". It is not: ``.git/refs/stash`` is
    ONE stack shared by the primary checkout and every worktree of this repo
    (the exact mechanism ``stash_benign``'s SHA-not-bool docstring already
    documents for a different symptom). Sweeping 25 unpushed rows from
    ``project-history/*.ndjson`` (branch-tree, worktree-salvage,
    auto-improvement, …) into that shared stack — even with a perfectly
    correct SHA-addressed restore — is loss-SHAPED: the entry can be popped
    by the wrong session, dropped by a cleanup pass that doesn't know it
    holds live data, or simply never restored if the caller errors before
    the ``finally``. A cache file surviving that is a cheap rebuild. A
    ledger row surviving that is the only copy of an append-only fact.

    The fix does not need the stash at all: every ``project-history/*.ndjson``
    ledger carries ``merge=union`` in ``.gitattributes`` and is append-only,
    so a ``chore(ledger)`` commit of just these paths rebases conflict-free
    onto anything — see :func:`commit_ledger_rows`. ``.claude/cache/*`` and
    the regenerated KB-count docs carry no such durability requirement and
    stay in the stash-and-pop path.
    """
    return fnmatch.fnmatch(path, _LEDGER_NDJSON_GLOB)


def partition_ledger(paths: list[str]) -> tuple[list[str], list[str]]:
    """Split an already-``is_benign`` path list into ``(ledger, stashable)``.

    ``ledger`` — ``project-history/*.ndjson`` rows (see :func:`is_ledger_ndjson`)
    — the caller must COMMIT these, never stash them.
    ``stashable`` — every other known-benign artifact (``.claude/cache/*``, the
    regenerated KB-count docs, ``PROJECT-HISTORY.md``) — genuinely derived,
    still safe to stash-and-pop.
    """
    ledger = [p for p in paths if is_ledger_ndjson(p)]
    stashable = [p for p in paths if not is_ledger_ndjson(p)]
    return ledger, stashable


LEDGER_COMMIT_MESSAGE = "chore(ledger): ship the append-only ledger rows written this run"


def commit_ledger_rows(
    run_git: RunGit,
    ledger_paths: list[str],
    *,
    commit_msg: str = LEDGER_COMMIT_MESSAGE,
    log_prefix: str = "benign_stash",
) -> str | None:
    """Commit — never stash — the dirty ``project-history/*.ndjson`` rows so the
    working tree is clean enough to rebase, without the shared-stash loss class
    documented on :func:`is_ledger_ndjson`. Path-scoped (``git add --
    <ledger_paths>`` then ``git commit -- <ledger_paths>``), so nothing else
    rides into this commit. The commit lands on the CURRENT branch, so it
    replays through the caller's subsequent rebase like any other commit —
    append-only + ``merge=union`` makes that conflict-free by construction.

    Returns a truthy value on success — the new HEAD sha when resolvable, else
    the sentinel string ``"committed"`` (the commit itself succeeded; only the
    SHA lookup came back empty, same "not addressable" edge case
    :func:`stash_benign` already tolerates for its own SHA resolution).
    Returns ``None`` ONLY when there was nothing to commit or `git add` /
    `git commit` itself failed (best-effort — a failure here is logged and
    the paths stay dirty, so the caller can fall back to stashing them rather
    than silently losing the distinction between "committed" and "failed").
    """
    if not ledger_paths:
        return None
    logger.debug("%s: committing %d ledger row(s) instead of stashing: %s",
                 log_prefix, len(ledger_paths), ledger_paths)
    rc_a, _out_a, err_a = run_git("add", "--", *ledger_paths)
    if rc_a != 0:
        logger.warning(
            "%s: git add of ledger path(s) failed (%s); leaving them dirty "
            "rather than stashing — they will surface as blocking dirt, "
            "never silently lost", log_prefix, (err_a or "").strip())
        return None
    rc_c, _out_c, err_c = run_git("commit", "-m", commit_msg, "--", *ledger_paths)
    if rc_c != 0:
        logger.warning("%s: git commit of ledger path(s) failed (%s)",
                       log_prefix, (err_c or "").strip())
        return None
    rc_r, out_r, _err_r = run_git("rev-parse", "HEAD")
    sha = (out_r or "").strip().splitlines()[0].strip() if rc_r == 0 and (out_r or "").strip() else None
    logger.debug("%s: committed %d ledger row(s) as %s", log_prefix, len(ledger_paths), sha or "?")
    return sha or "committed"


def strip_status_code(raw: str) -> str:
    """Strip the porcelain status columns from one ``git status --porcelain``
    line, returning the path.

    Real git always emits EXACTLY two status columns followed by a space
    (``" M path"``, ``"M  path"``, ``"MM path"``), so the fast path is a fixed
    3-char offset. But a fixed offset applied to a line that does NOT have that
    shape silently TRUNCATES the path — ``"M path"`` becomes ``"ath"``-style
    garbage that then misclassifies as real work. A path we cannot parse must
    never be silently corrupted into a different path, so anything not matching
    the canonical shape falls back to splitting on the first whitespace run.

    The rename form ``XY old -> new`` keeps the destination path.
    """
    body = raw[3:] if len(raw) > 3 and raw[2] == " " else (
        raw.lstrip().split(" ", 1)[-1] if " " in raw.lstrip() else raw
    )
    return body.strip().split(" -> ")[-1].strip()


def classify_porcelain(
    out: str, patterns: tuple[str, ...] = BENIGN_REFRESH_PATTERNS
) -> tuple[list[str], list[str]]:
    """Split ``git status --porcelain`` output into ``(benign, real)`` paths.

    An UNTRACKED path (``??``) that is not a known-benign artifact is neither:
    ``git rebase`` never refuses because of untracked files, so it cannot be
    what blocks the rebase these callers are clearing the way for — and it is
    usually someone's unrelated, uncommitted file that is not ours to move.
    Counting it as ``real`` stranded every ledger push behind one stray
    untracked ``.docx`` for a whole session (2026-09-21/22: 22 commits queued
    on the primary). The one case where it does matter — an incoming commit
    ADDS that same path — makes git abort the rebase with "untracked working
    tree files would be overwritten", which the push leg already reports as
    a failed rebase; nothing is lost or clobbered.
    """
    benign: list[str] = []
    real: list[str] = []
    for raw in out.splitlines():
        if not raw.strip():
            continue
        path = strip_status_code(raw)
        if is_benign(path, patterns):
            benign.append(path)
        elif not raw.startswith("??"):
            real.append(path)
    return benign, real


def classify_dirty(run_git: RunGit) -> tuple[list[str], list[str]]:
    """``git status --porcelain`` → ``(benign, real)``.

    A git-status failure returns ``([], ["<git-status-failed>"])`` so the caller
    treats it conservatively as real dirt rather than assuming a clean tree.
    """
    rc, out, _err = run_git("status", "--porcelain")
    if rc != 0:
        return [], ["<git-status-failed>"]
    return classify_porcelain(out or "")


def stash_benign(
    run_git: RunGit,
    benign: list[str],
    *,
    log_prefix: str = "benign_stash",
    label_hint: str | None = None,
) -> str | None:
    """Stash the known-benign artifacts so the tree is clean enough to rebase.

    Returns the created stash's COMMIT SHA — the handle :func:`pop_stash` needs
    to restore *this* entry rather than whatever currently sits on top of the
    stack. ``None`` when there was nothing to stash, when the stash failed (the
    caller then proceeds unstashed and lets the rebase surface it, rather than
    pretending the tree is clean), or when the entry could not be addressed.

    ``label_hint`` (typically the caller's worktree path) is folded into the
    stash message alongside a content fingerprint (:func:`stash_message`) so
    a human triaging a shared stack carrying 10+ of these entries can tell
    them apart in ``git stash list`` — restore/drop remain SHA-addressed
    either way (the message plays no role in correctness).

    🔴 WHY A SHA AND NOT A BOOL (2026-09-09 — a real cross-session data-loss
    incident). ``.git/refs/stash`` is ONE stack shared by the primary checkout
    and every worktree of the repository. This helper used to return a bool and
    :func:`pop_stash` used to run a bare ``git stash pop``, i.e. ``stash@{0}``.
    ``stash@{0}`` is not a stable handle: it means "whatever was pushed most
    recently, by anyone". Two sessions whose ledger pushes interleave —
    A pushes, B pushes, A pops — leave A holding B's rows and B holding A's,
    each applied into a tree that never authored them and is not on their
    branch. That is exactly what happened: three `project-history/*.ndjson`
    files carrying session 034951b2's rows materialised as uncommitted
    modifications inside a THIRD session's worktree, and were only noticed
    because they happened to block a rebase. The obvious unblocking move
    (`git checkout -- project-history/`) would have destroyed them silently.

    The path allowlist was never the weak part — those paths are genuinely
    benign. The *stack* was shared, and nothing here modelled that.
    """
    if not benign:
        return None
    logger.debug("%s: auto-stashing %d benign artifact(s): %s",
                 log_prefix, len(benign), benign)
    message = stash_message(benign, label_hint=label_hint)
    rc, _out, err = run_git(
        "stash", "push", "--include-untracked", "--message", message, "--", *benign
    )
    if rc != 0:
        logger.warning("%s: auto-stash failed (%s); proceeding without stash — "
                       "the rebase may be refused", log_prefix, (err or "").strip())
        return None

    rc, out, err = run_git("rev-parse", "stash@{0}")
    sha = (out or "").strip().splitlines()[0].strip() if (out or "").strip() else ""
    if rc != 0 or not sha:
        # We DID stash — the rows are safe in the stack, just not addressable by
        # us. Say so at ERROR with the message to grep for; never fall back to a
        # positional ref, which is the bug this whole contract exists to prevent.
        logger.error(
            "%s: stashed the benign artifacts but could not resolve their SHA "
            "(%s). They are NOT lost: find them with `git stash list | grep %r` "
            "and restore with `git stash apply <sha>`. Refusing to pop "
            "positionally — stash@{0} may belong to another worktree.",
            log_prefix, (err or "").strip(), STASH_MESSAGE,
        )
        return None
    return sha


def pop_stash(
    run_git: RunGit,
    ref: str | None = None,
    *,
    log_prefix: str = "benign_stash",
) -> None:
    """Restore the stash entry :func:`stash_benign` created, by SHA.

    ``apply`` + a targeted ``drop`` rather than ``pop``: ``pop`` is positional,
    and the stack is shared with every other worktree (see :func:`stash_benign`).
    A failed apply leaves the entry in place — losing the restore is recoverable,
    dropping someone else's rows is not.

    Best-effort: a failure is logged, never raised — the surrounding operation
    has already completed one way or the other.
    """
    if not ref:
        # No handle ⇒ nothing this call can safely restore. A bare pop here is
        # precisely the cross-worktree swap; refuse instead.
        logger.debug("%s: no stash ref to restore", log_prefix)
        return

    rc, _out, err = run_git("stash", "apply", ref)
    if rc != 0:
        logger.warning("%s: stash apply %s failed (%s); the benign artifacts "
                       "remain stashed — restore with `git stash apply %s`",
                       log_prefix, ref, (err or "").strip(), ref)
        return

    # Drop needs the POSITIONAL name, which is why we resolve it fresh here
    # instead of remembering one: a peer push may have shifted our entry down
    # the stack between the stash and this call.
    rc, out, _err = run_git("stash", "list", "--format=%H %gd")
    if rc != 0:
        logger.warning("%s: applied %s but could not list the stash to drop it; "
                       "a stale entry remains (harmless, but `git stash drop` it)",
                       log_prefix, ref)
        return
    positional = next(
        (
            line.split(None, 1)[1].strip()
            for line in (out or "").splitlines()
            if line.strip() and line.split(None, 1)[0].strip() == ref and len(line.split(None, 1)) == 2
        ),
        None,
    )
    if positional is None:
        logger.warning("%s: applied %s but it is no longer in the stash list; "
                       "not dropping anything", log_prefix, ref)
        return
    rc, _out, err = run_git("stash", "drop", positional)
    if rc != 0:
        logger.warning("%s: applied %s but could not drop %s (%s); a stale "
                       "entry remains", log_prefix, ref, positional, (err or "").strip())


def dirty_blocked_result(real: list[str], dev_ref: str) -> dict[str, Any]:
    """The explicit, named outcome for 'the tree carries REAL dirt, so the rebase
    cannot run'. Replaces a generic failure that later reads as an unexplained
    primary/origin divergence."""
    files = ", ".join(real[:10]) + (" …" if len(real) > 10 else "")
    return {
        "ok": False,
        "status": "dirty_blocked",
        "retryable": False,
        "committed_locally": True,
        "dirty_files": real,
        "error": (
            f"working tree carries uncommitted non-benign changes ({files}), so the "
            f"rebase onto {dev_ref} cannot run — the ledger row is committed locally "
            f"but NOT pushed. Commit or stash that work, then re-run; local will stay "
            f"diverged from {dev_ref} until you do."
        ),
    }


__all__ = [
    "BENIGN_REFRESH_PATTERNS", "STASH_MESSAGE", "LEDGER_COMMIT_MESSAGE", "RunGit",
    "_kb_counts_regenerated_rel_paths",
    "is_benign", "is_ledger_ndjson", "partition_ledger",
    "strip_status_code", "classify_porcelain", "classify_dirty",
    "stash_message", "stash_benign", "pop_stash", "commit_ledger_rows",
    "dirty_blocked_result",
]
