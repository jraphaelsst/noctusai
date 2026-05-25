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
from .errors import confirmation_required_message, typed_error
from .transport import (
    BROWSER_USER_AGENT,
    DEFAULT_USER_AGENT,
    ConnectorHttpError,
    normalize_base_url,
    request_json,
)
from .registry import build_registry
from .seed_pin import pin_in_tree_seed
from .settings import ConnectorSettings, make_get_settings

__all__ = [
    "ConnectorSettings",
    "make_get_settings",
    "build_registry",
    "typed_error",
    "confirmation_required_message",
    "request_json",
    "normalize_base_url",
    "ConnectorHttpError",
    "BROWSER_USER_AGENT",
    "DEFAULT_USER_AGENT",
    "prepare_sys_path",
    "pin_in_tree_seed",
    "configure_stderr_logging",
    "run_stdio_server",
]
