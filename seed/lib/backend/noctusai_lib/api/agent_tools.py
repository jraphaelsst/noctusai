"""Agent-tools router factory -- the platform's product-token callback surface for agents.

An agent (issuer ``agents``) calls back into a product DURING a turn with a product token carrying one
scope. This factory builds that router once, so every product surface (a chat agent's read tools, a creation
agent's read tools, ...) shares the SAME gate and error envelope instead of re-implementing it:

  - no / invalid / expired credential -> 401 (the underlying auth dep, before anything here)
  - a human session                   -> 403 ``product_required``
  - missing scope                     -> 403 ``scope_missing``
  - issuer != ``issuer``              -> 403 ``issuer_not_allowed``  (a scope says what a token may do, never who holds it)
  - unknown tool                      -> 404 ``ferramenta_desconhecida``
  - body does not fit the tool model  -> 422 ``invalid_field``

Success is ``{"data": ..., **meta}``. The org is ALWAYS the token's (``ctx.org_id``), never a body field. Every
call is logged (tool, org, latency, outcome) for measurement.

The product injects its own seams: ``get_auth_context`` (its auth dep), ``get_client`` (the schema-scoped client
dep tests override) and ``coerce_org`` (auth org -> the type its tools take). Access tier: ``service``.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Mapping, NamedTuple, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import ValidationError

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth.session import AuthContext, require_scopes
from noctusai_lib.api.schemas import StrictHttpModel
from noctusai_lib.primitives.exceptions import AppException

logger = logging.getLogger(__name__)


class ToolResult(NamedTuple):
    """A tool result with sibling keys next to ``data`` (returned as ``{"data": data, **meta}``)."""

    data: Any
    meta: dict[str, Any]


class AgentTool(NamedTuple):
    """One tool: its strict body model and ``run(client, org, args_dict) -> data | ToolResult``."""

    args: type[StrictHttpModel]
    run: Callable[[Any, Any, dict[str, Any]], Any]


#: Called after a successful tool run: ``(client, org, nome, args, data)``. Must never raise.
AfterCall = Callable[[Any, Any, str, dict[str, Any], Any], None]


def make_agent_tools_router(
    prefix: str,
    scope: str,
    registry: Mapping[str, AgentTool],
    *,
    get_auth_context: Callable[..., Any],
    get_client: Callable[..., Any],
    coerce_org: Callable[[Any], Any] = lambda raw: raw,
    issuer: str = "agents",
    tags: Optional[list[str]] = None,
    extra_routes: Optional[Callable[[APIRouter, Callable[..., AuthContext]], None]] = None,
    after_call: Optional[AfterCall] = None,
) -> APIRouter:
    """Build ``POST {prefix}/{nome}``. ``extra_routes(router, require_tools)`` registers routes that must be
    declared BEFORE the ``/{nome}`` catch-all (they share the same auth dependency)."""

    def require_tools(
        ctx: AuthContext = Depends(require_scopes(scope, get_auth_context=get_auth_context, restrict="product_only")),
    ) -> AuthContext:
        if ctx.issuer != issuer:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"detail": "Token issuer not allowed for this route", "code": "issuer_not_allowed"},
            )
        return ctx

    router = make_router(tier="service", guard=require_tools, prefix=prefix, tags=tags or ["agent-tools"])

    if extra_routes is not None:
        extra_routes(router, require_tools)

    @router.post("/{nome}")  # access-tier-ok: tier service -- make_router(guard=require_tools): product token + scope + issuer
    def post_ferramenta(
        nome: str,
        corpo: dict[str, Any] = Body(default_factory=dict),
        ctx: AuthContext = Depends(require_tools),
        client: Any = Depends(get_client),
    ) -> dict[str, Any]:
        tool = registry.get(nome)
        if tool is None:
            raise AppException("ferramenta_desconhecida", "Ferramenta desconhecida.", status_code=404)
        try:
            args = tool.args(**corpo).model_dump()
        except ValidationError as exc:
            campos = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
            raise AppException(
                "invalid_field", "Argumentos inválidos.", status_code=422, details={"campos": campos},
            ) from exc
        org = coerce_org(ctx.org_id)
        t0 = time.perf_counter()
        outcome = "ok"
        try:
            resultado = tool.run(client, org, args)
        except Exception:
            outcome = "error"
            raise
        finally:
            logger.info(
                "agent_tool prefix=%s tool=%s org=%s latency_ms=%d outcome=%s",
                prefix, nome, org, int((time.perf_counter() - t0) * 1000), outcome,
            )
        data, meta = (resultado.data, resultado.meta) if isinstance(resultado, ToolResult) else (resultado, {})
        if after_call is not None:
            after_call(client, org, nome, args, data)
        return {"data": data, **meta}

    return router


__all__ = ["AfterCall", "AgentTool", "ToolResult", "make_agent_tools_router"]
