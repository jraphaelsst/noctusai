"""`mcp/_kit` — shared connector-MCP boilerplate.

The platform's connector MCP servers (`mcp/vista`, and the upcoming
`mcp/meta` / `mcp/google`) share the same stdio bootstrap, settings
pattern, tool-registry aggregation, and error envelope. N=3 recurrence
⇒ formalized here (per the DRY recurrence rule) so the 3rd connector
composes the kit instead of copy-pasting vista.

A new `mcp/<vendor>` server is ~30 lines: a `settings.py` subclassing
`ConnectorSettings` + `make_get_settings`, leaf tool modules following
the `HANDLERS`/`tool_descriptors()`/`register()` contract, a
`tools/__init__.py` calling `build_registry`, and a `server.py` calling
`prepare_sys_path` → `configure_stderr_logging` → `run_stdio_server`.

See `mcp/_kit/README.md` for the full composition recipe.
"""
from __future__ import annotations

from .bootstrap import (
    configure_stderr_logging,
    prepare_sys_path,
    run_stdio_server,
)
from .errors import typed_error
from .registry import build_registry
from .settings import ConnectorSettings, make_get_settings

__all__ = [
    "ConnectorSettings",
    "make_get_settings",
    "build_registry",
    "typed_error",
    "prepare_sys_path",
    "configure_stderr_logging",
    "run_stdio_server",
]
