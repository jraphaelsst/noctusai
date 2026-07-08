"""Pydantic In/Out schemas for the Cloudflare connector MCP tools.

One In + one Out per tool (n8n/waha/hostinger/github/vista shape). Out
models keep the raw Cloudflare object as a `dict`/`list` where full
fidelity matters (zone payloads, DNS records, tunnel objects, ingress
config) — lossy normalization would hide state. `cloudflare` imports as
a top-level package (PyPI-`mcp`-shadow trick, `mcp/_kit/README.md`), so
`types.py` is safe here.

Shapes verified 2026-05-21 against the official Cloudflare API v4 docs
(via `search_cloudflare_documentation` + the public reference) — there
is no live token yet, so these are documented-shape Pydantic schemas;
LIVE validation is deferred until the user pastes a scoped token:
- zones.list  → array of zone objects (envelope `result`, paginated).
- zones.get   → single zone object.
- zones.create→ created zone object (body {name, account:{id}, type}).
- dns.list_records → array of record objects.
- dns.get/create/update_record → single record object
  ({id, type, name, content, ttl, proxied, ...}).
- dns.delete_record → `result:{id}` (envelope result on success).
- tunnel.list → array of cfd_tunnel objects.
- tunnel.get  → single tunnel object ({id, name, status, connections,...}).
- tunnel.create → created tunnel object (incl. `token`, body
  {name, config_src:"cloudflare"}).
- tunnel.delete → `result` tunnel object (deleted_at set).
- tunnel.get_config / update_config → config object {config:{ingress:[...]}}.
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

# ─── Shared write-gate field (mirrors hostinger/waha/n8n `_CONFIRM`) ──────

_CONFIRM = Field(
    default=False,
    description=(
        "WRITE GATE — must be explicitly true. False/omitted returns a "
        "typed error (status 412) and performs NO side-effect. This is "
        "the confirm-then-execute gate for a state-changing Cloudflare "
        "action (create/update/delete a zone, DNS record, or tunnel)."
    ),
)

_ZONE_ID = Field(
    ...,
    description="Cloudflare zone id (32-hex string identifying a domain).",
)

_TUNNEL_ID = Field(
    ...,
    description="Cloudflare Tunnel (cfd_tunnel) id (uuid).",
)

_RECORD_ID = Field(
    ...,
    description="Cloudflare DNS record id (within the zone).",
)


# ═══════════════════════════════════════════════════════════════════════
# ZONES
# ═══════════════════════════════════════════════════════════════════════


class ZonesListInput(BaseModel):
    """List zones (domains) on the account. PURE read.

    Optional `name` filters to an exact zone name (Cloudflare's
    `?name=` query)."""

    name: Optional[str] = Field(
        None,
        description="Exact zone name filter (e.g. example.com). Optional.",
    )


class ZonesListOutput(BaseModel):
    zones: List[dict] = Field(default_factory=list)
    result_info: Optional[dict] = None
    error: Optional[dict] = None


class ZonesGetInput(BaseModel):
    """Inspect one zone — status, name servers, plan, account. PURE read."""

    zone_id: str = _ZONE_ID


class ZonesGetOutput(BaseModel):
    zone: Optional[dict] = None
    error: Optional[dict] = None


class ZonesCreateInput(BaseModel):
    """Create (onboard) a new zone (domain) on the account. WRITE —
    confirm-gated (adds a billable domain + changes account state).

    Cloudflare requires `name` + the owning `account` id; `type` defaults
    to `full` (Cloudflare authoritative DNS). Use `partial` for a CNAME
    setup. The account id defaults to the connector's configured
    `CLOUDFLARE_ACCOUNT_ID` when not passed explicitly.
    """

    name: str = Field(..., description="The domain name (e.g. example.com).")
    account_id: Optional[str] = Field(
        None,
        description="Owning account id. Defaults to the connector's "
        "configured CLOUDFLARE_ACCOUNT_ID when omitted.",
    )
    type: str = Field(
        "full",
        description="Zone type: 'full' (Cloudflare authoritative DNS, "
        "default) or 'partial' (CNAME setup).",
    )
    confirm: bool = _CONFIRM


class ZonesCreateOutput(BaseModel):
    zone: Optional[dict] = None
    ok: bool = False
    error: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════
# DNS RECORDS
# ═══════════════════════════════════════════════════════════════════════


class DnsListRecordsInput(BaseModel):
    """List DNS records in a zone. PURE read. Optional `type`/`name`
    pass-through filters (Cloudflare's `?type=&name=`)."""

    zone_id: str = _ZONE_ID
    type: Optional[str] = Field(
        None,
        description="Filter by record type (A/AAAA/CNAME/TXT/MX/...). "
        "Optional.",
    )
    name: Optional[str] = Field(
        None,
        description="Filter by record name (FQDN). Optional.",
    )


class DnsListRecordsOutput(BaseModel):
    records: List[dict] = Field(default_factory=list)
    result_info: Optional[dict] = None
    error: Optional[dict] = None


class DnsGetRecordInput(BaseModel):
    """Inspect one DNS record. PURE read."""

    zone_id: str = _ZONE_ID
    record_id: str = _RECORD_ID


class DnsRecordOutput(BaseModel):
    record: Optional[dict] = None
    ok: bool = False
    error: Optional[dict] = None


class DnsCreateRecordInput(BaseModel):
    """Create a DNS record in a zone. WRITE — confirm-gated (publishes a
    new public DNS record).

    `type`/`name`/`content` are required; `ttl` (1 = automatic) and
    `proxied` (orange-cloud) are optional. `priority` is required for MX/
    SRV — pass it via `priority`.
    """

    zone_id: str = _ZONE_ID
    type: str = Field(..., description="Record type (A/AAAA/CNAME/TXT/MX/...).")
    name: str = Field(..., description="Record name (FQDN, e.g. www.example.com).")
    content: str = Field(..., description="Record content (IP / target / value).")
    ttl: Optional[int] = Field(
        None,
        description="TTL in seconds; 1 = automatic. Optional (Cloudflare "
        "defaults to automatic).",
    )
    proxied: Optional[bool] = Field(
        None,
        description="Proxy status (orange-cloud). Optional; only valid for "
        "proxiable types (A/AAAA/CNAME).",
    )
    priority: Optional[int] = Field(
        None,
        description="Priority — required for MX/SRV records. Optional "
        "otherwise.",
    )
    confirm: bool = _CONFIRM


class DnsUpdateRecordInput(BaseModel):
    """Update (PATCH) a DNS record. WRITE — confirm-gated (changes a live
    public DNS record). Only the fields you pass are changed (PATCH
    semantics)."""

    zone_id: str = _ZONE_ID
    record_id: str = _RECORD_ID
    type: Optional[str] = Field(None, description="New record type. Optional.")
    name: Optional[str] = Field(None, description="New record name. Optional.")
    content: Optional[str] = Field(None, description="New content. Optional.")
    ttl: Optional[int] = Field(None, description="New TTL (1=auto). Optional.")
    proxied: Optional[bool] = Field(
        None, description="New proxy status. Optional."
    )
    priority: Optional[int] = Field(
        None, description="New priority (MX/SRV). Optional."
    )
    confirm: bool = _CONFIRM


class DnsDeleteRecordInput(BaseModel):
    """Delete a DNS record. WRITE — confirm-gated, STRONGEST: this is
    OUTWARD-FACING and IRREVERSIBLE — the public DNS record is removed
    immediately (anything resolving through it breaks) and cannot be
    undone (you must re-create it)."""

    zone_id: str = _ZONE_ID
    record_id: str = _RECORD_ID
    confirm: bool = _CONFIRM


# ═══════════════════════════════════════════════════════════════════════
# TUNNEL (cfd_tunnel — account-scoped)
# ═══════════════════════════════════════════════════════════════════════


class TunnelListInput(BaseModel):
    """List Cloudflare Tunnels (cfd_tunnel) on the account. PURE read.
    Account-scoped — needs the connector's CLOUDFLARE_ACCOUNT_ID."""


class TunnelListOutput(BaseModel):
    tunnels: List[dict] = Field(default_factory=list)
    result_info: Optional[dict] = None
    error: Optional[dict] = None


class TunnelGetInput(BaseModel):
    """Inspect one tunnel — status, connections, type. PURE read.
    Account-scoped."""

    tunnel_id: str = _TUNNEL_ID


class TunnelGetOutput(BaseModel):
    tunnel: Optional[dict] = None
    status: Optional[str] = None
    error: Optional[dict] = None


class TunnelCreateInput(BaseModel):
    """Create a remotely-managed Cloudflare Tunnel. WRITE — confirm-gated.
    Account-scoped.

    The created tunnel's response includes the `token` used to run
    `cloudflared` — treat it as a secret. `config_src` defaults to
    `cloudflare` (remotely-managed; configure ingress via
    `tunnel.update_config`).
    """

    name: str = Field(..., description="Tunnel name (e.g. api-tunnel).")
    config_src: str = Field(
        "cloudflare",
        description="Configuration source: 'cloudflare' (remotely-managed, "
        "default) or 'local'.",
    )
    confirm: bool = _CONFIRM


class TunnelCreateOutput(BaseModel):
    tunnel: Optional[dict] = None
    ok: bool = False
    error: Optional[dict] = None


class TunnelDeleteInput(BaseModel):
    """Delete a Cloudflare Tunnel. WRITE — confirm-gated, STRONGEST:
    IRREVERSIBLE — the tunnel and its credentials are destroyed (any
    `cloudflared` running it stops serving; routes through it break).
    Account-scoped. Delete the tunnel's connections / DNS routes first
    if you need a clean teardown."""

    tunnel_id: str = _TUNNEL_ID
    confirm: bool = _CONFIRM


class TunnelDeleteOutput(BaseModel):
    tunnel_id: Optional[str] = None
    ok: bool = False
    result: Optional[Any] = None
    error: Optional[dict] = None


class TunnelGetConfigInput(BaseModel):
    """Read a tunnel's ingress configuration (the public-hostname →
    service routing rules). PURE read. Account-scoped."""

    tunnel_id: str = _TUNNEL_ID


class TunnelConfigOutput(BaseModel):
    config: Optional[dict] = None
    ok: bool = False
    error: Optional[dict] = None


class TunnelUpdateConfigInput(BaseModel):
    """Replace a tunnel's ingress configuration. WRITE — confirm-gated
    (PUT — replaces the whole ingress rule set). Account-scoped.

    `ingress` is the full ordered list of rules; Cloudflare REQUIRES a
    catch-all rule (one with only a `service`, e.g.
    `{"service":"http_status:404"}`) as the LAST entry. ALWAYS
    `tunnel.get_config` first and keep that as a rollback snapshot — this
    is a full replace, not a merge. Pass the rules as `ingress`; the
    handler wraps them in `{config:{ingress:[...]}}`.
    """

    tunnel_id: str = _TUNNEL_ID
    ingress: List[dict] = Field(
        ...,
        description="Ordered ingress rules (full replace). Each rule is "
        "{hostname?, service, originRequest?}; the LAST must be a catch-all "
        "(service-only, e.g. {\"service\":\"http_status:404\"}).",
    )
    confirm: bool = _CONFIRM


# ═══════════════════════════════════════════════════════════════════════
# DIAGNOSTICS
# ═══════════════════════════════════════════════════════════════════════


class ConnectionStatusInput(BaseModel):
    """Introspect the Cloudflare dependency. PURE read.

    Gated-capability honesty: distinguishes not-configured (no token) vs
    host-down (network failure) vs token-rejected (401 / success:false)
    vs ok (token verified) — so the operator gets a real quad-state
    signal rather than a conflated failure. Probes `GET
    /user/tokens/verify` (the canonical token-validity endpoint).
    """


class ConnectionStatusOutput(BaseModel):
    configured: bool = False
    root: Optional[str] = None
    reachable: Optional[bool] = None
    authenticated: Optional[bool] = None
    token_status: Optional[str] = None
    account_id_present: bool = False
    error: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════════════════════════════


class CachePurgeInput(BaseModel):
    """Purge the Cloudflare edge cache for a zone.

    Confirm-gated: purging is a production edge action (a brief cache-cold
    period as assets re-fetch from origin). Purge by explicit URL list
    (``files``) — the safe default — or the whole zone (``purge_everything``,
    the STRONGEST form). Requires the API token to carry the
    ``Zone > Cache Purge > Purge`` permission.
    """

    zone: str = Field(
        default="noctusai.com",
        description="Zone (domain) name to purge; resolved to a zone id. "
        "Pass `zone_id` directly to skip the lookup.",
    )
    zone_id: Optional[str] = Field(
        default=None,
        description="Zone id (32-hex). When set, wins over `zone` (no lookup).",
    )
    files: Optional[List[str]] = Field(
        default=None,
        description="Absolute URLs to purge (e.g. "
        "'https://erp.noctusai.com/sw.js'). Up to 30 per call. Ignored when "
        "`purge_everything` is true.",
    )
    purge_everything: bool = Field(
        default=False,
        description="Purge the ENTIRE zone cache (STRONGEST). Mutually "
        "exclusive with `files`.",
    )
    confirm: bool = _CONFIRM


class CachePurgeOutput(BaseModel):
    ok: bool = False
    zone_id: Optional[str] = None
    purged_files: Optional[List[str]] = None
    purged_everything: bool = False
    error: Optional[dict] = None


__all__ = [
    # zones
    "ZonesListInput",
    "ZonesListOutput",
    "ZonesGetInput",
    "ZonesGetOutput",
    "ZonesCreateInput",
    "ZonesCreateOutput",
    # dns
    "DnsListRecordsInput",
    "DnsListRecordsOutput",
    "DnsGetRecordInput",
    "DnsRecordOutput",
    "DnsCreateRecordInput",
    "DnsUpdateRecordInput",
    "DnsDeleteRecordInput",
    # tunnel
    "TunnelListInput",
    "TunnelListOutput",
    "TunnelGetInput",
    "TunnelGetOutput",
    "TunnelCreateInput",
    "TunnelCreateOutput",
    "TunnelDeleteInput",
    "TunnelDeleteOutput",
    "TunnelGetConfigInput",
    "TunnelConfigOutput",
    "TunnelUpdateConfigInput",
    # diagnostics
    "ConnectionStatusInput",
    "ConnectionStatusOutput",
    # cache
    "CachePurgeInput",
    "CachePurgeOutput",
]
