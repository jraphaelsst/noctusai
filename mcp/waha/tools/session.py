"""waha.session.* tools — WhatsApp session lifecycle.

Reads (no gate): list / get / me.
Writes (confirm-gated): start / stop / restart; logout is also
hard-to-reverse (drops the WhatsApp pairing).

Every tool routes through the single `api.request_json` HTTP seam
(tests patch `waha.api.request_json`). API failure ⇒ a typed-error
envelope, never a fabricated success. `api` is invoked via the module
so `patch("waha.api.request_json")` is observed.
"""
from __future__ import annotations

import logging
from typing import Optional

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    SessionActionOutput,
    SessionGetInput,
    SessionGetOutput,
    SessionListInput,
    SessionListOutput,
    SessionLogoutInput,
    SessionMeInput,
    SessionMeOutput,
    SessionRestartInput,
    SessionStartInput,
    SessionStopInput,
)

logger = logging.getLogger(__name__)


def _ctx() -> dict:
    s = get_settings()
    return {
        "base_url": s.base_url or "",
        "api_key": s.api_key or "",
        "timeout": s.timeout_seconds,
    }


def _sess(name: Optional[str]) -> str:
    return name or get_settings().default_session


# ─── Reads ───────────────────────────────────────────────────────────────


async def session_list(args: dict) -> dict:
    inp = SessionListInput(**args)
    try:
        data = api.request_json(
            "GET", "/api/sessions",
            params={"all": "true" if inp.all else "false"}, **_ctx(),
        )
    except api.WahaApiError as e:
        return SessionListOutput(error=typed_error(e)).model_dump()
    return SessionListOutput(
        sessions=data if isinstance(data, list) else []
    ).model_dump()


async def session_get(args: dict) -> dict:
    inp = SessionGetInput(**args)
    name = _sess(inp.session)
    try:
        data = api.request_json("GET", f"/api/sessions/{name}", **_ctx())
    except api.WahaApiError as e:
        return SessionGetOutput(error=typed_error(e)).model_dump()
    return SessionGetOutput(
        session=data if isinstance(data, dict) else None,
        status=(data or {}).get("status") if isinstance(data, dict) else None,
    ).model_dump()


async def session_me(args: dict) -> dict:
    inp = SessionMeInput(**args)
    name = _sess(inp.session)
    try:
        data = api.request_json("GET", f"/api/sessions/{name}/me", **_ctx())
    except api.WahaApiError as e:
        return SessionMeOutput(error=typed_error(e)).model_dump()
    return SessionMeOutput(
        me=data if isinstance(data, dict) else None
    ).model_dump()


# ─── Writes (confirm-gated) ──────────────────────────────────────────────


async def _action(name: str, verb: str) -> dict:
    try:
        data = api.request_json(
            "POST", f"/api/sessions/{name}/{verb}", **_ctx()
        )
    except api.WahaApiError as e:
        return SessionActionOutput(
            session=name, error=typed_error(e)
        ).model_dump()
    return SessionActionOutput(
        session=name,
        ok=True,
        status=(data or {}).get("status") if isinstance(data, dict) else None,
        result=data,
    ).model_dump()


async def session_start(args: dict) -> dict:
    inp = SessionStartInput(**args)
    if not inp.confirm:
        return SessionActionOutput(
            error=typed_error(api.ConfirmationRequiredError("waha.session.start"))
        ).model_dump()
    return await _action(_sess(inp.session), "start")


async def session_stop(args: dict) -> dict:
    inp = SessionStopInput(**args)
    if not inp.confirm:
        return SessionActionOutput(
            error=typed_error(api.ConfirmationRequiredError("waha.session.stop"))
        ).model_dump()
    return await _action(_sess(inp.session), "stop")


async def session_restart(args: dict) -> dict:
    inp = SessionRestartInput(**args)
    if not inp.confirm:
        return SessionActionOutput(
            error=typed_error(
                api.ConfirmationRequiredError("waha.session.restart")
            )
        ).model_dump()
    return await _action(_sess(inp.session), "restart")


async def session_logout(args: dict) -> dict:
    inp = SessionLogoutInput(**args)
    if not inp.confirm:
        return SessionActionOutput(
            error=typed_error(
                api.ConfirmationRequiredError("waha.session.logout")
            )
        ).model_dump()
    return await _action(_sess(inp.session), "logout")


HANDLERS = {
    "waha.session.list": session_list,
    "waha.session.get": session_get,
    "waha.session.me": session_me,
    "waha.session.start": session_start,
    "waha.session.stop": session_stop,
    "waha.session.restart": session_restart,
    "waha.session.logout": session_logout,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="waha.session.list",
             description="List WhatsApp sessions (incl. stopped). "
             "READ-ONLY.",
             inputSchema=SessionListInput.model_json_schema()),
        Tool(name="waha.session.get",
             description="Inspect one session — status WORKING/STARTING/"
             "SCAN_QR_CODE/STOPPED/FAILED. READ-ONLY.",
             inputSchema=SessionGetInput.model_json_schema()),
        Tool(name="waha.session.me",
             description="The connected WhatsApp account for a session. "
             "READ-ONLY.",
             inputSchema=SessionMeInput.model_json_schema()),
        Tool(name="waha.session.start",
             description="Start a session. WRITE — confirm-gated (412).",
             inputSchema=SessionStartInput.model_json_schema()),
        Tool(name="waha.session.stop",
             description="Stop a session. WRITE — confirm-gated (412).",
             inputSchema=SessionStopInput.model_json_schema()),
        Tool(name="waha.session.restart",
             description="Restart a session — the fix for a stuck/STOPPED "
             "worker. WRITE — confirm-gated (412).",
             inputSchema=SessionRestartInput.model_json_schema()),
        Tool(name="waha.session.logout",
             description="Log the session out of WhatsApp. WRITE / "
             "HARD-TO-REVERSE (re-pair needs a QR scan) — confirm-gated.",
             inputSchema=SessionLogoutInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
