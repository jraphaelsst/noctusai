#!/usr/bin/env python3
"""PreToolUse hook (Bash) - the ONE place a Bash command is rewritten or refused by the heavy-run and background guards.

Replaces the two separately wired hooks (`claude-guard-heavy-run.py`, `claude-guard-background-launch.py`): both
returned `updatedInput`, Claude Code runs matching hooks in parallel on the original input and one rewrite wins,
so a background heavy command lost a wrap. The composer (`bash_rewrite_chain.decide`) applies them in a fixed order
(hw_admission innermost, bg_run outermost), a deny from either wins, each rewrite logs its own guard event.
Same contract as the other guards: payload on stdin, fail-CLOSED via `_guard_failclosed.run_guard`; a deny carries
the marker of the member guard that issued it (`[noc-guard:heavy-run]` / `[noc-guard:background-launch]`).
The two old scripts stay as standalone entry points for tests/debugging but are NOT wired in settings.json.
KB § PATTERNS/common/background-agent-lifecycle.md (Rewrite chain).
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAIN = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "bash_rewrite_chain.py"

# Fast path: this hook matches EVERY Bash call. Anything that is neither a background launch, nor could hold a
# heavy run, nor a never-ending shape returns before any module load (superset of what the two judges can report).
_PREFILTER = re.compile(
    r"\b(?:while|until|tail|watch|pytest|py\.test|vitest|vite|playwright|whisper\w*|npm|pnpm|yarn|npx|pnpx|bunx|bun|uv)\b"
    r"|--watch|\.(?:sh|bash|zsh|py)\b|(?:^|[\s;&|(])\./|\bpython[\d.]*\b|\b(?:bash|sh|zsh)\b|<<")


def _judge(payload: dict) -> dict | None:
    return load_module(CHAIN).decide(payload)


def main() -> int:
    raw = sys.stdin.read()
    try:
        quick = json.loads(raw) if raw.strip() else None
    except ValueError:
        quick = None  # malformed: let run_guard refuse it, fail-closed
    if isinstance(quick, dict):
        ti = quick.get("tool_input") or {}
        if quick.get("tool_name") != "Bash":
            return 0
        if not ti.get("run_in_background") and not _PREFILTER.search(str(ti.get("command") or "")):
            return 0
    return run_guard("bash-rewrite", _judge, stdin=io.StringIO(raw))


if __name__ == "__main__":
    raise SystemExit(main())
