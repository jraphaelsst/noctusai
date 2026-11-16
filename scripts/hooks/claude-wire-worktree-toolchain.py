#!/usr/bin/env python3
"""SessionStart / SubagentStart hook - give a harness-created worktree its node toolchain BY CONSTRUCTION.

`mcp/noctusai/node/node_modules` (ts-morph, PGlite) is gitignored, so every fresh `.claude/worktrees/agent-*` tree
lacked it and each engineer symlinked the primary's copy by hand to make the PGlite replay fixtures run
(NOC-REMEDIATE[worktree-pglite-node-modules]). `task_branch action=start` already wires its own worktrees; harness
agent worktrees never went through it. This hook runs the SAME resolver (`mcp/noctusai/node_toolchain.py`):

  * the tree the session/agent starts in: `provision` - a lockfile-identical link to the primary's install, else a LOUD
    `npm ci --prefix` into that tree (bounded by NPM_TIMEOUT_S);
  * every other `.claude/worktrees/*` tree of the clone: link-only (cheap, no network), so a tree created since the last
    session is wired too.

It never blocks a session: always exit 0. It is never silent about a failure: the reason (with the exact fix) goes to the
agent as additionalContext. Stdlib only; the resolver is loaded by path from THIS checkout's toolkit.
KB § PATTERNS/architect/mcp-tool-conventions.md (Node toolchain).
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

NPM_TIMEOUT_S = 240


def _git(cwd: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def _toolchain_module(toolkit_root: Path):
    path = toolkit_root / "mcp" / "noctusai" / "node_toolchain.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_noc_node_toolchain", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass needs the module registered
    spec.loader.exec_module(mod)
    return mod


def linked_worktree_top(start: Path) -> Path | None:
    """The top of `start`'s tree when it is a LINKED worktree (not the primary), else None."""
    top = _git(start, "rev-parse", "--show-toplevel")
    common = _git(start, "rev-parse", "--path-format=absolute", "--git-common-dir")
    gitdir = _git(start, "rev-parse", "--path-format=absolute", "--git-dir")
    if not top or not common or not gitdir or Path(common).resolve() == Path(gitdir).resolve():
        return None
    return Path(top)


def wire(start: Path, toolkit_root: Path, *, npm_timeout: int = NPM_TIMEOUT_S) -> list[str]:
    """Lines to tell the agent; [] when nothing needed doing. See the module docstring."""
    mod = _toolchain_module(toolkit_root)
    if mod is None:
        return []
    lines: list[str] = []
    own = linked_worktree_top(start)
    seen: set[Path] = set()
    if own is not None:
        seen.add(own.resolve())
        had = (own / "mcp" / "noctusai" / "node" / "node_modules").exists()
        tc = mod.provision(own, timeout=npm_timeout)
        if not tc.ok:
            lines.append(f"[noc-node-toolchain] LOUD: this worktree has NO usable node toolchain - {tc.reason}. "
                         "ts-morph keepers and the PGlite/real-Postgres fixtures cannot run here until that is fixed "
                         "(under NOC_REQUIRE_REAL_PG=1 they FAIL, naming this).")
        elif not had or tc.source in ("linked", "installed"):
            lines.append(f"[noc-node-toolchain] {own.name}: node toolchain {tc.source} (mcp/noctusai/node/node_modules).")
    common = _git(start, "rev-parse", "--path-format=absolute", "--git-common-dir")
    wt_dir = Path(common).parent / ".claude" / "worktrees" if common else None
    linked = 0
    if wt_dir is not None and wt_dir.is_dir():
        for child in sorted(wt_dir.iterdir()):
            if child.resolve() in seen or not (child / ".git").exists():
                continue
            if (child / "mcp" / "noctusai" / "node" / "node_modules").exists():
                continue
            tc = mod.resolve(child)  # link-only: lockfile-identical or nothing, no network
            if tc.ok and tc.source == "linked":
                linked += 1
    if linked:
        lines.append(f"[noc-node-toolchain] linked the primary's node toolchain into {linked} other worktree(s).")
    return lines


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    try:
        start = Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        toolkit_root = Path(__file__).resolve().parents[2]
        lines = wire(start, toolkit_root)
    except Exception as exc:  # noqa: BLE001 - never block a session start, never swallow it either
        lines = [f"[noc-node-toolchain] LOUD: the worktree toolchain wiring itself failed: {type(exc).__name__}: {exc}"]
    if lines:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": payload.get("hook_event_name", "SessionStart"),
                                                 "additionalContext": "\n".join(lines)}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
