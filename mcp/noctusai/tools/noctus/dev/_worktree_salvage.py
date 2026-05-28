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
`dev` ⇒ extraction-no-op for the *learnings* leg), so this records the recovery
pointer + sweep provenance; it never needs to salvage uncommitted diffs (the
classifier refuses dirty/unmerged worktrees). Best-effort: a ledger-write failure is
logged, never raised — recording must not break a sweep.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Tracked, durable — committed like ledger.ndjson; survives the transient salvage dir.
LEDGER_REL = "project-history/worktree-salvage.ndjson"


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
    if not ledger.exists():
        return set()
    keys: set[tuple] = set()
    try:
        for line in ledger.read_text(encoding="utf-8").splitlines():
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


def append_ledger(root: Path, records: list[dict]) -> Path | None:
    """Append recovery records to the TRACKED worktree-salvage ledger — idempotent.

    Skips a record whose (path, branch, sha) is already in the ledger. The N=3
    cross-tree hazard fix (2026-05-28): the previous unconditional append created
    a loop — every cleanup invocation re-appended the same pointer, leaving the
    worktree dirty and blocking `git worktree remove`. Returns the ledger path
    when at least one record was *written*, or when the path is already canonical
    (records all duplicates) — callers can use the path to git-stage. Returns None
    only on hard failure or empty input. Never raises.
    """
    if not records:
        return None
    ledger = root / LEDGER_REL
    try:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        existing = _existing_keys(ledger)
        new = [
            rec for rec in records
            if (rec.get("path"), rec.get("branch"), rec.get("sha")) not in existing
        ]
        if not new:
            return ledger  # canonical — caller still gets the path; nothing dirty
        with ledger.open("a", encoding="utf-8") as fh:
            for rec in new:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return ledger
    except OSError as exc:
        logger.warning("worktree-salvage: append ledger %s failed (%s)", ledger, exc)
        return None


def record_sweep(root: Path, removed: list[dict]) -> Path | None:
    """Convenience: build + append in one call. Returns the ledger path or None."""
    return append_ledger(root, build_records(removed))
