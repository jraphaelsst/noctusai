"""Vista CRM HTTP client — typed, async, audit-aware.

This is the only module that talks to Vista over the network. Everything
else (services, routers, normalizers) goes through this client.

See `products/erp-imobiliario/projects/vista-crm-wiring/VISTA-API.md` for
the full Vista contract — auth, query convention, response shape, and
error model. Keep this file in sync when the contract evolves.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_PAGE_SIZE = 50
PAGINATION_KEYS = {"total", "paginas", "pagina", "quantidade"}


class VistaError(Exception):
    """Base class for any Vista adapter failure."""


class VistaConfigError(VistaError):
    """Vista base URL or API key is missing/empty."""


class VistaUpstreamError(VistaError):
    """Generic upstream non-2xx wrapper."""

    def __init__(self, status: int, body: str, endpoint: str):
        super().__init__(f"Vista {endpoint} returned {status}: {body[:200]}")
        self.status = status
        self.body = body
        self.endpoint = endpoint


class VistaPermissionDenied(VistaUpstreamError):
    """Endpoint exists but the API key has no permission (HTTP 401)."""


class VistaNotFound(VistaUpstreamError):
    """Endpoint not exposed on this tenant (HTTP 404)."""


class VistaFieldNotAvailable(VistaUpstreamError):
    """Vista refused a field — `400 "Campo X não está disponível"`."""

    def __init__(self, field: str, body: str, endpoint: str):
        super().__init__(400, body, endpoint)
        self.field = field


class VistaTimeout(VistaError):
    """`httpx.TimeoutException` wrapper."""

    def __init__(self, endpoint: str):
        super().__init__(f"Vista {endpoint} timed out")
        self.endpoint = endpoint


class VistaCallResult:
    """Lightweight tuple-like carrier for a successful request.

    Carries both the parsed JSON and the raw response so the caller can
    audit-log latency + status without re-running the request.
    """

    __slots__ = ("data", "status", "latency_ms", "endpoint", "params_keys")

    def __init__(
        self,
        data: Any,
        status: int,
        latency_ms: int,
        endpoint: str,
        params_keys: list[str],
    ):
        self.data = data
        self.status = status
        self.latency_ms = latency_ms
        self.endpoint = endpoint
        self.params_keys = params_keys


class VistaClient:
    """Async HTTP client for the Vista REST API.

    Follows the dep-factory leniency rule: __init__ never raises on missing
    config. Any request raises VistaConfigError at call time.
    """

    def __init__(
        self,
        base_url: Optional[str],
        api_key: Optional[str],
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = api_key or ""
        self._timeout = timeout_seconds
        self._http_client = http_client  # injected for tests; None → per-call client

    @property
    def configured(self) -> bool:
        return bool(self._base_url) and bool(self._api_key)

    @property
    def base_url(self) -> str:
        return self._base_url

    # ------------------------------------------------------------------
    # Low-level request
    # ------------------------------------------------------------------

    async def _request(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        pesquisa: Optional[dict] = None,
        extra_params: Optional[dict] = None,
        showtotal: bool = False,
    ) -> VistaCallResult:
        if not self.configured:
            raise VistaConfigError(
                "Vista is not configured (VISTA_BASE_URL / VISTA_API_KEY missing)"
            )

        params: dict[str, Any] = {"key": self._api_key}
        if extra_params:
            params.update(extra_params)
        if pesquisa is not None:
            params["pesquisa"] = json.dumps(pesquisa, separators=(",", ":"))
        if showtotal:
            params["showtotal"] = 1

        url = f"{self._base_url}{endpoint}"
        headers = {"Accept": "application/json"}
        params_keys = sorted(params.keys())

        started = time.perf_counter()
        try:
            if self._http_client is not None:
                resp = await self._http_client.request(
                    method, url, params=params, headers=headers, timeout=self._timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.request(
                        method, url, params=params, headers=headers
                    )
        except httpx.TimeoutException as e:
            logger.warning("Vista %s timed out after %.1fs: %s", endpoint, self._timeout, e)
            raise VistaTimeout(endpoint) from e
        except httpx.HTTPError as e:
            logger.warning("Vista %s HTTP error: %s", endpoint, e)
            raise VistaUpstreamError(0, str(e), endpoint) from e

        latency_ms = int((time.perf_counter() - started) * 1000)
        body_text = resp.text or ""

        if resp.status_code == 200:
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                logger.warning("Vista %s returned non-JSON 200: %s", endpoint, e)
                raise VistaUpstreamError(200, body_text, endpoint) from e
            return VistaCallResult(
                data=data,
                status=200,
                latency_ms=latency_ms,
                endpoint=endpoint,
                params_keys=params_keys,
            )

        if resp.status_code == 401:
            logger.info("Vista %s denied (401) — tenant key lacks permission", endpoint)
            raise VistaPermissionDenied(401, body_text, endpoint)

        if resp.status_code == 404:
            logger.info("Vista %s not found (404) — not exposed on this tenant", endpoint)
            raise VistaNotFound(404, body_text, endpoint)

        if resp.status_code == 400 and "não está disponível" in body_text:
            field = _extract_unavailable_field(body_text)
            logger.info("Vista %s rejected field %r", endpoint, field)
            raise VistaFieldNotAvailable(field, body_text, endpoint)

        logger.warning("Vista %s returned %d: %s", endpoint, resp.status_code, body_text[:200])
        raise VistaUpstreamError(resp.status_code, body_text, endpoint)

    # ------------------------------------------------------------------
    # Domain-level helpers
    # ------------------------------------------------------------------

    async def listar_imoveis(
        self,
        *,
        fields: list[Any],
        filter_: Optional[dict] = None,
        order: Optional[dict] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> VistaCallResult:
        pesquisa: dict[str, Any] = {
            "fields": fields,
            "paginacao": {"pagina": page, "quantidade": min(page_size, DEFAULT_PAGE_SIZE)},
        }
        if filter_:
            pesquisa["filter"] = filter_
        if order:
            pesquisa["order"] = order
        return await self._request("/imoveis/listar", pesquisa=pesquisa, showtotal=True)

    async def detalhes_imovel(self, codigo: str, *, fields: list[Any]) -> VistaCallResult:
        return await self._request(
            "/imoveis/detalhes",
            pesquisa={"fields": fields},
            extra_params={"imovel": codigo},
        )

    async def listar_conteudo_imoveis(self, *, fields: list[str]) -> VistaCallResult:
        return await self._request(
            "/imoveis/listarConteudo",
            pesquisa={"fields": fields},
        )

    async def listar_usuarios(self, *, fields: list[str]) -> VistaCallResult:
        return await self._request("/usuarios/listar", pesquisa={"fields": fields})

    async def listar_agencias(self, *, fields: list[str]) -> VistaCallResult:
        return await self._request("/agencias/listar", pesquisa={"fields": fields})

    # ------------------------------------------------------------------
    # Diagnostics — health probe used by the "Diagnóstico" sub-tab
    # ------------------------------------------------------------------

    async def probe(self, endpoint: str) -> dict:
        """Probe a single endpoint and return a structured status row.

        Used by the diagnostics tab. Catches typed errors and returns
        a JSON-friendly summary instead of raising.
        """
        try:
            result = await self._request(endpoint, pesquisa={"fields": ["Codigo"]})
            return {
                "endpoint": endpoint,
                "status": "ok",
                "http_status": 200,
                "latency_ms": result.latency_ms,
            }
        except VistaPermissionDenied as e:
            return {"endpoint": endpoint, "status": "permission_denied", "http_status": e.status}
        except VistaNotFound as e:
            return {"endpoint": endpoint, "status": "not_found", "http_status": e.status}
        except VistaTimeout:
            return {"endpoint": endpoint, "status": "timeout", "http_status": None}
        except VistaConfigError:
            return {"endpoint": endpoint, "status": "not_configured", "http_status": None}
        except VistaUpstreamError as e:
            return {"endpoint": endpoint, "status": "upstream_error", "http_status": e.status}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_unavailable_field(body: str) -> str:
    """Best-effort parse of `"Campo X não está disponível"` payloads."""
    marker = "Campo "
    idx = body.find(marker)
    if idx < 0:
        return "<unknown>"
    tail = body[idx + len(marker):]
    end = tail.find(" ")
    return tail[:end] if end > 0 else tail[:32]


def extract_items(payload: dict) -> tuple[list[dict], dict]:
    """Split Vista's dict-keyed-by-id response into (items, pagination).

    Vista returns `{"<id1>": {...}, "<id2>": {...}, "total": 1784, ...}`.
    Pagination siblings are `total`, `paginas`, `pagina`, `quantidade`.

    Note: the dict key is whatever Vista uses as the primary id — that's
    alphanumeric for /imoveis ("CA2830") and numeric-as-string for
    /usuarios ("16") and /agencias ("1"). Don't read the key — read
    `Codigo` from the payload.
    """
    if not isinstance(payload, dict):
        return [], {}
    items: list[dict] = []
    pagination: dict = {}
    for key, value in payload.items():
        if key in PAGINATION_KEYS:
            pagination[key] = value
            continue
        if isinstance(value, dict):
            items.append(value)
    return items, pagination
