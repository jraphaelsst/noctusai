#!/usr/bin/env python3
"""PostToolUse hook — flag a Bash call whose non-zero exit matches a known
HARNESS-failure signature (missing browser, dead dev server, venv-less
worktree, a wrong argparse invocation, a command the shell couldn't find, a
timeout kill, a suite that collected zero tests, ...).

WHY THIS EXISTS (2026-09-20, same session as `gate_sweep`'s harness-validity
leg, three instances of ONE class)
---------------------------------------------------------------------------
`gate_sweep.py`'s `_harness_suspect` classifier only ever fires when
`gate_sweep` itself orchestrates a gate. Two of the three real instances
that day happened OUTSIDE it — a `pytest ... | tail -60` whose exit code
belonged to `tail`, and (the one this hook targets) a plain interactive
`cli.py --predeploy-check --product core` — wrong argparse syntax, the flag
takes a positional slug — that exited 2 before any real work ran, for all 6
live products, and got reported as "6 failing products". That failure was
in INTERPRETATION, not in any tool: nothing about it would ever route
through `gate_sweep`. A PostToolUse hook on every Bash call is the only
place that can catch it.

All the actual decision logic lives in the SHARED, stdlib-only
`harness_signatures.py` module (`bash_advisory(tool_response)` — same table
`gate_sweep.py` imports for its own orchestrated gates). This file only
speaks the harness's hook protocol (JSON on stdin -> stdout/stderr) and
loads that module BY PATH, the same `importlib.util.spec_from_file_location`
idiom `claude-guard-primary-write.py` already uses, for the same reason:
this hook runs after EVERY Bash call in the session, so its import cost is
paid hundreds of times — `harness_signatures.py` imports only `re` and
`dataclasses`, never the toolkit's `settings`/import graph, keeping this in
the low milliseconds.

ADVISORY BY CONSTRUCTION — three properties, on purpose:

* **Never blocks.** This always exits 0. A harness signature is a HINT
  ("this red is probably about the setup, not the code"), not a proof;
  blocking on a hint would be worse than the disease it treats. (PostToolUse
  cannot un-run the Bash call anyway — the point is to warn about how to
  INTERPRET a result that already happened.)
* **Silent on success and on an unmatched non-zero exit.** `bash_advisory`
  returns `None` for both — a genuinely unclassified red gets NO comment
  from this hook, on purpose: inventing a guess there would be the same
  harm the signature table exists to prevent, pointed the other way.
* **Fails OPEN, loudly.** If the module cannot be loaded or throws, the
  call proceeds silently to stdout/exit-0 and the reason goes to stderr —
  same posture as every other `claude-guard-*` hook in this repo.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIGNATURES = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "harness_signatures.py"


def _load_signatures():
    spec = importlib.util.spec_from_file_location("noc_harness_signatures", SIGNATURES)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {SIGNATURES}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _format_warning(advisory: dict) -> str:
    return (
        f"HARNESS SIGNATURE MATCHED: `{advisory['signature']}` "
        f"(exit_code={advisory.get('exit_code')}). This judges the SETUP, "
        "not the code under test — do not report this Bash call's failure "
        "as a verdict about the subject.\n"
        f"Evidence: {advisory['matched_line']}\n"
        f"Remedy: {advisory['remedy']}"
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    try:
        signatures = _load_signatures()
        advisory = signatures.bash_advisory(payload.get("tool_response"))
    except Exception as exc:  # fail open — see the module docstring
        print(
            f"claude-guard-harness-signature: unavailable ({exc}) — not blocking",
            file=sys.stderr,
        )
        return 0

    if advisory is None:
        return 0

    warning = _format_warning(advisory)
    print(warning, file=sys.stderr)
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": warning,
        }
    }, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
