"""`omie.call.*` — the generic seam that reaches the ENTIRE Omie API.

Omie's uniform `{call, app_key, app_secret, param}` envelope means one
correct implementation covers all 134 endpoints and 461 methods. The
curated tools in `resources.py` are ergonomics on top; this module is the
completeness guarantee — anything Omie can do, these two tools can do.

The generic seam is validated, not raw: `call`/`endpoint` are checked
against the bundled catalog first, so a typo returns "did you mean
UpsertCliente?" instead of burning a request against Omie's per-method
rate budget and coming back with a Portuguese fault string.

`escape_hatch=true` exists for a method Omie ships that our catalog
snapshot predates — it skips validation but is explicitly labelled in the
result so an unvalidated call is never mistaken for a validated one.
"""
from __future__ import annotations

from mcp.server import Server
from mcp.types import Tool

from .. import catalog
from ..api import client_for, is_mutating, normalize_path
from ..errors import OmieValidationError
from ._common import guarded, schema


def _resolve(call: str, endpoint: str | None, escape_hatch: bool) -> tuple[str, dict | None]:
    """Resolve (and validate) the endpoint for a method. Returns (path, meta)."""
    if endpoint:
        path = normalize_path(endpoint)
        if not escape_hatch:
            try:
                known = {m["call"] for m in catalog.endpoint_methods(path)}
            except KeyError as e:
                raise OmieValidationError(str(e), status=422) from e
            if call not in known:
                raise OmieValidationError(
                    f"Method {call!r} is not on endpoint {path!r}. "
                    f"Available there: {sorted(known)}. "
                    f"Or omit `endpoint` to let the catalog resolve it.",
                    status=422,
                )
        return path, catalog.find_method(call)
    hit = catalog.find_method(call)
    if hit is None:
        if escape_hatch:
            raise OmieValidationError(
                f"escape_hatch=true requires an explicit `endpoint` for the "
                f"uncatalogued method {call!r}.", status=422,
            )
        raise OmieValidationError(
            f"Unknown Omie method {call!r}. Did you mean: {catalog.suggest(call)}? "
            f"Use omie.catalog.search to browse all 461 methods.",
            status=422,
        )
    return hit["endpoint"], hit


async def invoke(args: dict) -> dict:
    """Call any Omie method by name."""
    async def run():
        call = (args.get("call") or "").strip()
        if not call:
            raise OmieValidationError("`call` is required.", status=422)
        escape = bool(args.get("escape_hatch"))
        path, meta = _resolve(call, args.get("endpoint"), escape)
        c = client_for(args.get("environment"))
        result = await c.call(
            path, call, args.get("param") or {},
            confirm=bool(args.get("confirm")),
        )
        return {
            "environment": c.env.name,
            "call": call,
            "endpoint": path,
            "mutating": is_mutating(call),
            "validated": meta is not None and not escape,
            "result": result,
        }
    return await guarded(run)


async def paginate(args: dict) -> dict:
    """Call any `Listar*` method and walk its pages."""
    async def run():
        call = (args.get("call") or "").strip()
        if not call:
            raise OmieValidationError("`call` is required.", status=422)
        path, _ = _resolve(call, args.get("endpoint"), bool(args.get("escape_hatch")))
        if is_mutating(call):
            raise OmieValidationError(
                f"{call!r} is not a read method — paginate only walks "
                f"Listar*/Pesquisar* methods. Use omie.call.invoke instead.",
                status=422,
            )
        c = client_for(args.get("environment"))
        out = await c.paginate(
            path, call, args.get("param") or {},
            page_size=int(args.get("page_size") or 50),
            max_pages=int(args.get("max_pages") or 5),
            max_records=args.get("max_records"),
            records_key=args.get("records_key"),
        )
        return {"environment": c.env.name, "call": call, "endpoint": path, **out}
    return await guarded(run)


HANDLERS = {"omie.call.invoke": invoke, "omie.call.paginate": paginate}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="omie.call.invoke",
            description=(
                "Call ANY of Omie's 461 API methods by name — the complete "
                "escape hatch beyond the curated tools. The endpoint is resolved "
                "from the bundled catalog, so you usually pass only `call` and "
                "`param`. Unknown method names are rejected with suggestions "
                "before any request is spent. Mutating calls (Incluir/Alterar/"
                "Excluir/Upsert/Cancelar/...) require confirm=true and are "
                "refused on a readonly environment. Look up the exact `param` "
                "shape with omie.catalog.describe_method first."
            ),
            inputSchema=schema({
                "call": {"type": "string", "description":
                         "Omie method name, e.g. 'ListarClientes', 'UpsertCliente', "
                         "'LancarRecebimento'."},
                "param": {"type": "object", "description":
                          "The method's parameter object (wrapped into Omie's "
                          "`param` array for you)."},
                "endpoint": {"type": "string", "description":
                             "Optional explicit endpoint, e.g. '/geral/clientes/'. "
                             "Only needed to disambiguate a name shared by several "
                             "endpoints."},
                "escape_hatch": {"type": "boolean", "default": False,
                                 "description":
                                 "Skip catalog validation for a method newer than "
                                 "the bundled snapshot. Requires `endpoint`. The "
                                 "result is flagged validated=false."},
            }, required=["call"], confirm=True),
        ),
        Tool(
            name="omie.call.paginate",
            description=(
                "Walk ANY Omie list method across pages and concatenate the "
                "records. Handles Omie's 100-record page cap, detects the "
                "per-resource record array automatically, and stops cleanly at "
                "end-of-data (which Omie signals as a fault, not an empty list). "
                "Always reports `truncated` and `next_page` so a partial result "
                "is never mistaken for a complete one."
            ),
            inputSchema=schema({
                "call": {"type": "string", "description":
                         "A read method, e.g. 'ListarContasReceber'."},
                "param": {"type": "object", "description": "Filters / date ranges."},
                "endpoint": {"type": "string", "description": "Optional explicit endpoint."},
                "page_size": {"type": "integer", "default": 50, "minimum": 1, "maximum": 100},
                "max_pages": {"type": "integer", "default": 5, "minimum": 1},
                "max_records": {"type": "integer", "description": "Optional hard cap."},
                "records_key": {"type": "string", "description":
                                "Override the auto-detected record-array key."},
                "escape_hatch": {"type": "boolean", "default": False},
            }, required=["call"]),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
