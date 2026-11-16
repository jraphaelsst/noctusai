"""Backstop: a ledger/registry TOOL must never write into the shared PRIMARY checkout.

Why (2026-11-15, found by the release steward). `findings_ledger` append/update/reconcile, the gate-alignment inventory
writers and the access-tier catalog all wrote `project-history/**` straight into whatever tree the MCP server's
`REPO_ROOT` pointed at, which is the shared primary checkout sitting on `dev`. Nothing ever shipped those edits except
`task_branch`'s end-of-run "chore(ledger)" drain, which committed them on the primary's own `dev`; the primary then
diverged from `origin/dev` (1 ahead, 11 behind) and could no longer fast-forward.

The CONSTRUCTION leg is elsewhere: row writes (findings append/update) go through `_ledger_store` (git plumbing, off
every working tree, pushed by itself); code-coupled renders (reconcile, inventory, catalog) are written in the caller's
worktree and ship with its branch. THIS module is the safety net for the writes that still touch a tree: it refuses
loudly when that tree is the shared primary on a shared branch, names `noctus.dev.ledger_store`, and records a gate
event so the wall shows up in `gate_alignment action=walls` if anything keeps hitting it.

Stdlib-only apart from the lazy telemetry import; everything injectable (`run`) so tests use real git in a tmp dir.
KB § PATTERNS/common/ledger-store.md
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from .primary_write_guard import SHARED_BRANCHES

GATE = "ledger-primary-write"

Run = Callable[[list[str], Path], "subprocess.CompletedProcess[str]"]


class PrimaryLedgerWriteRefused(RuntimeError):
    """A ledger/registry write was aimed at the shared primary checkout."""


def _run(cmd: list[str], cwd: Path) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=15, check=False)


def _abs(base: Path, out: str) -> Path:
    p = Path(out.strip())
    return (p if p.is_absolute() else base / p).resolve()


def is_shared_primary(root: Path, *, run: Run = _run) -> tuple[bool, str]:
    """(True, branch) when ``root`` is the primary checkout (not a linked worktree) on a shared branch.

    A non-git directory, a linked worktree, a detached HEAD or a feature branch are all NOT the shared primary."""
    root = Path(root)
    if not root.is_dir():
        return False, ""
    try:
        gd = run(["git", "rev-parse", "--git-dir"], root)
        cd = run(["git", "rev-parse", "--git-common-dir"], root)
        br = run(["git", "symbolic-ref", "--short", "-q", "HEAD"], root)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if gd.returncode != 0 or cd.returncode != 0:
        return False, ""
    if _abs(root, gd.stdout) != _abs(root, cd.stdout):
        return False, ""  # a linked worktree: its own HEAD, ships with its own branch
    branch = br.stdout.strip() if br.returncode == 0 else ""
    return branch in SHARED_BRANCHES, branch


def refusal_message(root: Path, tool: str, branch: str) -> str:
    return (f"[noc-guard:{GATE}] {tool} would write project-history files into the shared PRIMARY checkout "
            f"{root} (on `{branch}`), where nothing ships them and the primary diverges from origin/dev. "
            "Row writes go through `noctus.dev.ledger_store` (git plumbing, off every working tree, pushed by itself: "
            "`findings_ledger append|update` already do); a code-coupled render/inventory/catalog write must run in "
            "your own worktree (`worktree_path=<your worktree>`) and ship with that branch.")


def ensure_not_shared_primary(root: Path | None, tool: str, *, run: Run = _run, record: bool = True) -> None:
    """Raise :class:`PrimaryLedgerWriteRefused` when ``root`` is the shared primary on a shared branch."""
    if root is None:
        return
    shared, branch = is_shared_primary(Path(root), run=run)
    if not shared:
        return
    if record:
        _record(tool, str(root))
    raise PrimaryLedgerWriteRefused(refusal_message(Path(root), tool, branch))


def _record(tool: str, target: str) -> None:
    try:  # telemetry must never change the verdict
        from tools.noctus.dev import gate_alignment as ga
        ga.record_event(GATE, "deny", kind=tool, target=target, reason="ledger write aimed at the shared primary",
                        source="_primary_ledger_guard")
    except Exception:  # noqa: BLE001 -- advisory
        return


__all__ = ["GATE", "PrimaryLedgerWriteRefused", "ensure_not_shared_primary", "is_shared_primary", "refusal_message"]
