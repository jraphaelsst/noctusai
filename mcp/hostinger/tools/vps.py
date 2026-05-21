"""hostinger.vps.* tools — VPS lifecycle + telemetry.

Reads (no gate): list / get / metrics / actions.
Writes/power (confirm-gated): restart / start / stop. `stop` is the
STRONGEST gate — it takes the server down (every service it hosts goes
offline until a start).

Every tool routes through the single `api.request_json` HTTP seam
(tests patch `hostinger.api.request_json`). API failure ⇒ a typed-error
envelope, never a fabricated success. `api` is invoked via the module
so `patch("hostinger.api.request_json")` is observed.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    VpsActionOutput,
    VpsActionsInput,
    VpsActionsOutput,
    VpsGetInput,
    VpsGetOutput,
    VpsListInput,
    VpsListOutput,
    VpsMetricsInput,
    VpsMetricsOutput,
    VpsRestartInput,
    VpsStartInput,
    VpsStopInput,
)

logger = logging.getLogger(__name__)

_VPS_BASE = "/api/vps/v1/virtual-machines"


def _ctx() -> dict:
    s = get_settings()
    return {
        "api_token": s.api_token or "",
        "base_url": s.base_url or "",
        "timeout": s.timeout_seconds,
    }


# ─── Reads ───────────────────────────────────────────────────────────────


async def vps_list(args: dict) -> dict:
    VpsListInput(**args)
    try:
        data = api.request_json("GET", _VPS_BASE, **_ctx())
    except api.HostingerApiError as e:
        return VpsListOutput(error=typed_error(e)).model_dump()
    return VpsListOutput(
        virtual_machines=data if isinstance(data, list) else []
    ).model_dump()


async def vps_get(args: dict) -> dict:
    inp = VpsGetInput(**args)
    try:
        data = api.request_json("GET", f"{_VPS_BASE}/{inp.vm_id}", **_ctx())
    except api.HostingerApiError as e:
        return VpsGetOutput(error=typed_error(e)).model_dump()
    return VpsGetOutput(
        virtual_machine=data if isinstance(data, dict) else None,
        state=(data or {}).get("state") if isinstance(data, dict) else None,
    ).model_dump()


async def vps_metrics(args: dict) -> dict:
    inp = VpsMetricsInput(**args)
    try:
        data = api.request_json(
            "GET", f"{_VPS_BASE}/{inp.vm_id}/metrics",
            params={"date_from": inp.date_from, "date_to": inp.date_to},
            **_ctx(),
        )
    except api.HostingerApiError as e:
        return VpsMetricsOutput(error=typed_error(e)).model_dump()
    return VpsMetricsOutput(
        metrics=data if isinstance(data, dict) else {"value": data}
    ).model_dump()


async def vps_actions(args: dict) -> dict:
    inp = VpsActionsInput(**args)
    try:
        data = api.request_json(
            "GET", f"{_VPS_BASE}/{inp.vm_id}/actions", **_ctx()
        )
    except api.HostingerApiError as e:
        return VpsActionsOutput(error=typed_error(e)).model_dump()
    # API wraps as {data:[...], meta:{...}}; tolerate a bare list too.
    if isinstance(data, dict):
        actions = data.get("data") if isinstance(data.get("data"), list) else []
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else None
    elif isinstance(data, list):
        actions, meta = data, None
    else:
        actions, meta = [], None
    return VpsActionsOutput(actions=actions, meta=meta).model_dump()


# ─── Writes / power (confirm-gated) ──────────────────────────────────────


async def _power(vm_id: int, verb: str) -> dict:
    try:
        data = api.request_json(
            "POST", f"{_VPS_BASE}/{vm_id}/{verb}", **_ctx()
        )
    except api.HostingerApiError as e:
        return VpsActionOutput(
            vm_id=vm_id, action=verb, error=typed_error(e)
        ).model_dump()
    return VpsActionOutput(
        vm_id=vm_id, ok=True, action=verb, result=data
    ).model_dump()


async def vps_restart(args: dict) -> dict:
    inp = VpsRestartInput(**args)
    if not inp.confirm:
        return VpsActionOutput(
            vm_id=inp.vm_id, action="restart",
            error=typed_error(api.ConfirmationRequiredError(
                "hostinger.vps.restart", "reboots the VPS (brief downtime)"
            )),
        ).model_dump()
    return await _power(inp.vm_id, "restart")


async def vps_start(args: dict) -> dict:
    inp = VpsStartInput(**args)
    if not inp.confirm:
        return VpsActionOutput(
            vm_id=inp.vm_id, action="start",
            error=typed_error(api.ConfirmationRequiredError(
                "hostinger.vps.start", "powers the VPS on"
            )),
        ).model_dump()
    return await _power(inp.vm_id, "start")


async def vps_stop(args: dict) -> dict:
    inp = VpsStopInput(**args)
    if not inp.confirm:
        return VpsActionOutput(
            vm_id=inp.vm_id, action="stop",
            error=typed_error(api.ConfirmationRequiredError(
                "hostinger.vps.stop",
                "TAKES THE SERVER DOWN — every service it hosts goes "
                "offline until a start",
            )),
        ).model_dump()
    return await _power(inp.vm_id, "stop")


HANDLERS = {
    "hostinger.vps.list": vps_list,
    "hostinger.vps.get": vps_get,
    "hostinger.vps.metrics": vps_metrics,
    "hostinger.vps.actions": vps_actions,
    "hostinger.vps.restart": vps_restart,
    "hostinger.vps.start": vps_start,
    "hostinger.vps.stop": vps_stop,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="hostinger.vps.list",
             description="List all virtual machines on the account. "
             "READ-ONLY.",
             inputSchema=VpsListInput.model_json_schema()),
        Tool(name="hostinger.vps.get",
             description="Inspect one VM — state/plan/resources/IPs/"
             "template. READ-ONLY.",
             inputSchema=VpsGetInput.model_json_schema()),
        Tool(name="hostinger.vps.metrics",
             description="Time-series resource metrics (cpu/mem/disk/net) "
             "for a VM. Requires date_from + date_to (ISO 8601). "
             "READ-ONLY.",
             inputSchema=VpsMetricsInput.model_json_schema()),
        Tool(name="hostinger.vps.actions",
             description="Action history for a VM (backups, power actions). "
             "READ-ONLY.",
             inputSchema=VpsActionsInput.model_json_schema()),
        Tool(name="hostinger.vps.restart",
             description="Reboot a VM (brief downtime). WRITE/POWER — "
             "confirm-gated (412).",
             inputSchema=VpsRestartInput.model_json_schema()),
        Tool(name="hostinger.vps.start",
             description="Power a stopped VM on. WRITE/POWER — "
             "confirm-gated (412).",
             inputSchema=VpsStartInput.model_json_schema()),
        Tool(name="hostinger.vps.stop",
             description="Power a running VM off — STRONGEST gate: TAKES "
             "THE SERVER DOWN (all hosted services offline until a "
             "start). WRITE/POWER — confirm-gated (412).",
             inputSchema=VpsStopInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
