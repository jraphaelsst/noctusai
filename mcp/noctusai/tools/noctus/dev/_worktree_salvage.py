"""Learn/extract-before-delete — the mechanical "recovery record → tracked ledger" leg.

KB § PATTERNS/storage-hygiene.md § 2.3 (Learn/extract-before-delete). The worktree
analogue of `noctus.dev.archive`'s learn-before-archive: every swept worktree is
recorded to a **tracked** ledger (`project-history/worktree-salvage.ndjson`, the
sibling of `project-history/ledger.ndjson`) so the recovery pointer (branch + SHA)
survives the transient out-of-repo `~/…-salvage-*/` dir — the drift that re-hit
2026-05-25. Shared by `noctus.dev.mole` (worktree sweep) +
`noctus.dev.cleanup_stale_worktrees` — one source of truth, no parity drift
(mirrors the `_worktree_staleness` shared-predicate pattern).

The automated sweeps only ever remove merged-to-`dev` worktrees (content already on
`dev` ⇒ extraction-no-op for the *learnings* leg); it never needs to salvage
uncommitted diffs (the classifier refuses dirty/unmerged worktrees). Best-effort: a
ledger-write failure is logged, never raised — recording must not break a sweep.

2026-09-24 (owner decision, KB § PATTERNS/common/ledger-store.md):
  * the ledger lives on the orphan `origin/ledgers` branch — rows are appended
    through `_ledger_store`, never committed to dev (373 `chore(salvage)` dev
    commits since 2026-08-01 were this ledger);
  * a record whose SHA is already on `origin/dev` (ancestor, or every commit
    patch-equivalent) is NOT written: `origin/dev` itself recovers it, so the
    row was pure noise. Only a pointer that recovers something dev does not
    have is kept (an unknown/unresolvable SHA is kept — never dropped on doubt).
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ._ledger_store import append_rows, read_ledger_text, store_mode, MODE_FAKE

logger = logging.getLogger(__name__)

# The legacy dev copy (S2 dual-read source; the Fake store's backing file).
LEDGER_REL = "project-history/worktree-salvage.ndjson"
LEDGER_NAME = "worktree-salvage.ndjson"
STORE_LOCATION = f"origin/ledgers:{LEDGER_NAME}"
MERGED_BASE = "origin/dev"


def branch_sha(root: Path, branch: str | None) -> str | None:
    """Resolve a branch ref to its SHA — the recovery pointer (`git branch <name> <sha>`).

    `git worktree remove` keeps the branch ref, so the SHA stays resolvable after
    removal; capturing it records how to recover the work. None if unresolvable
    (e.g. an orphan dir with no branch).
    """
    if not branch:
        return None
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "rev-parse", branch],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("worktree-salvage: rev-parse %s failed (%s)", branch, exc)
        return None


def is_merged_into(root: Path, sha: str | None, base: str = MERGED_BASE) -> bool | None:
    """Is every commit reachable from ``sha`` already on ``base``?

    ``True``  — ``sha`` is an ancestor of ``base``, or ``git cherry`` shows every
                commit patch-equivalent (squash/rebase-integrated);
    ``False`` — at least one commit is NOT on ``base`` (the pointer recovers work);
    ``None``  — cannot tell (no sha, no ``base``, not a repo). Callers KEEP the row.
    """
    if not sha:
        return None
    try:
        r = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", sha, base],
                           capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            return True
        if r.returncode != 1:
            return None
        c = subprocess.run(["git", "-C", str(root), "cherry", base, sha],
                           capture_output=True, text=True, timeout=30)
        if c.returncode != 0:
            return None
        return not any(ln.startswith("+") for ln in c.stdout.splitlines())
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("worktree-salvage: merged check for %s failed (%s)", sha, exc)
        return None


def build_records(removed: list[dict]) -> list[dict]:
    """Build ndjson-ready ledger records for removed worktrees. Pure (no IO).

    Each `removed` entry: {"path", "branch", "sha", "reason"}.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return [
        {
            "ts": ts,
            "event": "worktree-sweep",
            "path": e.get("path"),
            "branch": e.get("branch"),
            "sha": e.get("sha"),
            "reason": e.get("reason") or "merged-to-dev",
        }
        for e in removed
    ]


def _existing_keys(ledger: Path) -> set[tuple]:
    """Read the ledger and return the set of (path, branch, sha) keys already recorded.

    The idempotency primitive — `append_ledger` skips a record whose key already
    appears. A malformed line is silently skipped (no spurious dupes from bad data);
    a read failure returns the empty set (safe — caller appends as if fresh).
    """
    keys: set[tuple] = set()
    try:
        text, _store_err = read_ledger_text(LEDGER_NAME, ledger)
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            keys.add((rec.get("path"), rec.get("branch"), rec.get("sha")))
    except OSError as exc:
        logger.warning("worktree-salvage: read ledger %s failed (%s)", ledger, exc)
    return keys


def append_ledger(root: Path, records: list[dict]) -> Path | str | None:
    """Append recovery records to the salvage ledger — idempotent, noise-free.

    Drops records whose SHA is already on ``origin/dev`` (see
    :func:`is_merged_into` — dev recovers them itself), then skips any whose
    (path, branch, sha) is already recorded (dual-read of the dev copy ∪
    origin/ledgers; the N=3 cross-tree loop fix of 2026-05-28). The rest are
    appended through `_ledger_store` (origin/ledgers).

    Returns the ledger LOCATION when at least one record was written or all
    were already recorded (``STORE_LOCATION`` for the Real store, the local file
    for the Fake); ``None`` for empty input, when every record was
    merged-and-skipped, or on hard failure. Never raises.
    """
    if not records:
        return None
    ledger = root / LEDGER_REL
    location: Path | str = ledger if store_mode() == MODE_FAKE else STORE_LOCATION
    try:
        recordable = [rec for rec in records if is_merged_into(root, rec.get("sha")) is not True]
        skipped = len(records) - len(recordable)
        if skipped:
            logger.info("worktree-salvage: %d record(s) skipped — already on %s", skipped, MERGED_BASE)
        if not recordable:
            return None
        existing = _existing_keys(ledger)
        new = [
            rec for rec in recordable
            if (rec.get("path"), rec.get("branch"), rec.get("sha")) not in existing
        ]
        if not new:
            return location  # already recorded — nothing to write
        result = append_rows(LEDGER_NAME, ledger, new,
                             message=f"worktree-salvage: {len(new)} recovery pointer(s)")
        if not result.get("ok"):
            logger.warning("worktree-salvage: rows spooled, not yet on origin/ledgers: %s",
                           result.get("error"))
        return location
    except (OSError, ValueError) as exc:
        logger.warning("worktree-salvage: append ledger %s failed (%s)", ledger, exc)
        return None


def record_sweep(root: Path, removed: list[dict]) -> Path | str | None:
    """Convenience: build + append in one call. Returns the ledger path or None."""
    return append_ledger(root, build_records(removed))
