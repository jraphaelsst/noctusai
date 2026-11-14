#!/usr/bin/env python3
"""Launch wrapper for EVERY background command: it carries a purpose and an end condition the process
checks itself, salvages its own output on exit, and tree-stops its children (no orphans).

    python3 scripts/bg_run.py --purpose "wait for CI of feat/x" --done "run finishes" -- gh run watch 123
    python3 scripts/bg_run.py --purpose "poll deliverable" --done "DONE line appears" \
        --done-when 'grep -q DONE run.log' --command 'tail -f run.log'
    python3 scripts/bg_run.py --purpose "dev server for the session" --long-lived -- npm run dev

No lifetime cap, no idle timer (owner, 2026-11-14): it ends when the command exits or --done-when
succeeds, not on a clock. Open-ended background launches without it are refused at launch by
claude-guard-background-launch.py. KB § PATTERNS/common/background-agent-lifecycle.md
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "hooks"))
import _bg_process_core as core  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(core.wrapper_main(sys.argv[1:]))
