#!/usr/bin/env python3
"""PreToolUse hook — refuse a write aimed at the primary checkout on a shared
branch, AND (separately) refuse a git invocation that disables its own hooks.

Thin adapter. Every decision lives in
`mcp/noctusai/tools/noctus/dev/primary_write_guard.py` — `decide()` for the
primary-checkout-write concern, `decide_git_bypass()` for the hooks-bypass
concern (deliberately two independent functions in the SAME module; see that
function's docstring for why). This file only speaks the harness's hook
protocol (JSON on stdin → a permission decision on stdout), and loads that
ONE module ONCE per call — checking both concerns costs no additional
`importlib` round-trip, only two extra function calls on an already-loaded
module.

Two deliberate properties:

* **It loads the guard BY PATH, not as a package.** Importing
  `tools.noctus.dev.…` normally would drag in `settings` and the rest of the
  toolkit; this hook runs before EVERY Bash/Edit/Write call, so its import cost
  is paid hundreds of times per session. By-path import of a stdlib-only module
  keeps that in the low milliseconds.
* **It fails OPEN, loudly.** If the guard cannot be loaded or throws, the tool
  call proceeds and the reason goes to stderr. A gate that hard-fails every tool
  call when its own probe breaks is a gate that gets uninstalled by lunchtime;
  `check_primary_checkout_commit` is still downstream of it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "primary_write_guard.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("noc_primary_write_guard", GUARD)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {GUARD}")
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: @dataclass resolves annotations through
    # sys.modules and raises without it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    try:
        guard = _load_guard()
        # Hooks-bypass is checked FIRST: it is the universal, branch- and
        # location-independent concern (see `decide_git_bypass`'s own
        # docstring), so a command that is both a hooks bypass AND a
        # primary-checkout write gets the more specific reason.
        verdict = guard.decide_git_bypass(tool_name, tool_input)
        if verdict is None:
            verdict = guard.decide(tool_name, tool_input, payload.get("cwd"))
    except Exception as exc:  # fail open — see the module docstring
        print(f"claude-guard-primary-write: guard unavailable ({exc}) — not blocking", file=sys.stderr)
        return 0

    if verdict is None:
        return 0

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": verdict["reason"],
        }
    }, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
