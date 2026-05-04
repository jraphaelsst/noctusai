"""dev_team CLI — ``python -m dev_team [run|status|route] ...``.

This is the human / shell entrypoint. The MCP tools at
``mcp/noctusai/tools/noctus/team/`` are the agent-facing entrypoint; both
share the same dispatch shape so behavior is identical.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint. Returns exit code."""
    parser = argparse.ArgumentParser(
        prog="dev_team",
        description="agno multi-agent dev team for NoctusAI.",
    )
    sub = parser.add_subparsers(dest="cmd")

    run = sub.add_parser("run", help="Fire the team for a task.")
    run.add_argument("task", help="The task description for the team.")
    run.add_argument("--project", help="Project slug for memory scoping.", default=None)
    run.add_argument("--config", help="YAML config name (default: default).", default="default")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the team and print its shape; do not invoke any LLM.",
    )

    status = sub.add_parser("status", help="Show current team state from memory.")
    status.add_argument("--project", help="Project slug for memory scoping.", default=None)

    route = sub.add_parser("route", help="Decide team-vs-direct for a task.")
    route.add_argument("task", help="The task description.")

    args = parser.parse_args(argv)

    if args.cmd is None:
        parser.print_help()
        return 0

    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "status":
        return _cmd_status(args)
    if args.cmd == "route":
        return _cmd_route(args)
    parser.print_help()
    return 2


def _cmd_run(args: argparse.Namespace) -> int:
    from dev_team.team import build_team

    team = build_team(config_name=args.config)
    if args.dry_run:
        print(_describe_team(team))
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "[dev_team] ANTHROPIC_API_KEY not set — cannot run live. "
            "Use --dry-run to inspect the team shape, or export the key.",
            file=sys.stderr,
        )
        return 3
    result = team.run(args.task)
    print(getattr(result, "content", result))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from dev_team.memory import MemoryStore

    store = MemoryStore(project=args.project)
    snapshot = store.snapshot()
    for k, v in snapshot.items():
        print(f"{k}: {v}")
    return 0


def _cmd_route(args: argparse.Namespace) -> int:
    from dev_team.team import recommend_route

    decision = recommend_route(args.task)
    print(f"recommended: {decision['recommended']}")
    print(f"rationale: {decision['rationale']}")
    return 0


def _describe_team(team) -> str:
    """Best-effort textual dump of the team shape — no LLM call."""
    lines = [
        f"Team mode: {getattr(team, 'mode', 'coordinate')}",
        f"Members: {[getattr(m, 'name', repr(m)) for m in getattr(team, 'members', [])]}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
