"""Fast-forward the PRIMARY checkout to ``origin/dev`` — ff-only, never forced.

**The recurrence this closes (3x on 2026-10-09).** Everything that runs the
toolkit "from the primary" — `task_branch`'s fresh-subprocess fallback, the
SessionStart worktree sweep, the merged-tip gates — executes the primary
checkout's ``mcp/noctusai/cli.py``. Nothing moved the primary forward, so code
that had already landed on ``dev`` stayed invisible until someone fast-forwarded
it by hand (the scoped mcp gate and the .env scrub both shipped and then did
not run, because the primary still held the old code).

**When it refuses (and says so — never silently):** the primary is on any
branch other than ``dev``, a detached HEAD, has STAGED changes or unstaged
modifications to a file the FF changes (unstaged edits to files it does not
touch are carried through and reported as ``kept_dirty``), has local commits ``origin/dev`` lacks (diverged), or the FF would
overwrite an untracked file that DIFFERS from the incoming blob (untracked files byte-identical to
the incoming blob are removed first and reported in ``removed_identical_untracked`` — a tool wrote
the same bytes the commit now carries; nothing is lost). Untracked files are otherwise fine: an ff-only
merge leaves them alone. Every refusal is a ``skipped_*`` status with the
reason; the caller surfaces it.

**Why no guard is involved.** ``primary_write_guard`` is a PreToolUse hook over
Claude's own Edit/Write/Bash calls, and ``check_primary_checkout_commit`` fires
on commits. This runs inside the toolkit / a harness hook and creates no commit
— an ff-only merge only moves ``dev`` to a commit that already passed every
gate on its way to ``origin/dev``, exactly what a human ``git pull --ff-only``
does. The guards stay sharp: no carve-out was needed.

Stdlib-only, importable by file path (the SessionStart hook loads it without
importing the toolkit package).
"""
from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable
from typing import Any

GitFn = Callable[..., tuple[int, str, str]]

# An index.lock no git process has touched for this long is a crash leftover (2026-11-13: one from
# the previous evening blocked every git command in the primary for a day). Our own ff-only merge
# times out at 600s, so 900s can never be a live operation of this tool.
STALE_INDEX_LOCK_S = 900
# Where a landed-commit drop parks the old HEAD (recoverable: `git log refs/noc/primary-landed/<sha>`).
LANDED_BACKUP_PREFIX = "refs/noc/primary-landed/"


def _clear_stale_index_lock(root: str, g: GitFn, now: float | None = None) -> dict[str, Any]:
    """Remove ``<git-dir>/index.lock`` when it is older than STALE_INDEX_LOCK_S.

    Returns ``{}`` (no lock), ``{"removed_stale_index_lock": age_s}`` or ``{"locked": age_s}`` (a young
    lock — someone may be mid-operation; the caller refuses rather than racing it)."""
    rc, git_dir, _e = g("rev-parse", "--git-dir")
    if rc != 0:
        return {}
    lock = os.path.join(root if not os.path.isabs(git_dir) else "", git_dir, "index.lock")
    try:
        age = int((now if now is not None else time.time()) - os.stat(lock).st_mtime)
    except FileNotFoundError:
        return {}
    if age < STALE_INDEX_LOCK_S:
        return {"locked": age}
    os.remove(lock)
    return {"removed_stale_index_lock": age}


def _restore_dirty_identical_to_upstream(g: GitFn, files: list[str], upstream: str) -> list[str]:
    """Unstaged edits whose bytes ALREADY equal ``upstream``'s blob: restore them to HEAD (the FF then
    delivers those same bytes, so nothing is lost). Returns the restored paths."""
    restored: list[str] = []
    for rel in files:
        rc1, local_sha, _e = g("hash-object", "--", rel)
        rc2, remote_sha, _e = g("rev-parse", f"{upstream}:{rel}")
        if rc1 == 0 and rc2 == 0 and local_sha == remote_sha and g("checkout", "--", rel)[0] == 0:
            restored.append(rel)
    return restored


def _local_commits_already_landed(g: GitFn, upstream: str) -> bool:
    """True when every line the primary's local-only commits ADD is present in ``upstream``'s version of
    that file and every line they REMOVE is absent from it — i.e. the content already reached dev
    through another commit (the typical case: a ledger-drain commit whose rows a branch later shipped).
    Any doubt (git error, deleted file, unmatched line) answers False."""
    rc, base, _e = g("merge-base", "HEAD", upstream)
    if rc != 0:
        return False
    rc, names, _e = g("diff", "--name-only", base, "HEAD")
    if rc != 0 or not names:
        return False
    for rel in names.splitlines():
        rc, theirs, _e = g("show", f"{upstream}:{rel}")
        if rc != 0:
            return False
        upstream_lines = set(theirs.splitlines())
        rc, patch, _e = g("diff", "--unified=0", base, "HEAD", "--", rel)
        if rc != 0:
            return False
        for ln in patch.splitlines():
            if ln.startswith(("+++", "---")):
                continue
            if ln.startswith("+") and ln[1:] not in upstream_lines:
                return False
            if ln.startswith("-") and ln[1:] in upstream_lines:
                return False
    return True


def _default_git(root: str) -> GitFn:
    def git(*args: str, timeout: float = 120) -> tuple[int, str, str]:
        p = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    return git


def _remove_identical_untracked_collisions(root: str, g: GitFn, upstream: str) -> dict[str, list[str]]:
    """Untracked files the FF would overwrite: delete those byte-identical to the
    incoming blob (no data lost; typically a tool wrote the same file the commit
    now carries), report the rest as ``blocked`` (never touched)."""
    out: dict[str, list[str]] = {"removed": [], "blocked": []}
    rc, untracked, _e = g("ls-files", "--others", "--exclude-standard")
    if rc != 0 or not untracked:
        return out
    rc, incoming, _e = g("diff", "--name-only", "--diff-filter=AR", "HEAD", upstream)
    if rc != 0:
        return out
    colliding = set(untracked.splitlines()) & set(incoming.splitlines())
    for rel in sorted(colliding):
        rc1, local_sha, _e = g("hash-object", "--", rel)
        rc2, remote_sha, _e = g("rev-parse", f"{upstream}:{rel}")
        if rc1 == 0 and rc2 == 0 and local_sha == remote_sha:
            os.remove(os.path.join(root, rel))
            out["removed"].append(rel)
        else:
            out["blocked"].append(rel)
    return out


def ff_primary_to_dev(
    root: str,
    *,
    dev_branch: str = "dev",
    remote: str = "origin",
    fetch: bool = False,
    git: GitFn | None = None,
) -> dict[str, Any]:
    """Fast-forward ``root`` (the primary checkout) to ``<remote>/<dev_branch>``.

    ``fetch=True`` refreshes the remote-tracking ref first (the SessionStart
    child); ``task_branch integrate`` passes False — its push already moved the
    shared ``refs/remotes`` ref. Never raises: every outcome is a status.
    """
    g = git or _default_git(root)
    upstream = f"{remote}/{dev_branch}"
    try:
        if fetch:
            rc, _o, err = g("fetch", "--quiet", remote, dev_branch)
            if rc != 0:
                return {"status": "error", "reason": f"fetch failed: {err[:200]}"}
        rc, branch, err = g("rev-parse", "--abbrev-ref", "HEAD")
        if rc != 0:
            return {"status": "error", "reason": f"rev-parse failed: {err[:200]}"}
        if branch == "HEAD":
            return {"status": "skipped_detached", "reason": "primary is on a detached HEAD"}
        if branch != dev_branch:
            return {"status": "skipped_branch",
                    "reason": f"primary is on {branch!r}, not {dev_branch!r}"}
        healed: dict[str, Any] = {}
        lock = _clear_stale_index_lock(root, g)
        if "locked" in lock:
            return {"status": "skipped_locked",
                    "reason": f"index.lock is {lock['locked']}s old (< {STALE_INDEX_LOCK_S}s): a git operation may be running"}
        healed.update(lock)
        rc, dirty, err = g("status", "--porcelain", "--untracked-files=no")
        if rc != 0:
            return {"status": "error", "reason": f"status failed: {err[:200]}"}
        kept_dirty: list[str] = []
        if dirty and g("diff", "--cached", "--quiet")[0] == 0:
            # 2026-11-13: a FINDINGS.md render byte-identical to dev's kept the primary 108 commits behind.
            unstaged = [ln.split(maxsplit=1)[-1] for ln in dirty.splitlines() if ln.strip()]
            if restored := _restore_dirty_identical_to_upstream(g, unstaged, upstream):
                healed["restored_identical_dirty"] = restored
                rc, dirty, err = g("status", "--porcelain", "--untracked-files=no")
                if rc != 0:
                    return {"status": "error", "reason": f"status failed: {err[:200]}"}
        if dirty:
            # split, never slice: callers may have stripped the first line's leading space
            files = [ln.split(maxsplit=1)[-1] for ln in dirty.splitlines() if ln.strip()]
            # Unstaged edits to files the FF does not touch are carried through untouched (git's own ff-only
            # check is the backstop). 2026-11-12: one unshipped council-ledger row kept the primary 113 commits
            # behind for two days, so every push ran a stale pre-push hook (the primary's hooks are symlinks).
            # A staged change (someone mid-commit) or an edit to a file the FF changes still refuses.
            staged = g("diff", "--cached", "--quiet")[0] != 0
            rc_in, incoming, _e = g("diff", "--name-only", "HEAD", upstream)
            overlap = sorted(set(files) & set(incoming.splitlines())) if rc_in == 0 else files
            if staged or overlap:
                return {"status": "skipped_dirty",
                        "reason": (f"{len(files)} tracked modification(s) in the primary"
                                   + (" (staged)" if staged else f"; the FF changes {len(overlap)} of them")),
                        "files": (overlap or files)[:20]}
            kept_dirty = files
        rc, counts, err = g("rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        if rc != 0:
            return {"status": "error", "reason": f"rev-list failed: {err[:200]}"}
        ahead, behind = (int(x) for x in counts.split())
        rc, before, _e = g("rev-parse", "--short", "HEAD")
        if ahead:
            # 2026-11-13: a ledger-drain commit whose rows had already shipped through a branch kept the
            # primary diverged. When every local line is already on dev, park HEAD under a backup ref and
            # move to dev (`reset --keep` refuses rather than touch an unrelated unstaged edit).
            if kept_dirty or not _local_commits_already_landed(g, upstream):
                return {"status": "skipped_diverged",
                        "reason": f"primary {dev_branch} has {ahead} commit(s) {upstream} lacks",
                        "head": before, **healed}
            rc, full, _e = g("rev-parse", "HEAD")
            if rc != 0 or g("update-ref", LANDED_BACKUP_PREFIX + full, full)[0] != 0:
                return {"status": "error", "reason": "could not write the landed-commit backup ref", **healed}
            rc, _o, err = g("reset", "--keep", upstream, timeout=600)
            if rc != 0:
                return {"status": "skipped_ff_failed", "reason": f"git reset --keep refused: {err[:300]}",
                        "head": before, **healed}
            rc, after, _e = g("rev-parse", "--short", "HEAD")
            return {"status": "fast_forwarded", "from": before, "to": after, "commits": behind,
                    "dropped_landed_commits": ahead, "backup_ref": LANDED_BACKUP_PREFIX + full, **healed}
        if not behind:
            return {"status": "up_to_date", "head": before, **healed}
        removed = _remove_identical_untracked_collisions(root, g, upstream)
        if removed.get("blocked"):
            return {"status": "skipped_untracked_conflict",
                    "reason": f"{len(removed['blocked'])} untracked file(s) differ from "
                              f"{upstream}'s version; refusing to overwrite",
                    "files": removed["blocked"][:20], "head": before}
        rc, _o, err = g("merge", "--ff-only", "--quiet", upstream, timeout=600)
        if rc != 0:
            return {"status": "skipped_ff_failed",
                    "reason": f"git merge --ff-only refused: {err[:300]}", "head": before}
        rc, after, _e = g("rev-parse", "--short", "HEAD")
        out = {"status": "fast_forwarded", "from": before, "to": after, "commits": behind, **healed}
        if kept_dirty:
            out["kept_dirty"] = kept_dirty[:20]
        if removed["removed"]:
            out["removed_identical_untracked"] = removed["removed"]
        return out
    except Exception as e:  # noqa: BLE001 — best-effort; the caller reports it
        return {"status": "error", "reason": f"{type(e).__name__}: {e}"}


def summary_line(result: dict[str, Any]) -> str:
    """One human line for a result ('' for the boring up-to-date case)."""
    s = result.get("status")
    healed = "".join([
        f"; removed a stale index.lock ({a}s old)" if (a := result.get("removed_stale_index_lock")) is not None else "",
        f"; restored {len(r)} edit(s) already identical to dev: {', '.join(r)}"
        if (r := result.get("restored_identical_dirty")) else "",
        f"; dropped {d} local commit(s) whose content is already on dev (backup {result.get('backup_ref')})"
        if (d := result.get("dropped_landed_commits")) else "",
    ])
    if s == "up_to_date":
        return f"noc: primary checkout healed{healed}" if healed else ""
    if s == "fast_forwarded":
        rm = result.get("removed_identical_untracked")
        return (f"noc: primary checkout fast-forwarded {result['from']}..{result['to']} "
                f"({result['commits']} commit(s))"
                + (f"; removed {len(rm)} byte-identical untracked file(s): {', '.join(rm)}" if rm else "")
                + (f"; kept {len(kd)} unstaged edit(s) the FF does not touch: {', '.join(kd)}"
                   if (kd := result.get("kept_dirty")) else "")
                + healed)
    if s is None:
        return ""
    return f"noc: primary checkout NOT fast-forwarded ({s}): {result.get('reason', '')}{healed}"


def _primary_root(start: str) -> str:
    """The primary checkout: the parent of the shared git-common-dir (works from any worktree)."""
    p = subprocess.run(["git", "-C", start, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise SystemExit(f"not a git checkout: {start}: {p.stderr.strip()[:200]}")
    return os.path.dirname(p.stdout.strip())


if __name__ == "__main__":  # steward §7: `python3 mcp/noctusai/primary_ff.py [path]`
    import json
    import sys

    root = _primary_root(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    result = ff_primary_to_dev(root, fetch=True)
    print(json.dumps({"primary": root, **result}, indent=2))
    print(summary_line(result) or f"noc: primary checkout up to date ({result.get('head', '')})")
    sys.exit(0 if result.get("status") in ("up_to_date", "fast_forwarded") else 1)
