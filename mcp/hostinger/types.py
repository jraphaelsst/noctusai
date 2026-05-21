"""Pydantic In/Out schemas for the Hostinger connector MCP tools.

One In + one Out per tool (n8n/waha/github/vista shape). Out models
keep the raw Hostinger object as a `dict`/`list` where full fidelity
matters (VM payloads, metrics buckets, action history) — lossy
normalization would hide state. `hostinger` imports as a top-level
package (PyPI-`mcp`-shadow trick, `mcp/_kit/README.md`), so `types.py`
is safe here.

Shapes verified live 2026-05-21 against VM id 1303151:
- `vps.list`   → JSON **array** of VM objects.
- `vps.get`    → single VM **object** (`{id, hostname, state, plan,
  cpus, memory, ipv4[], ...}`).
- `vps.metrics`→ requires `date_from`/`date_to` (ISO 8601; 422 without);
  returns a dict of metric series (`cpu_usage`, ... each
  `{unit, usage:{ts:value}}`).
- `vps.actions`→ `{data:[{id,name,state,created_at,...}], meta:{...}}`.
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

# ─── Shared write/power-gate field (mirrors waha/n8n `_CONFIRM`) ──────────

_CONFIRM = Field(
    default=False,
    description=(
        "WRITE/POWER GATE — must be explicitly true. False/omitted returns "
        "a typed error (status 412) and performs NO side-effect. This is "
        "the confirm-then-execute gate for a state-changing power action "
        "(restart/start/stop) on the VPS."
    ),
)

_VM_ID = Field(
    ...,
    description="Hostinger virtual-machine id (integer, e.g. 1303151).",
)


# ─── hostinger.vps.list ──────────────────────────────────────────────────


class VpsListInput(BaseModel):
    """List all virtual machines on the account. PURE read."""


class VpsListOutput(BaseModel):
    virtual_machines: List[dict] = Field(default_factory=list)
    error: Optional[dict] = None


# ─── hostinger.vps.get ───────────────────────────────────────────────────


class VpsGetInput(BaseModel):
    """Inspect one virtual machine (state running/stopped/..., plan,
    resources, IPs, template). PURE read."""

    vm_id: int = _VM_ID


class VpsGetOutput(BaseModel):
    virtual_machine: Optional[dict] = None
    state: Optional[str] = None
    error: Optional[dict] = None


# ─── hostinger.vps.metrics ───────────────────────────────────────────────


class VpsMetricsInput(BaseModel):
    """Time-series resource metrics for a VM (cpu/memory/disk/network).
    PURE read.

    Hostinger REQUIRES both `date_from` and `date_to` (ISO 8601, e.g.
    `2026-05-20T00:00:00Z`) — omitting them is a 422 upstream, surfaced
    as a typed never-faked error.
    """

    vm_id: int = _VM_ID
    date_from: Optional[str] = Field(
        None,
        description="Window start, ISO 8601 (e.g. 2026-05-20T00:00:00Z). "
        "Required by the API — omit ⇒ upstream 422 (typed, never faked).",
    )
    date_to: Optional[str] = Field(
        None,
        description="Window end, ISO 8601 (e.g. 2026-05-21T00:00:00Z). "
        "Required by the API — omit ⇒ upstream 422 (typed, never faked).",
    )


class VpsMetricsOutput(BaseModel):
    metrics: Optional[dict] = None
    error: Optional[dict] = None


# ─── hostinger.vps.actions ───────────────────────────────────────────────


class VpsActionsInput(BaseModel):
    """Action history for a VM (backups, power actions, ...). PURE read.
    The API paginates: `{data:[...], meta:{...}}`."""

    vm_id: int = _VM_ID


class VpsActionsOutput(BaseModel):
    actions: List[dict] = Field(default_factory=list)
    meta: Optional[dict] = None
    error: Optional[dict] = None


# ─── hostinger.vps.restart / start / stop (WRITE/POWER 🔒) ────────────────


class VpsRestartInput(BaseModel):
    """Restart (reboot) a virtual machine. WRITE/POWER — confirm-gated
    (a reboot interrupts service briefly)."""

    vm_id: int = _VM_ID
    confirm: bool = _CONFIRM


class VpsStartInput(BaseModel):
    """Start (power on) a stopped virtual machine. WRITE/POWER —
    confirm-gated."""

    vm_id: int = _VM_ID
    confirm: bool = _CONFIRM


class VpsStopInput(BaseModel):
    """Stop (power off) a running virtual machine. WRITE/POWER — the
    STRONGEST gate: this TAKES THE SERVER DOWN (every service it hosts
    goes offline until a start). confirm-gated."""

    vm_id: int = _VM_ID
    confirm: bool = _CONFIRM


class VpsActionOutput(BaseModel):
    vm_id: Optional[int] = None
    ok: bool = False
    action: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[dict] = None


# ─── hostinger.diagnostics.connection_status ─────────────────────────────


class ConnectionStatusInput(BaseModel):
    """Introspect the Hostinger dependency. PURE read.

    Gated-capability honesty: distinguishes not-configured (no token) vs
    host-down (network failure / Cloudflare unreachable) vs
    token-rejected (401/403) vs ok (200) — so the operator gets a real
    tri/quad-state signal rather than a conflated failure.
    """


class ConnectionStatusOutput(BaseModel):
    configured: bool = False
    root: Optional[str] = None
    reachable: Optional[bool] = None
    authenticated: Optional[bool] = None
    vm_count: Optional[int] = None
    error: Optional[dict] = None


__all__ = [
    "VpsListInput",
    "VpsListOutput",
    "VpsGetInput",
    "VpsGetOutput",
    "VpsMetricsInput",
    "VpsMetricsOutput",
    "VpsActionsInput",
    "VpsActionsOutput",
    "VpsRestartInput",
    "VpsStartInput",
    "VpsStopInput",
    "VpsActionOutput",
    "ConnectionStatusInput",
    "ConnectionStatusOutput",
]
