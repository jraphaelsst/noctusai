"""cloudflare.dns.* tools — DNS record list / inspect / create / update / delete.

Reads (no gate): list_records / get_record.
Writes (confirm-gated): create_record / update_record / delete_record.
`delete_record` is the STRONGEST gate — it is OUTWARD-FACING and
IRREVERSIBLE (the public DNS record is removed immediately; anything
resolving through it breaks; you must re-create it to undo).

Every tool routes through the single `api.request_json` /
`api.request_envelope` HTTP seam (tests patch
`cloudflare.api.request_json` / `request_envelope`). API failure ⇒ a
typed-error envelope, never a fabricated success.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    DnsCreateRecordInput,
    DnsDeleteRecordInput,
    DnsGetRecordInput,
    DnsListRecordsInput,
    DnsListRecordsOutput,
    DnsRecordOutput,
    DnsUpdateRecordInput,
)

logger = logging.getLogger(__name__)


def _ctx() -> dict:
    s = get_settings()
    return {
        "api_token": s.api_token or "",
        "base_url": s.base_url or "",
        "timeout": s.timeout_seconds,
    }


def _records_base(zone_id: str) -> str:
    return f"/zones/{zone_id}/dns_records"


def _record_body(inp) -> dict:
    """Assemble the DNS record request body from the non-None fields the
    caller passed (PATCH-friendly — only present fields are sent)."""
    body: dict = {}
    for key in ("type", "name", "content", "ttl", "proxied", "priority"):
        val = getattr(inp, key, None)
        if val is not None:
            body[key] = val
    return body


# ─── Reads ───────────────────────────────────────────────────────────────


async def dns_list_records(args: dict) -> dict:
    inp = DnsListRecordsInput(**args)
    try:
        env = api.request_envelope(
            "GET", _records_base(inp.zone_id),
            params={"type": inp.type, "name": inp.name}, **_ctx(),
        )
    except api.CloudflareApiError as e:
        return DnsListRecordsOutput(error=typed_error(e)).model_dump()
    result = env.get("result")
    return DnsListRecordsOutput(
        records=result if isinstance(result, list) else [],
        result_info=env.get("result_info")
        if isinstance(env.get("result_info"), dict)
        else None,
    ).model_dump()


async def dns_get_record(args: dict) -> dict:
    inp = DnsGetRecordInput(**args)
    try:
        data = api.request_json(
            "GET", f"{_records_base(inp.zone_id)}/{inp.record_id}", **_ctx()
        )
    except api.CloudflareApiError as e:
        return DnsRecordOutput(error=typed_error(e)).model_dump()
    return DnsRecordOutput(
        record=data if isinstance(data, dict) else None, ok=True
    ).model_dump()


# ─── Writes (confirm-gated) ──────────────────────────────────────────────


async def dns_create_record(args: dict) -> dict:
    inp = DnsCreateRecordInput(**args)
    if not inp.confirm:
        return DnsRecordOutput(
            error=typed_error(api.ConfirmationRequiredError(
                "cloudflare.dns.create_record",
                f"publishes a new public {inp.type} DNS record "
                f"({inp.name} → {inp.content})",
            )),
        ).model_dump()
    try:
        data = api.request_json(
            "POST", _records_base(inp.zone_id), body=_record_body(inp), **_ctx()
        )
    except api.CloudflareApiError as e:
        return DnsRecordOutput(error=typed_error(e)).model_dump()
    return DnsRecordOutput(
        record=data if isinstance(data, dict) else None, ok=True
    ).model_dump()


async def dns_update_record(args: dict) -> dict:
    inp = DnsUpdateRecordInput(**args)
    if not inp.confirm:
        return DnsRecordOutput(
            error=typed_error(api.ConfirmationRequiredError(
                "cloudflare.dns.update_record",
                "changes a live public DNS record (resolution updates "
                "globally)",
            )),
        ).model_dump()
    try:
        data = api.request_json(
            "PATCH", f"{_records_base(inp.zone_id)}/{inp.record_id}",
            body=_record_body(inp), **_ctx(),
        )
    except api.CloudflareApiError as e:
        return DnsRecordOutput(error=typed_error(e)).model_dump()
    return DnsRecordOutput(
        record=data if isinstance(data, dict) else None, ok=True
    ).model_dump()


async def dns_delete_record(args: dict) -> dict:
    inp = DnsDeleteRecordInput(**args)
    if not inp.confirm:
        return DnsRecordOutput(
            error=typed_error(api.ConfirmationRequiredError(
                "cloudflare.dns.delete_record",
                "STRONGEST GATE — IRREVERSIBLE: removes a live public DNS "
                "record immediately (anything resolving through it breaks; "
                "you must re-create it to undo)",
            )),
        ).model_dump()
    try:
        data = api.request_json(
            "DELETE", f"{_records_base(inp.zone_id)}/{inp.record_id}", **_ctx()
        )
    except api.CloudflareApiError as e:
        return DnsRecordOutput(error=typed_error(e)).model_dump()
    # Cloudflare DELETE returns `result:{id}` on success.
    return DnsRecordOutput(
        record=data if isinstance(data, dict) else None, ok=True
    ).model_dump()


HANDLERS = {
    "cloudflare.dns.list_records": dns_list_records,
    "cloudflare.dns.get_record": dns_get_record,
    "cloudflare.dns.create_record": dns_create_record,
    "cloudflare.dns.update_record": dns_update_record,
    "cloudflare.dns.delete_record": dns_delete_record,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="cloudflare.dns.list_records",
             description="List DNS records in a zone; optional type/name "
             "filters. READ-ONLY.",
             inputSchema=DnsListRecordsInput.model_json_schema()),
        Tool(name="cloudflare.dns.get_record",
             description="Inspect one DNS record. READ-ONLY.",
             inputSchema=DnsGetRecordInput.model_json_schema()),
        Tool(name="cloudflare.dns.create_record",
             description="Publish a new DNS record in a zone. WRITE — "
             "confirm-gated (412).",
             inputSchema=DnsCreateRecordInput.model_json_schema()),
        Tool(name="cloudflare.dns.update_record",
             description="Update (PATCH) a live DNS record. WRITE — "
             "confirm-gated (412).",
             inputSchema=DnsUpdateRecordInput.model_json_schema()),
        Tool(name="cloudflare.dns.delete_record",
             description="Delete a DNS record — STRONGEST gate: "
             "OUTWARD-FACING / IRREVERSIBLE (resolution breaks "
             "immediately). WRITE — confirm-gated (412).",
             inputSchema=DnsDeleteRecordInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
