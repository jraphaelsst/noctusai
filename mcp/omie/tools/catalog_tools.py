"""`omie.catalog.*` — offline discovery over the whole Omie API.

Omie publishes no OpenAPI document, so an agent that doesn't already know
the method name has nowhere to look. These tools answer that from the
bundled catalog: 134 endpoints, 461 methods, 1757 complex types, with the
live request example Omie ships for each method.

None of them spends an API request — discovery must never eat into the
per-method rate budget or risk the 30-minute failure block.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from .. import catalog


async def search(args: dict) -> dict:
    hits = catalog.search(
        args.get("query") or "",
        limit=int(args.get("limit") or 25),
        family=args.get("family"),
    )
    return {
        "ok": True,
        "query": args.get("query"),
        "count": len(hits),
        "results": hits,
        "hint": "Use omie.catalog.describe_method for the full param schema "
                "and a live example, then omie.call.invoke to run it.",
    }


async def describe_method(args: dict) -> dict:
    try:
        return {"ok": True, **catalog.describe_method(
            args.get("call") or "",
            endpoint=args.get("endpoint"),
            depth=int(args.get("depth") or 2),
        )}
    except KeyError as e:
        return {"ok": False, "error": {
            "error_class": "UnknownMethod", "status": 404,
            "message": str(e).strip('"')}}


async def list_endpoints(args: dict) -> dict:
    eps = catalog.list_endpoints(args.get("family"))
    return {"ok": True, "count": len(eps), "family": args.get("family"),
            "endpoints": eps}


async def endpoint_methods(args: dict) -> dict:
    try:
        methods = catalog.endpoint_methods(args.get("endpoint") or "")
        return {"ok": True, "endpoint": args.get("endpoint"),
                "count": len(methods), "methods": methods}
    except KeyError as e:
        return {"ok": False, "error": {
            "error_class": "UnknownEndpoint", "status": 404,
            "message": str(e).strip('"')}}


async def status(args: dict) -> dict:
    return {"ok": True, **catalog.status()}


HANDLERS = {
    "omie.catalog.search": search,
    "omie.catalog.describe_method": describe_method,
    "omie.catalog.list_endpoints": list_endpoints,
    "omie.catalog.endpoint_methods": endpoint_methods,
    "omie.catalog.status": status,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="omie.catalog.search",
            description=(
                "Search all 461 Omie API methods by keyword (name, description, "
                "resource). Omie publishes no OpenAPI spec, so this is how you "
                "find the right method — e.g. 'contas a receber', 'nota fiscal', "
                "'estoque', 'pix'. Costs no API request. Returns ranked hits with "
                "the endpoint and whether the method mutates data."
            ),
            inputSchema={"type": "object", "properties": {
                "query": {"type": "string", "description":
                          "Keywords, Portuguese or English."},
                "family": {"type": "string", "enum":
                           ["geral", "financas", "produtos", "servicos",
                            "estoque", "crm", "contador"],
                           "description": "Optional family filter."},
                "limit": {"type": "integer", "default": 25, "minimum": 1, "maximum": 100},
            }, "required": ["query"]},
        ),
        Tool(
            name="omie.catalog.describe_method",
            description=(
                "Full schema for one Omie method: every parameter with its type, "
                "max length and Portuguese documentation, the resolved nested "
                "complex types, the return shape, AND the live request example "
                "Omie publishes. Call this before omie.call.invoke to build a "
                "valid `param` first time. Costs no API request."
            ),
            inputSchema={"type": "object", "properties": {
                "call": {"type": "string", "description":
                         "Method name, e.g. 'IncluirContaReceber'."},
                "endpoint": {"type": "string", "description":
                             "Optional, to disambiguate a shared method name."},
                "depth": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5,
                          "description":
                          "Nested type expansion depth. Omie types nest deeply; "
                          "truncation is always reported, never silent."},
            }, "required": ["call"]},
        ),
        Tool(
            name="omie.catalog.list_endpoints",
            description=(
                "Inventory of all 134 Omie endpoints with their method names, "
                "optionally filtered by family (geral, financas, produtos, "
                "servicos, estoque, crm, contador). Costs no API request."
            ),
            inputSchema={"type": "object", "properties": {
                "family": {"type": "string", "enum":
                           ["geral", "financas", "produtos", "servicos",
                            "estoque", "crm", "contador"]},
            }},
        ),
        Tool(
            name="omie.catalog.endpoint_methods",
            description=(
                "Every method on one endpoint (e.g. '/financas/contareceber/') "
                "with descriptions and live examples. Costs no API request."
            ),
            inputSchema={"type": "object", "properties": {
                "endpoint": {"type": "string", "description":
                             "Endpoint path, e.g. '/geral/clientes/'."},
            }, "required": ["endpoint"]},
        ),
        Tool(
            name="omie.catalog.status",
            description=(
                "Provenance of the bundled API catalog — when it was harvested "
                "from Omie's developer portal and what it covers. Check this if a "
                "method seems missing: the catalog is a snapshot and can be "
                "regenerated with scripts/harvest_catalog.py."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
