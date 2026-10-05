"""`telegram.diagnostics.*` — setup state + identity. Never shows a phone number."""
from __future__ import annotations

from pathlib import Path

from mcp.server import Server
from mcp.types import Tool

from .. import client
from ..settings import get_settings
from ..types import NoArgs
from ._run import run_with_gateway


async def connection_status(args: dict) -> dict:
    NoArgs(**args)
    s = get_settings()
    session_present = Path(s.session_file).exists()
    out = {
        "configured": s.configured,
        "has_api_id": bool(s.api_id),
        "has_api_hash": bool(s.api_hash),
        "session_present": session_present,
        "authorized": False,
        "next_step": None,
    }
    if not s.configured:
        out["next_step"] = "set TELEGRAM_API_ID and TELEGRAM_API_HASH in mcp/telegram/.env"
    elif not session_present and client._client_override is None:
        out["next_step"] = "run: mcp/noctusai/.venv/bin/python mcp/telegram/login.py"
    else:
        async def _auth(gw):
            out["authorized"] = bool(await gw.is_authorized())
            if not out["authorized"]:
                out["next_step"] = "session not authorized — re-run mcp/telegram/login.py"
            return out
        out = await run_with_gateway(_auth, **out)
    out["ok"] = bool(out.get("configured") and out.get("authorized"))
    return out


async def me(args: dict) -> dict:
    NoArgs(**args)

    async def _me(gw):
        return {"me": await gw.get_me()}

    return await run_with_gateway(_me, me=None)


HANDLERS = {
    "telegram.diagnostics.connection_status": connection_status,
    "telegram.diagnostics.me": me,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="telegram.diagnostics.connection_status",
            description="Are TELEGRAM_API_ID/HASH configured and is the saved session "
            "logged in? READ, no API calls beyond the authorization check.",
            inputSchema=NoArgs.model_json_schema(),
        ),
        Tool(
            name="telegram.diagnostics.me",
            description="The logged-in account (id, username, name; no phone). READ.",
            inputSchema=NoArgs.model_json_schema(),
        ),
    ]


__all__ = ["HANDLERS", "register", "tool_descriptors"]
