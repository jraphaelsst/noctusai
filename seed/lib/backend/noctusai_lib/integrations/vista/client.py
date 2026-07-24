"""Vista CRM HTTP client — typed, async, audit-aware. Canonical platform implementation.

Both consumers — `mcp/vista/` (in-repo MCP server) and the ERP showcase
router/service (`products/erp-imobiliario/backend/app/{routers,services}/vista_showcase*.py`) —
import this from `noctusai_lib.integrations.vista`.

**Formalized 2026-05-03** from two parallel ports at N=2 → triage time.
See `KB § INTEGRATIONS/vista.md` § 1-3 for the full Vista contract (auth,
query convention, response shape, error model), § 5.1-5.6 for the
adapter behavior this client implements, and § 6 for the per-tenant
calibration gap addressed by `mcp/vista/calibration.py`.
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


# ─── Error hierarchy (vista.md §3 typed-error model) ───────────────────────


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


# ─── Result carrier ───────────────────────────────────────────────────────


class VistaCallResult:
    """Lightweight tuple-like carrier for a successful request.

    Carries both the parsed JSON and the raw response so the caller can
    audit-log latency + status without re-running the request. (Same shape
    as the showcase adapter — kept compatible so absorbing into seed-lib
    later is a rename, not a rewrite.)
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


# ─── Client ───────────────────────────────────────────────────────────────


class VistaClient:
    """Async HTTP client for the Vista REST API.

    Follows the dep-factory leniency rule (vista.md § 1): __init__ never
    raises on missing config. Any request raises VistaConfigError at call
    time. This lets the MCP server start even when no Vista key is
    configured yet.
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

    # ─── Low-level request ──────────────────────────────────────────────

    async def _request(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        pesquisa: Optional[dict] = None,
        extra_params: Optional[dict] = None,
        showtotal: bool = False,
    ) -> VistaCallResult:
        # NOC-REMEDIATE[rate-limit]: pace this async chokepoint via
        # `await rate_limit.acquire_async("vista")` (mirror the Mailchimp
        # wiring). Deferred: Vista call volume is low today, but a
        # property-list sync loop should be paced before it grows. See
        # KB § PATTERNS/common/outbound-rate-limiting.md.
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
        # Sorted, key-only — never values (LGPD: vista.md § 5.4).
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

        if resp.status_code == 400:
            matched, field = _detect_unavailable_field(body_text)
            if matched:
                logger.info("Vista %s rejected field %r", endpoint, field)
                raise VistaFieldNotAvailable(field, body_text, endpoint)

        logger.warning("Vista %s returned %d: %s", endpoint, resp.status_code, body_text[:200])
        raise VistaUpstreamError(resp.status_code, body_text, endpoint)

    # ─── Domain-level helpers ───────────────────────────────────────────

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

    async def listar_clientes(self, *, fields: list[str]) -> VistaCallResult:
        """Permission-gated on most tenants (returns 401 → VistaPermissionDenied).

        Kept here so the MCP server can register `vista.clientes.list` as
        a real tool; the typed error becomes the response when the tenant
        key lacks permission (vista.md § 4.2).
        """
        return await self._request("/clientes/listar", pesquisa={"fields": fields})

    async def listar_corretores(self, *, fields: list[str]) -> VistaCallResult:
        """Permission-gated on most tenants (vista.md § 4.5)."""
        return await self._request("/corretores/listar", pesquisa={"fields": fields})

    # ─── Diagnostics ────────────────────────────────────────────────────

    async def probe(self, endpoint: str) -> dict:
        """Probe a single endpoint and return a structured status row.

        Catches typed errors and returns a JSON-friendly summary instead of
        raising. Used by `tools/diagnostics.py` and by `calibration.py`'s
        per-tenant field-set discovery.
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


# ─── Helpers ──────────────────────────────────────────────────────────────


def _detect_unavailable_field(body: str) -> tuple[bool, str]:
    """Detect the "Campo X não está disponível" pattern in a Vista 400 body.

    Vista's server JSON-escapes non-ASCII characters in the wire body
    (`"n\\u00e3o est\\u00e1 dispon\\u00edvel"` — five literal chars per
    escape, NOT pre-decoded). A naive `"não está disponível" in body`
    substring check misses every real Vista 400 because the source-code
    `não` (UTF-8 bytes) doesn't appear in the wire body.

    The fix: JSON-parse the body so unicode escapes resolve, then search
    the parsed `message` field (string or array of strings — vista.md
    § 3.3). Falls back to raw-body search for endpoints that may emit
    plain-text bodies.

    Returns (matched, field_name); `field_name` is `<unknown>` if the
    pattern matched but the field couldn't be parsed.
    """
    candidates: list[str] = [body]
    try:
        payload = json.loads(body)
        if isinstance(payload, dict):
            msg = payload.get("message")
            if isinstance(msg, str):
                candidates.append(msg)
            elif isinstance(msg, list):
                candidates.extend(s for s in msg if isinstance(s, str))
    except (json.JSONDecodeError, ValueError):
        pass

    for text in candidates:
        if "não está disponível" in text:
            return True, _extract_field_name(text)
    return False, "<unknown>"


def _extract_field_name(text: str) -> str:
    """Pull `<X>` out of `"Campo <X> não está disponível"`."""
    marker = "Campo "
    idx = text.find(marker)
    if idx < 0:
        return "<unknown>"
    tail = text[idx + len(marker):]
    end = tail.find(" ")
    return tail[:end] if end > 0 else tail[:32]


def extract_items(payload: dict) -> tuple[list[dict], dict]:
    """Split Vista's dict-keyed-by-id response into (items, pagination).

    Vista returns `{"<id1>": {...}, "<id2>": {...}, "total": 1784, ...}`.
    Pagination siblings are `total`, `paginas`, `pagina`, `quantidade`.

    The dict key is whatever Vista uses as the primary id — alphanumeric for
    /imoveis ("CA2830"), numeric-as-string for /usuarios ("16") and
    /agencias ("1"). Don't read the key — read `Codigo` from the payload.

    Defensive: returns ([], {}) for non-dict input.
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


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_PAGE_SIZE",
    "PAGINATION_KEYS",
    "VistaError",
    "VistaConfigError",
    "VistaUpstreamError",
    "VistaPermissionDenied",
    "VistaNotFound",
    "VistaFieldNotAvailable",
    "VistaTimeout",
    "VistaCallResult",
    "VistaClient",
    "extract_items",
]
