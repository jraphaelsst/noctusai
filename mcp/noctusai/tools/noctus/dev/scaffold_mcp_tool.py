"""noctus.dev.scaffold_mcp_tool — two targets.

target='connector' (default): emit a connector-MCP leaf skeleton
(register/HANDLERS/tool_descriptors + Pydantic In/Out + confirm-gate+
audit if write) as CONSUMABLE CODE.

target='noctus.dev': scaffold a TOOLKIT tool (module + __init__ register
line + cli.py flag/dispatch + test [+ toolkit_freshness mapping for a
writer]) via libcst — see _scaffold_noctus_dev.py. Dry-run by default;
confirm=True writes. Refuses an existing name.

~5 near-identical leaf files were hand-written this session
(gmail/ads/publish). The tool returns the boilerplate so the agent
fills only the unique adapter call — token-saving + conventions
(mcp-tool-conventions §2/§3) by construction. Returns code (does not
write files) — the agent places it, sidestepping worktree-path/overlay
divergence concerns.
"""
from __future__ import annotations


def scaffold_mcp_tool(
    vendor: str = "",
    service: str = "",
    action: str = "",
    kind: str = "read",
    seed_import: str = "noctusai_lib.integrations.CHANGE_ME",
    *,
    target: str = "connector",
    name: str = "",
    description: str = "",
    tree_dependent: bool = False,
    worktree_path: str | None = None,
    confirm: bool = False,
) -> dict:
    """target='connector': return `{leaf_code, test_code, tool_name}` for
    `<vendor>.<service>.<action>`. `kind='write'` adds the required
    confirm-gate + audit-log shape; `kind='read'` omits it.
    target='noctus.dev': scaffold `noctus.dev.<name>` into the tree at
    `worktree_path` (default: this checkout); `confirm=False` plans."""
    if target == "noctus.dev":
        from pathlib import Path

        from ._scaffold_noctus_dev import default_repo_root, scaffold_noctus_dev

        root = Path(worktree_path) if worktree_path else default_repo_root()
        return scaffold_noctus_dev(
            name, description, kind, tree_dependent, root, confirm)
    if target != "connector":
        return {"ok": False, "error": "target must be 'connector' or 'noctus.dev'"}
    if not (vendor and service and action):
        return {"ok": False, "error": "target='connector' needs vendor, service and action"}
    if kind not in ("read", "write"):
        return {"ok": False, "error": "kind must be 'read' or 'write'"}
    name = f"{vendor}.{service}.{action}"
    Inp = "".join(p.capitalize() for p in action.split("_")) + "Input"
    Out = "".join(p.capitalize() for p in action.split("_")) + "Output"

    confirm_field = (
        '    confirm: bool = Field(default=False, description="WRITE GATE '
        '— must be true; false returns a typed error, no mutation.")\n'
        if kind == "write" else ""
    )
    gate = (
        f'    if not inp.confirm:\n'
        f'        return {Out}(error=typed_error(PermissionError(\n'
        f'            "{name} is a WRITE — re-call with confirm=true."))).model_dump()\n'
        f'    _audit.info("AUDIT {name} confirmed=true")\n'
        if kind == "write" else ""
    )

    leaf = f'''"""{name} — thin _kit-composed wrapper over {seed_import}."""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool
from pydantic import BaseModel, Field

from _kit.errors import typed_error
# from {seed_import} import ...  # TODO: import the adapter/factory

logger = logging.getLogger(__name__)
_audit = logging.getLogger("{vendor}.audit")


class {Inp}(BaseModel):
{confirm_field}    pass  # TODO: declare inputs


class {Out}(BaseModel):
    adapter: str = "fake"
    error: dict | None = None
    # TODO: declare output fields


async def {action}(args: dict) -> dict:
    inp = {Inp}(**args)
{gate}    # TODO: pick Fake vs Real via the seed factory, call it, shape {Out}
    return {Out}().model_dump()


HANDLERS = {{"{name}": {action}}}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [Tool(
        name="{name}",
        description="TODO. {'WRITE — confirm-gated.' if kind == 'write' else 'READ-ONLY.'}",
        inputSchema={Inp}.model_json_schema(),
    )]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
'''

    test = f'''"""Colocated smoke for {name}."""
from __future__ import annotations

import asyncio

from tools import {service}  # noqa: F401  TODO: adjust import path


def test_{action}_registered():
    assert "{name}" in {service}.HANDLERS


def test_{action}_fake_path():
    out = asyncio.run({service}.{action}({{{"'confirm': True" if kind == "write" else ""}}}))
    assert "adapter" in out
'''
    return {
        "ok": True,
        "tool_name": name,
        "leaf_code": leaf,
        "test_code": test,
        "note": "Place leaf at mcp/<vendor>/tools/<service>.py; add to LEAF_MODULES; fill the TODOs.",
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_mcp_tool",
        description=(
            "Scaffold an MCP tool. target='connector' (default): return a "
            "connector-MCP leaf skeleton + test as consumable code "
            "(register/HANDLERS/tool_descriptors + Pydantic In/Out, + "
            "confirm-gate+audit when kind='write'); writes nothing. "
            "target='noctus.dev': scaffold a TOOLKIT tool noctus.dev.<name> "
            "(module with a pure core + executor seam + register, the "
            "__init__ register line, the cli.py flag + dispatch, a seam test, "
            "and for kind='write' the refuse_gate + toolkit_freshness "
            "mapping) via libcst edits to the tree at worktree_path. "
            "Dry-run by default (confirm=False returns the plan + code); "
            "confirm=True writes; an existing name is refused, nothing is "
            "duplicated. Requires name; vendor/service/action are connector-only."
        ),
    )
    def _scaffold_mcp_tool(
        vendor: str = "",
        service: str = "",
        action: str = "",
        kind: str = "read",
        seed_import: str = "noctusai_lib.integrations.CHANGE_ME",
        target: str = "connector",
        name: str = "",
        description: str = "",
        tree_dependent: bool = False,
        worktree_path: str | None = None,
        confirm: bool = False,
    ) -> dict:
        return scaffold_mcp_tool(
            vendor, service, action, kind=kind, seed_import=seed_import,
            target=target, name=name, description=description,
            tree_dependent=tree_dependent, worktree_path=worktree_path, confirm=confirm,
        )


__all__ = ["scaffold_mcp_tool", "register"]
