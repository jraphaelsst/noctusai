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
import re
import time
from typing import Any, Mapping, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_PAGE_SIZE = 50
PAGINATION_KEYS = {"total", "paginas", "pagina", "quantidade"}

KEY_REDACTION_PLACEHOLDER = "<VISTA_API_KEY:redacted>"


def redact_api_key(text: str, api_key: str) -> str:
    """Strip the tenant API key out of any text bound for an exception or log.

    Vista echoes the key **verbatim** in its 401 body — confirmed live
    2026-08-05 against `oneconsu-rest.vistahost.com.br`::

        {"status":401,"message":"Permissão Negada: \\"<key>\\" Método: clientes/listar"}

    and the key also rides in the query string of any URL that httpx
    surfaces inside a transport error. Both paths end up in
    `VistaUpstreamError.body` / `str(exc)`, and from there in the MCP's
    `typed_error.message` — which is read straight into an AI agent's
    context. Redact at the boundary, so no downstream consumer has to
    remember to.

    Applied at every point where upstream text enters our error/log model;
    see `KB § INTEGRATIONS/vista.md § 3` (Credential echo).
    """
    if not api_key or not text:
        return text
    return text.replace(api_key, KEY_REDACTION_PLACEHOLDER)


# ─── Endpoint baseline (vista.md § 4) ─────────────────────────────────────

# Probe-status vocabulary. The permission_gated/absent split is the
# actionable one: only the former is unlocked by a Vista support request.
ENDPOINT_LIVE = "live_probed"            # reachable
ENDPOINT_PERMISSION_GATED = "permission_gated"  # route exists, key lacks grant (401)
ENDPOINT_WRITE_ONLY = "write_only"       # route exists, rejects GET (405)
ENDPOINT_ABSENT = "absent"               # no such route on this tenant (404)

# Canonical for BOTH consumers — `mcp/vista/tools/diagnostics.py` and the ERP
# showcase service (`products/erp-imobiliario/.../vista_showcase_service.py`).
# Lifted to the seed 2026-08-05 at N=2: the identical list had been hand-copied
# into both, and both carried the same two stale labels — a hand-maintained
# list in two places drifts in two places.
#
# `expected_http_status` is what a HEALTHY tenant returns for a BARE GET.
# Several of these are non-200 by design, so a non-200 is not itself a fault;
# only a deviation from this baseline is.
#
# Re-probed live 2026-08-21, after Vista applied the § 9 Tier-1 grant to key
# `…644c` and cleared their cache. `/clientes/listar` and `/clientes/detalhes`
# flipped 401 → open and are now graded as LIVE; a 401 on either from here on
# is a REGRESSION (the grant was rolled back), not the standing state.
# `/corretores/listar` was NOT included in that grant and stays gated.
VISTA_ENDPOINT_BASELINE: tuple[tuple[str, int, str, str], ...] = (
    ("/imoveis/listar", 200, ENDPOINT_LIVE, "reachable"),
    ("/imoveis/listarConteudo", 400, ENDPOINT_LIVE, "reachable; bare GET needs `pesquisa`"),
    ("/usuarios/listar", 200, ENDPOINT_LIVE, "reachable"),
    ("/agencias/listar", 200, ENDPOINT_LIVE, "reachable"),
    ("/clientes/listar", 200, ENDPOINT_LIVE, "granted 2026-08-21 (vista.md § 4.2); a 401 here is a grant ROLLBACK"),
    ("/clientes/detalhes", 400, ENDPOINT_LIVE, "granted 2026-08-21 (vista.md § 4.2); bare GET now reaches the missing-`cliente` 400 that the 401 used to precede"),
    ("/corretores/listar", 401, ENDPOINT_PERMISSION_GATED, "permission-gated (vista.md § 4.5) — NOT included in the 2026-08-21 grant"),
    ("/imoveis/fotos", 405, ENDPOINT_WRITE_ONLY, "write-only route; GET not allowed"),
)

VISTA_PROBE_PATHS: tuple[str, ...] = tuple(row[0] for row in VISTA_ENDPOINT_BASELINE)

# ─── Write-permission baseline (vista.md § 4.7) ───────────────────────────

# Verdict vocabulary for `VistaClient.probe_write_permission`.
WRITE_PERMITTED = "permitted"            # auth passed; Vista then asked for params
WRITE_DENIED = "denied"                  # 401 "Permissão Negada … Método: <m>"
WRITE_ABSENT = "absent"                  # 404 — no such route
WRITE_UNKNOWN = "unknown"                # timeout / 5xx / unrecognised body

# The three write routes this tenant exposes, with the verdict our key
# (`…644c`) actually gets — re-probed live 2026-09-16, the day Vista said the
# permission grants were resolved. `/imoveis/fotos` is still DENIED, so the
# grant has NOT landed for it; a `permitted` verdict there is the signal that
# it finally did. `/lead` was never tested before this probe existed and turns
# out to be PERMITTED.
#
# Why an empty POST is safe AND conclusive: Vista checks the per-method
# permission BEFORE it validates parameters. Proven on both sides of the gate
# 2026-09-16 — the sandbox key (write-permitted) answers an empty POST to
# `/imoveis/fotos` with the missing-`cadastro` 401, while our key answers the
# same request with `Permissão Negada`. With no `cadastro` there is nothing to
# create, so the probe can never write.
VISTA_WRITE_PERMISSION_BASELINE: tuple[tuple[str, str, str], ...] = (
    ("/imoveis/fotos", WRITE_DENIED, "photo upload — asked of Vista; still denied on …644c 2026-09-16"),
    ("/lead", WRITE_PERMITTED, "lead submission — permitted on …644c (first probed 2026-09-16)"),
    ("/clientes/anexos", WRITE_DENIED, "client attachments — denied on …644c; never requested"),
)

#: Vista's permission-denial marker. JSON-escaped on the wire
#: (`Permiss\u00e3o`), so match the ASCII prefix only.
_PERMISSION_DENIED_MARKER = "Permiss"


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
    """The API key lacks a grant.

    Two shapes: **401** `"Permissão Negada"` (method-level — the whole route)
    and **403** (field-level — e.g. the `proprietarios` owner group on
    `/imoveis/detalhes`, vista.md § 4.7). `status` tells them apart.
    """


class VistaMissingParameter(VistaUpstreamError):
    """A 401 that is NOT a permission denial — Vista's missing-parameter reply.

    Vista answers a request that lacks a required parameter with **401**, e.g.
    `"Você deve informar os dados em json no parâmetro \"cadastro\""`, and
    reserves `"Permissão Negada: … Método: <m>"` for real denials. Reading
    the status alone produced a retracted KB claim once already (vista.md
    § 4.7, "read the MESSAGE, not the status"), so the two are separate types.

    Deliberately NOT a `VistaPermissionDenied` subclass: a caller that
    catches the denial must not swallow a request-shape bug as "ask Vista".
    """


class VistaNotFound(VistaUpstreamError):
    """Endpoint not exposed on this tenant (HTTP 404)."""


class VistaFieldNotAvailable(VistaUpstreamError):
    """Vista refused one or more fields — `400 "Campo X não está disponível"`.

    Vista reports **every** rejected field in a single 400 (`message` is an
    array, one entry per field), so `fields` carries the whole set and the
    calibration loop can drop them in one pass. `field` remains the first
    rejected name for back-compat with callers that predate `fields`.
    """

    def __init__(self, fields: list[str], body: str, endpoint: str):
        super().__init__(400, body, endpoint)
        self.fields = list(fields)
        self.field = fields[0] if fields else "<unknown>"


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

    def _redact(self, text: str) -> str:
        """Scrub this client's API key from `text`. See `redact_api_key`."""
        return redact_api_key(text, self._api_key)

    # ─── Low-level request ──────────────────────────────────────────────

    async def _request(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        pesquisa: Optional[dict] = None,
        extra_params: Optional[dict] = None,
        cadastro: Optional[dict] = None,
        showtotal: bool = False,
    ) -> VistaCallResult:
        # NOC-REMEDIATE[rate-limit]: pace this async chokepoint via
        # `await rate_limit.acquire_async("vista")` (mirror the Mailchimp
        # wiring). Deferred: Vista call volume is low today, but a
        # property-list sync loop should be paced before it grows. See
        # KB § PATTERNS/common/outbound-rate-limiting.md. — 2026-07-24
        if not self.configured:
            raise VistaConfigError(
                "Vista is not configured (VISTA_BASE_URL / VISTA_API_KEY missing)"
            )

        params: dict[str, Any] = {"key": self._api_key}
        if extra_params:
            params.update(extra_params)
        if pesquisa is not None:
            params["pesquisa"] = json.dumps(pesquisa, separators=(",", ":"))
        if cadastro is not None:
            # Writes carry their payload in the QUERY string as `cadastro`,
            # with an empty body — the only shape Vista accepts (vista.md § 4.7).
            params["cadastro"] = json.dumps(cadastro, separators=(",", ":"))
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
            # httpx renders the full request URL — which carries ?key=<secret>.
            logger.warning(
                "Vista %s timed out after %.1fs: %s",
                endpoint, self._timeout, self._redact(str(e)),
            )
            raise VistaTimeout(endpoint) from e
        except httpx.HTTPError as e:
            redacted = self._redact(str(e))
            logger.warning("Vista %s HTTP error: %s", endpoint, redacted)
            raise VistaUpstreamError(0, redacted, endpoint) from e

        latency_ms = int((time.perf_counter() - started) * 1000)
        # Redact ONCE, here — every error/log path below is fed from body_text,
        # so this is the single boundary the credential has to cross.
        body_text = self._redact(resp.text or "")

        # 207 = a write where some items failed (per-photo fetch errors on
        # `/imoveis/fotos`). The request itself succeeded; the per-item
        # verdicts are in the body, so it is returned, not raised.
        if resp.status_code in (200, 207):
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                logger.warning("Vista %s returned non-JSON 200: %s", endpoint, e)
                raise VistaUpstreamError(resp.status_code, body_text, endpoint) from e
            return VistaCallResult(
                data=data,
                status=resp.status_code,
                latency_ms=latency_ms,
                endpoint=endpoint,
                params_keys=params_keys,
            )

        if resp.status_code == 401:
            # Read the MESSAGE, not the status (vista.md § 4.7). Only an
            # explicit missing-parameter reply is reclassified; any other 401
            # stays a denial, which is what a 401 meant before this split.
            if _is_missing_parameter(body_text):
                logger.info("Vista %s rejected the request shape (401): %s", endpoint, body_text[:200])
                raise VistaMissingParameter(401, body_text, endpoint)
            logger.info("Vista %s denied (401) — tenant key lacks permission", endpoint)
            raise VistaPermissionDenied(401, body_text, endpoint)

        if resp.status_code == 403:
            logger.info("Vista %s denied (403) — key lacks a field-level grant", endpoint)
            raise VistaPermissionDenied(403, body_text, endpoint)

        if resp.status_code == 404:
            logger.info("Vista %s not found (404) — not exposed on this tenant", endpoint)
            raise VistaNotFound(404, body_text, endpoint)

        if resp.status_code == 400:
            matched, fields = _detect_unavailable_fields(body_text)
            if matched:
                logger.info("Vista %s rejected fields %r", endpoint, fields)
                raise VistaFieldNotAvailable(fields, body_text, endpoint)

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

    async def listar_clientes(
        self,
        *,
        fields: list[str],
        filter_: Optional[dict] = None,
        order: Optional[dict] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> VistaCallResult:
        """✅ GRANTED on `oneconsu-rest` since 2026-08-21 — 42,960 clients.

        Still permission-gated on tenants that have not been granted, where
        it returns 401 → `VistaPermissionDenied`; that path is kept, not
        deleted, because it is the correct answer for an ungranted key
        (vista.md § 4.2).

        ⚠️ **LGPD — a 200 here is third-party personal data.** The eleven
        fields this tenant accepts include `Celular`, and asking for more
        reaches `DataNascimento` / `Sexo` / `EstadoCivil` / `Profissao`.
        Callers should request the MINIMUM projection they render; the ERP
        showcase splits list-vs-detail for exactly this reason
        (`ShowcaseCliente` vs `ShowcaseClienteDetalhes`).

        🔴 No `DataAtualizacao` on this family ⇒ no delta sync. A full
        refresh is 860 requests at the 50-row cap; do not design a polling
        loop over it without asking Vista for the field first.

        **Paginated like `listar_imoveis`, deliberately.** Until 2026-08-19
        this helper took no `page`/`page_size` at all while the MCP tool
        above it *declared* both — so a host asking for page 2 silently got
        page 1. A parameter a caller can set and the wire never sees is a
        silent error (CLAUDE.md §1); the two signatures are now the same
        shape, so the gated surface cannot drift from the working one again.
        """
        pesquisa: dict[str, Any] = {
            "fields": fields,
            "paginacao": {"pagina": page, "quantidade": min(page_size, DEFAULT_PAGE_SIZE)},
        }
        if filter_:
            pesquisa["filter"] = filter_
        if order:
            pesquisa["order"] = order
        return await self._request("/clientes/listar", pesquisa=pesquisa, showtotal=True)

    async def detalhes_cliente(self, codigo: str, *, fields: list[str]) -> VistaCallResult:
        """Per-client detail — `/clientes/detalhes?cliente=<codigo>`.

        ✅ GRANTED alongside `listar_clientes` on 2026-08-21. The 401 that
        used to precede parameter validation is gone: a bare GET now reaches
        the missing-`cliente` 400, which is why the probe baseline expects
        400 here and a 401 would read as a grant ROLLBACK.

        ⚠️ **LGPD — this is the widest personal-data surface in the tenant.**
        Correcting the record: it does NOT return CPF, address or e-mail —
        all four are rejected fields here. It DOES return `DataNascimento`,
        `Sexo`, `EstadoCivil` and `Profissao`, i.e. a demographic profile
        rather than the identity-document set the pre-grant note assumed
        (vista.md § 4.2). Scope requests to what the caller renders.
        """
        return await self._request(
            "/clientes/detalhes",
            pesquisa={"fields": fields},
            extra_params={"cliente": codigo},
        )

    async def listar_corretores(
        self,
        *,
        fields: list[str],
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> VistaCallResult:
        """Permission-gated on most tenants (vista.md § 4.5).

        Paginated for the same reason as `listar_clientes` above.
        """
        return await self._request(
            "/corretores/listar",
            pesquisa={
                "fields": fields,
                "paginacao": {
                    "pagina": page,
                    "quantidade": min(page_size, DEFAULT_PAGE_SIZE),
                },
            },
            showtotal=True,
        )

    # ─── Writes (vista.md § 4.7) ────────────────────────────────────────

    async def cadastrar_fotos_imovel(
        self, codigo: str, fotos: Mapping[str, str]
    ) -> VistaCallResult:
        """Attach photos to a listing — `POST /imoveis/fotos`.

        Contract (proven on the sandbox, vista.md § 4.7):

        - Vista **pulls** each image from its URL and re-hosts it; no bytes
          are sent, so every URL must be publicly reachable. base64 is
          rejected.
        - `fotos` is a keyed mapping (`{"foto1": url, …}`) — Vista answers
          per key. A JSON array is rejected, hence no `list` here.
        - `imovel` is a TOP-LEVEL param, not part of `cadastro`.
        - `200` = all attached; `207` = some keys failed (their entry in
          `data["Fotos"]` is an error list) and the failed ones created
          nothing. Inspect the per-key result either way.

        Raises `VistaPermissionDenied` when the key lacks the grant — the
        state of `…644c` as of 2026-09-16.
        """
        validate_fotos_payload(codigo, fotos)
        return await self._request(
            "/imoveis/fotos",
            method="POST",
            extra_params={"imovel": codigo},
            cadastro={"fields": dict(fotos)},
        )

    async def enviar_lead(self, lead: Mapping[str, Any]) -> VistaCallResult:
        """Submit an inbound lead — `POST /lead` (top level, NOT `/clientes/lead`).

        Contract (derived on the sandbox 2026-09-16):

        - payload is `cadastro={"lead": {...}}`; `{"fields": ...}` is rejected.
        - required: `nome`, `mensagem`, `veiculo` (the lead source, e.g. the
          portal/site name) and one of `email` / `fone`. Checked here first so
          a bad call never costs a round-trip.
        - Vista de-duplicates: a lead matching an existing client answers
          `"O cadastro foi encontrado."` instead of `"Ok."`. Both return
          `Codigo` (the client id) and `Corretor` (the assigned broker).
        - unknown keys are accepted silently, and `anuncio` (the listing code)
          is not validated — the caller owns correctness of both.

        ⚠️ LGPD: this WRITES a third party's personal data into the agency's
        CRM. The caller must hold a legal basis for that processing.
        """
        validate_lead_payload(lead)
        return await self._request(
            "/lead", method="POST", cadastro={"lead": dict(lead)}
        )

    async def probe_write_permission(self, endpoint: str) -> dict:
        """Non-mutating verdict on whether this key may write to `endpoint`.

        Sends a POST with **no payload**. Vista authorises before it
        validates, so the reply is `Permissão Negada` when the key lacks the
        method grant, and a missing-parameter/format error when it has it —
        and with no payload there is nothing to create. See
        `VISTA_WRITE_PERMISSION_BASELINE` for the evidence.

        Returns `{endpoint, verdict, http_status}`; never raises.
        """
        try:
            result = await self._request(endpoint, method="POST")
        except VistaPermissionDenied as e:
            return {"endpoint": endpoint, "verdict": WRITE_DENIED, "http_status": e.status}
        except VistaMissingParameter as e:
            return {"endpoint": endpoint, "verdict": WRITE_PERMITTED, "http_status": e.status}
        except VistaNotFound as e:
            return {"endpoint": endpoint, "verdict": WRITE_ABSENT, "http_status": e.status}
        except VistaConfigError:
            return {"endpoint": endpoint, "verdict": "not_configured", "http_status": None}
        except VistaTimeout:
            return {"endpoint": endpoint, "verdict": WRITE_UNKNOWN, "http_status": None}
        except VistaUpstreamError as e:
            # A 400 past the auth check ("O formato dos dados não está
            # correto" — `/clientes/anexos` on a permitted key) is still
            # evidence of permission. Anything else is not a verdict.
            verdict = WRITE_PERMITTED if e.status == 400 else WRITE_UNKNOWN
            return {"endpoint": endpoint, "verdict": verdict, "http_status": e.status}
        # An empty POST should never succeed; if it does, say so loudly
        # rather than guess.
        logger.warning("Vista %s accepted an EMPTY write probe (%d)", endpoint, result.status)
        return {"endpoint": endpoint, "verdict": WRITE_UNKNOWN, "http_status": result.status}

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


_LEAD_REQUIRED: tuple[str, ...] = ("nome", "mensagem", "veiculo")


def validate_fotos_payload(codigo: str, fotos: Mapping[str, str]) -> None:
    """Reject a photo write Vista would refuse. Shared by Real + Fake, so the
    Fake can never accept a call the Real rejects."""
    if not codigo:
        raise ValueError("codigo is required")
    if not fotos:
        raise ValueError("at least one photo URL is required")
    for key, url in fotos.items():
        if not key or not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise ValueError(f"photo {key!r} must map to an http(s) URL Vista can fetch")


def validate_lead_payload(lead: Mapping[str, Any]) -> None:
    """Reject a lead missing Vista's required fields (shared by Real + Fake)."""
    missing = [k for k in _LEAD_REQUIRED if not lead.get(k)]
    if not (lead.get("email") or lead.get("fone")):
        missing.append("email|fone")
    if missing:
        raise ValueError(f"lead is missing required field(s): {', '.join(missing)}")


def _is_missing_parameter(body: str) -> bool:
    """True iff a 401 body is Vista's missing-parameter reply, not a denial.

    Every such reply observed starts `"Você deve informar …"` (JSON-escaped
    on the wire as `Voc\u00ea deve informar`), so match the ASCII tail.
    """
    return _PERMISSION_DENIED_MARKER not in body and "deve informar" in body


def _detect_unavailable_fields(body: str) -> tuple[bool, list[str]]:
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

    **Every** rejected field is returned, not just the first. Vista emits one
    `message` entry per rejected field, so a single 400 already names the
    whole set — reading only the first turned calibration into one HTTP
    round-trip per rejected field (13 for `/clientes/listar` on `oneconsu`,
    measured 2026-08-21). Draining the array collapses that to two.

    Returns (matched, field_names); the list is `["<unknown>"]` if the
    pattern matched but no field name could be parsed.
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

    # Preserve first-seen order and de-duplicate: Vista repeats the same field
    # across both of its two message phrasings ("Campo X…" / "O campo X…").
    found: list[str] = []
    matched = False
    for text in candidates:
        if "não está disponível" not in text:
            continue
        matched = True
        # The raw body is in `candidates` too and holds every occurrence at
        # once; skip it only if a parsed message already yielded names.
        for name in _extract_field_names(text):
            if name not in found:
                found.append(name)
    if not matched:
        return False, []
    return True, found or ["<unknown>"]


#: Vista phrases the same rejection two ways in the SAME response — "Campo X
#: não está disponível." and "O campo X não está disponível." — so the match is
#: case-insensitive on `campo` and finds every occurrence in the text, not just
#: the first. Applied to a decoded upstream *message*, never to source.
_FIELD_REJECTION_RE = re.compile(r"campo\s+(\w+)\s+não\s+está\s+disponível", re.IGNORECASE)


def _extract_field_names(text: str) -> list[str]:
    """Pull every `<X>` out of `"Campo <X> não está disponível"` in `text`."""
    return _FIELD_REJECTION_RE.findall(text)


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
