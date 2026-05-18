"""noctus.dev.scaffold_mcp_tool — emit a connector-MCP leaf skeleton
(register/HANDLERS/tool_descriptors + Pydantic In/Out + confirm-gate+
audit if write) as CONSUMABLE CODE.

~5 near-identical leaf files were hand-written this session
(gmail/ads/publish). The tool returns the boilerplate so the agent
fills only the unique adapter call — token-saving + conventions
(mcp-tool-conventions §2/§3) by construction. Returns code (does not
write files) — the agent places it, sidestepping worktree-path/overlay
divergence concerns.
"""
from __future__ import annotations


def scaffold_mcp_tool(
    vendor: str,
    service: str,
    action: str,
    kind: str = "read",
    seed_import: str = "noctusai_lib.integrations.CHANGE_ME",
) -> dict:
    """Return `{leaf_code, test_code, tool_name}` for
    `<vendor>.<service>.<action>`. `kind='write'` adds the required
    confirm-gate + audit-log shape; `kind='read'` omits it."""
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
            "Return a connector-MCP leaf skeleton + test as consumable "
            "code (register/HANDLERS/tool_descriptors + Pydantic In/Out, "
            "+ confirm-gate+audit when kind='write'). Conventions-by-"
            "construction; agent fills only the adapter call. Does not "
            "write files — returns code to place."
        ),
    )
    def _scaffold_mcp_tool(
        vendor: str,
        service: str,
        action: str,
        kind: str = "read",
        seed_import: str = "noctusai_lib.integrations.CHANGE_ME",
    ) -> dict:
        return scaffold_mcp_tool(vendor, service, action, kind=kind, seed_import=seed_import)


__all__ = ["scaffold_mcp_tool", "register"]
