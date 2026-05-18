"""github.diagnostics.* tools — `gh` dependency introspection.

`github.diagnostics.connection_status` — the gated-capability honesty
signal (CLAUDE.md §1). Surfaces whether the `gh` binary is present AND
authenticated so a "succeeds-empty" read isn't silently misread as
"no data" when `gh` is merely logged out. PURE read, never faked.
"""
from __future__ import annotations

import logging
from typing import Optional

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import gh
from ..settings import get_settings
from ..types import ConnectionStatusInput, ConnectionStatusOutput

logger = logging.getLogger(__name__)


async def connection_status(args: dict) -> dict:
    ConnectionStatusInput(**args)
    s = get_settings()
    gh_path = s.effective_gh_path
    available = gh.gh_available(gh_path)
    if not available:
        return ConnectionStatusOutput(
            gh_available=False,
            default_repo=s.default_repo,
            error=typed_error(
                gh.GitHubCliError(
                    f"`{gh_path}` not found on PATH — install the GitHub "
                    f"CLI and run `gh auth login`.",
                    status=424,
                )
            ),
        ).model_dump()

    version: Optional[str] = None
    try:
        raw = gh.run_gh(
            ["--version"], gh_path=gh_path, timeout=s.timeout_seconds,
            parse_json=False,
        )
        version = (raw or "").splitlines()[0] if raw else None
    except gh.GitHubCliError:
        version = None  # surfaced via authenticated=False below; not fatal

    authenticated = False
    account: Optional[str] = None
    auth_err: Optional[dict] = None
    try:
        login = gh.run_gh(
            ["api", "user", "--jq", ".login"],
            gh_path=gh_path, timeout=s.timeout_seconds, parse_json=False,
        )
        account = (login or "").strip() or None
        authenticated = account is not None
    except gh.GitHubCliError as e:
        # `gh` present but logged out — a real, typed, never-faked signal.
        auth_err = typed_error(e)

    return ConnectionStatusOutput(
        gh_available=True,
        gh_version=version,
        authenticated=authenticated,
        account=account,
        default_repo=s.default_repo,
        error=auth_err,
    ).model_dump()


HANDLERS = {"github.diagnostics.connection_status": connection_status}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="github.diagnostics.connection_status",
            description="Introspect the `gh` dependency — binary present? "
            "authenticated? which account? resolved default repo? "
            "READ-ONLY. The gated-capability honesty signal: a logged-out "
            "`gh` is reported as authenticated=false, never faked.",
            inputSchema=ConnectionStatusInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
