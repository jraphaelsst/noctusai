#!/usr/bin/env python3
"""PreToolUse hook (Bash + the steward-class MCP tools) - only the elected release steward queues/deploys.

Sibling of `claude-guard-heavy-run.py`, same contract: payload on stdin, the
guard module's verdict out, fail-CLOSED via `_guard_failclosed.run_guard`
(`[noc-guard:release-steward]`). Every decision lives in
`mcp/noctusai/tools/noctus/dev/release_steward.py` (`decide`), which the MCP
tools re-run as their own backstop - one decision function, two ends.

Never denied: `release_steward` itself (claim/request/status/...), read-only
calls and dry-runs. Denied for a non-steward: enqueue/integrate/landed,
release bless|promote|backmerge, deploy_pull/deploy_image/migrate_product/
record_applied_migrations/vps recreate with confirm, and `git push` to
dev|main|prod|mq/*. The deny names the steward and says: queue it with
release_steward action=request and keep building - do not wait.
KB § PATTERNS/devops/release-steward.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _guard_failclosed import load_module, run_guard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus" / "dev" / "release_steward.py"


def _judge(payload: dict) -> dict | None:
    return load_module(GUARD).decide(payload)


def main() -> int:
    return run_guard("release-steward", _judge)


if __name__ == "__main__":
    raise SystemExit(main())
