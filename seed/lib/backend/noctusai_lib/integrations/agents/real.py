"""Real HTTP client of agents: the shared transport + the org-specs surface.

`AgentsHttpTransport` is the base a product-specific client (social-wiring's channel client) extends:
it owns the httpx plumbing, the timeout/network mapping and agents' two error-body shapes; the status->
exception table is a hook (`raise_for_status`) so the channel client keeps its richer one.
"""
from __future__ import annotations

from typing import Any, Callable, Optional
from urllib.parse import quote

import httpx

from noctusai_lib.integrations.agents.errors import (
    AgentNotFound,
    AgentsBadRequest,
    AgentsClientError,
    AgentsTimeout,
    AgentsTokenInvalid,
    AgentsUpstreamError,
)
from noctusai_lib.integrations.agents.types import OrgSpecDeclarada, OrgSpecs

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_RETRY_AFTER_S = 30


def error_code(response: httpx.Response) -> Optional[str]:
    """agents' errors are `HTTPException(detail={"detail", "code"})`; the seed auth deps raise
    plain-string details. Read both shapes defensively."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    detail = body.get("detail")
    if isinstance(detail, dict):
        code = detail.get("code")
        return str(code) if code else None
    code = body.get("code")
    return str(code) if code else None


def retry_after(response: httpx.Response) -> int:
    raw = response.headers.get("Retry-After", "")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_S
    return max(1, min(value, 3600))


def raise_for_agents_status(response: httpx.Response) -> None:
    """Generic status -> typed exception (2xx returns). Products with a richer table pass their own."""
    status = response.status_code
    if status < 400:
        return
    code = error_code(response)
    if status in (401, 403):
        raise AgentsTokenInvalid(f"agents refused the credential ({status})", code=code)
    if status == 404:
        if code == "agent_not_found":
            raise AgentNotFound("agent not found", code=code)
        raise AgentsUpstreamError("agents answered 404", code=code)
    if status == 422:
        fields: dict[str, Any] = {}
        try:
            body = response.json()
            detail = body.get("detail") if isinstance(body, dict) else None
            if isinstance(detail, dict):
                fields = {k: v for k, v in detail.items() if k not in ("detail", "code")}
                msg = str(detail.get("detail") or code or "")
            else:
                msg = str(detail or code or "")
        except ValueError:
            msg = code or ""
        raise AgentsBadRequest(msg or "agents rejected the request", code=code, fields=fields)
    raise AgentsUpstreamError(f"agents answered {status}", code=code)


def need(body: Any, key: str, kind: type | tuple) -> Any:
    if not isinstance(body, dict) or key not in body or not isinstance(body[key], kind):
        raise AgentsUpstreamError(f"malformed agents response: '{key}'")
    return body[key]


def opt_str(body: Any, key: str) -> Optional[str]:
    value = body.get(key) if isinstance(body, dict) else None
    return value if isinstance(value, str) and value else None


class AgentsHttpTransport:
    """base_url = `resolve_product_url("agents")`; `token` is sent as a bearer and never logged."""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        raise_for_status: Callable[[httpx.Response], None] = raise_for_agents_status,
    ):
        if not base_url:
            raise ValueError(f"{type(self).__name__} needs a base_url")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._transport = transport
        self._raise_for_status = raise_for_status

    def _client(self, token: Optional[str] = None) -> httpx.AsyncClient:
        bearer = token if token is not None else self._token
        if not bearer:
            raise ValueError(f"{type(self).__name__} needs a token")
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout,
            headers={"Authorization": f"Bearer {bearer}"}, transport=self._transport,
        )

    async def _send(
        self, method: str, path: str, *, json: Optional[dict] = None, params: Optional[dict] = None,
        ok_statuses: tuple[int, ...] = (), token: Optional[str] = None,
    ) -> Any:
        try:
            async with self._client(token) as client:
                response = await client.request(method, path, json=json, params=params)
        except httpx.TimeoutException as exc:
            raise AgentsTimeout("agents did not answer in time") from exc
        except httpx.HTTPError as exc:
            raise AgentsTimeout(f"agents unreachable: {type(exc).__name__}") from exc
        if response.status_code in ok_statuses:
            return None
        self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise AgentsUpstreamError("agents returned a non-JSON body") from exc


def parse_org_specs(body: Any) -> OrgSpecs:
    declaradas_raw = need(body, "declaradas", list)
    valores_raw = need(body, "valores", list)
    declaradas = tuple(
        OrgSpecDeclarada(
            chave=need(d, "chave", str), rotulo=need(d, "rotulo", str),
            descricao=d.get("descricao") if isinstance(d.get("descricao"), str) else "",
            tipo=d.get("tipo") if d.get("tipo") in ("texto", "texto_longo") else "texto",
            obrigatoria=bool(d.get("obrigatoria", True)), exemplo=opt_str(d, "exemplo"),
        )
        for d in declaradas_raw
    )
    return OrgSpecs(
        agent_key=need(body, "agent_key", str),
        declaradas=declaradas,
        valores={need(v, "chave", str): (v.get("valor") if isinstance(v.get("valor"), str) else "") for v in valores_raw},
        faltando=tuple(str(c) for c in need(body, "faltando", list)),
        version_id=opt_str(body, "version_id"),
        versao=body.get("versao") if isinstance(body.get("versao"), int) else None,
    )


class HttpAgentsOrgSpecsClient(AgentsHttpTransport):
    """`GET|PUT /api/studio/agents/{key}/specs` acting AS the logged-in user (their bearer per call)."""

    @staticmethod
    def _path(agent_key: str) -> str:
        return f"/api/studio/agents/{quote(agent_key, safe='')}/specs"

    async def get_org_specs(self, agent_key: str, *, token: str) -> OrgSpecs:
        return parse_org_specs(await self._send("GET", self._path(agent_key), token=token))

    async def put_org_specs(self, agent_key: str, valores: dict[str, str], *, token: str) -> OrgSpecs:
        return parse_org_specs(await self._send("PUT", self._path(agent_key), json={"valores": valores}, token=token))
