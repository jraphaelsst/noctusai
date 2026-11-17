"""ci_full_green: what a `scope=full` Tests & Build run is, and which one is the last full-green.

WHY (2026-11-17): branch verdicts and merge-queue batches now run test.yml SCOPED (`scope=changed`); a scheduled run
every 6h on dev and the bless/promote gate are what still prove the WHOLE suite. A run states its scope in its own
title (test.yml `run-name: ... [scope=full|changed]`), so ONE server-filtered `gh run list --json displayTitle` answers
"is this run full" with no per-run / per-job API call. Stdlib only: the scheduled run's summary step runs this with
a bare `python3` (stdin = `gh run list --json displayTitle,headSha,databaseId` output).

KB: PATTERNS/devops/merge-queue.md (scoped verdicts + scheduled full) · PATTERNS/architect/git-branch-model.md (bless gate).
"""
from __future__ import annotations

import json
import sys
from typing import Callable

FULL_MARK = "[scope=full]"


def is_full_title(title: str | None) -> bool:
    return FULL_MARK in (title or "")


def full_runs(runs: list[dict]) -> list[dict]:
    """The runs (newest first, as `gh run list` returns them) whose title says they ran the full suite."""
    return [r for r in runs if is_full_title(r.get("displayTitle"))]


def last_full_green(runs: list[dict], is_ancestor: Callable[[str, str], bool], head: str) -> str | None:
    """Head sha of the newest full run in `runs` (already status=success) that is an ancestor of `head`, else None."""
    for r in full_runs(runs):
        sha = r.get("headSha") or ""
        if sha and is_ancestor(sha, head):
            return sha
    return None


def main(argv: list[str] | None = None) -> int:
    """`ci_full_green.py <head> <ancestor-checked-by-git>`: reads run JSON on stdin, prints the last full-green sha (or '')."""
    import subprocess
    head = (argv or sys.argv[1:] or ["HEAD"])[0]

    def anc(a: str, b: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], check=False,  # noqa: S603, S607
                              capture_output=True).returncode == 0

    runs = json.loads(sys.stdin.read() or "[]")
    print(last_full_green(runs, anc, head) or "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
