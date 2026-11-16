#!/usr/bin/env python3
"""PostToolUse(Edit|Write|NotebookEdit) hook -- on the FIRST edit of a covered code file, say which living docs cover it.

UX over the Python gate, never a gate (KB § PATTERNS/common/harness-mods.md): the doc-staleness commit leg
(`scripts/hooks/commit-msg`, keeper `check_doc_staleness`) refused 476 commits because the agent learned which docs cover
a file only AT COMMIT TIME. This injects the answer at EDIT time, so the docs are updated in the same commit unprompted.

Hot path = one JSON read + glob match: the {doc: covered globs} map is precomputed by
`python mcp/noctusai/cli.py --write-doc-coverage-cache` (`doc_staleness.coverage_map`, the very set `check_range` couples
against). A missing or >1h-old cache is still served when present, and a DETACHED rebuild is started
(rate-limited); nothing heavy ever runs here. Dedupe per file + session in `.claude/cache/doc-coverage-seen.json`.

Stdlib-only; ALWAYS exits 0 (fail open, silent on any failure). Output = the harness's `additionalContext` JSON.
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".claude" / "cache" / "doc-coverage.json"
SEEN = ROOT / ".claude" / "cache" / "doc-coverage-seen.json"
REFRESH_MARK = ROOT / ".claude" / "cache" / "doc-coverage-refresh.mark"
CODE_EXTS = (".py", ".ts", ".tsx", ".sql")
MAX_DOCS = 6
MAX_AGE_S = 3600


def glob_match(path: str, pattern: str) -> bool:
    """Same predicate as `doc_staleness._glob_match` (a test pins the two together)."""
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3] + "/") or fnmatch.fnmatch(path, pattern[:-3] + "/*")
    return fnmatch.fnmatch(path, pattern)


def is_code(rel: str) -> bool:
    """Same non-material exclusions as `material_changes` (tests / __init__ never couple to a doc)."""
    parts = rel.split("/")
    if not rel.endswith(CODE_EXTS) or rel.endswith("__init__.py"):
        return False
    name = parts[-1]
    if any(p in ("tests", "test", "__tests__", "e2e") for p in parts[:-1]):
        return False
    return not (name.startswith("test_") or name == "conftest.py" or ".test." in name or ".spec." in name)


def rel_path(file_path: str) -> str | None:
    p = Path(file_path)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except (ValueError, OSError):
        pass
    s = p.as_posix()
    if "/.claude/worktrees/" in s:  # editing a claimed worktree from another checkout's session
        tail = s.split("/.claude/worktrees/", 1)[1].split("/", 1)
        return tail[1] if len(tail) == 2 else None
    return None


def _refresh_detached() -> None:
    """Rebuild the cache in the background (rate-limited 60s); the hot path never waits for it."""
    try:
        if REFRESH_MARK.exists() and time.time() - REFRESH_MARK.stat().st_mtime < 60:
            return
        REFRESH_MARK.parent.mkdir(parents=True, exist_ok=True)
        REFRESH_MARK.touch()
        py = next((c for c in (ROOT / "venv" / "bin" / "python",
                               Path(subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                                   cwd=ROOT, capture_output=True, text=True, timeout=3).stdout.strip()
                                    ).parent / "venv" / "bin" / "python") if c.is_file()), None)
        if py is None:
            return
        subprocess.Popen([str(py), str(ROOT / "mcp" / "noctusai" / "cli.py"), "--write-doc-coverage-cache",
                          "--worktree-path", str(ROOT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    except (OSError, subprocess.SubprocessError):
        pass


def message(rel: str, docs: list[str]) -> str:
    shown = ", ".join(f"`{d}`" for d in docs[:MAX_DOCS]) + (f" (+{len(docs) - MAX_DOCS} more)" if len(docs) > MAX_DOCS else "")
    return (f"Docs covering `{rel}`: {shown}. If this change adds/removes a file or changes a signature, update them in "
            f"THIS commit -- or add a `Docs-Reviewed: <doc> — <why unaffected>` trailer. The commit-msg doc-staleness "
            f"check will refuse otherwise (KB § PATTERNS/common/doc-staleness-gate.md).")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        ti = payload.get("tool_input") or {}
        fp = ti.get("file_path") or ti.get("notebook_path")
        if not fp:
            return 0
        rel = rel_path(str(fp))
        if not rel or not is_code(rel):
            return 0
        try:
            data = json.loads(CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _refresh_detached()
            return 0
        if time.time() - CACHE.stat().st_mtime > MAX_AGE_S:  # no git on the hot path: age, not HEAD, triggers a rebuild
            _refresh_detached()
        docs = sorted(d for d, globs in (data.get("docs") or {}).items() if any(glob_match(rel, g) for g in globs))
        if not docs:
            return 0
        sid = str(payload.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID") or "-")
        try:
            seen = json.loads(SEEN.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            seen = {}
        if seen.get("session") != sid:
            seen = {"session": sid, "files": []}
        if rel in seen["files"]:
            return 0
        seen["files"].append(rel)
        SEEN.parent.mkdir(parents=True, exist_ok=True)
        SEEN.write_text(json.dumps(seen), encoding="utf-8")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message(rel, docs)}}))
    except Exception as exc:  # noqa: BLE001 -- a UX hint never blocks an edit
        print(f"[noc-hook:doc-coverage] skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
