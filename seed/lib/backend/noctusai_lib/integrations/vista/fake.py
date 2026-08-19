"""In-memory deterministic FakeVistaClient for dev + tests.

Mirrors the public surface of `VistaClient` (the Real adapter) without
any network. Seed it with raw Vista-shaped payloads keyed by endpoint;
calls return `VistaCallResult` with the seeded `data` so the same
showcase normalizers (`vista_imovel_detalhes_to_showcase`, …) exercise
the *real* mapping code path.

The fake reproduces the two behaviors consumers depend on:

- **Config leniency** — `__init__` never raises; an *unconfigured*
  fake raises `VistaConfigError` at call time (same as the Real
  client per vista.md § 1). Pass ``configured=True`` (default) for the
  happy path.
- **Typed-error injection** — map an endpoint to a `VistaError`
  subclass instance in `errors=` and the matching call raises it,
  so tests cover the 401 / 404 / 400-field / timeout branches without
  a live tenant.

Seed-data shape::

    FakeVistaClient(
        responses={
            "/imoveis/detalhes": {
                "Codigo": "ONE10121",
                "TituloSite": "Casa com 2 dormitórios ...",
                "ValorVenda": "850000.00",
                "Caracteristicas": {"Piscina": "Sim"},
            },
        },
        errors={"/clientes/listar": VistaPermissionDenied(401, "{}", "/clientes/listar")},
    )

Validated against the live workspace behavior captured in
`SESSION-NOTES_chatbot-multichannel-2026-05-12` (live
`/imoveis/detalhes?imovel=ONE10121` returning real property data).
"""
from __future__ import annotations

from typing import Any, Optional

from .client import (
    DEFAULT_PAGE_SIZE,
    VistaCallResult,
    VistaConfigError,
    VistaError,
)


class FakeVistaClient:
    """Deterministic in-memory `VistaClient` stand-in.

    Every domain helper resolves its endpoint, then either raises the
    seeded `VistaError` for that endpoint or returns a `VistaCallResult`
    wrapping the seeded payload (`{}` when nothing was seeded — a
    valid empty Vista response). `latency_ms` is fixed at 0; the call
    is recorded in `self.calls` as `(endpoint, params_keys)` for
    post-hoc assertions.
    """

    def __init__(
        self,
        responses: Optional[dict[str, Any]] = None,
        errors: Optional[dict[str, VistaError]] = None,
        *,
        configured: bool = True,
        base_url: str = "https://fake-vista.local",
    ) -> None:
        self._responses: dict[str, Any] = dict(responses or {})
        self._errors: dict[str, VistaError] = dict(errors or {})
        self._configured = configured
        self._base_url = base_url.rstrip("/")
        self.calls: list[tuple[str, list[str]]] = []

    # ─── Parity properties (mirror VistaClient) ─────────────────────────

    @property
    def configured(self) -> bool:
        return self._configured

    @property
    def base_url(self) -> str:
        return self._base_url

    # ─── Core resolution ────────────────────────────────────────────────

    def _resolve(
        self, endpoint: str, params_keys: list[str]
    ) -> VistaCallResult:
        if not self._configured:
            raise VistaConfigError(
                "Vista is not configured (VISTA_BASE_URL / VISTA_API_KEY missing)"
            )
        self.calls.append((endpoint, sorted(params_keys)))
        if endpoint in self._errors:
            raise self._errors[endpoint]
        data = self._responses.get(endpoint, {})
        return VistaCallResult(
            data=data,
            status=200,
            latency_ms=0,
            endpoint=endpoint,
            params_keys=sorted(params_keys),
        )

    # ─── Domain helpers (signature-parity with VistaClient) ─────────────

    async def listar_imoveis(
        self,
        *,
        fields: list[Any],
        filter_: Optional[dict] = None,
        order: Optional[dict] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> VistaCallResult:
        return self._resolve("/imoveis/listar", ["key", "pesquisa", "showtotal"])

    async def detalhes_imovel(
        self, codigo: str, *, fields: list[Any]
    ) -> VistaCallResult:
        return self._resolve("/imoveis/detalhes", ["imovel", "key", "pesquisa"])

    async def listar_conteudo_imoveis(
        self, *, fields: list[str]
    ) -> VistaCallResult:
        return self._resolve("/imoveis/listarConteudo", ["key", "pesquisa"])

    async def listar_usuarios(self, *, fields: list[str]) -> VistaCallResult:
        return self._resolve("/usuarios/listar", ["key", "pesquisa"])

    async def listar_agencias(self, *, fields: list[str]) -> VistaCallResult:
        return self._resolve("/agencias/listar", ["key", "pesquisa"])

    async def listar_clientes(
        self,
        *,
        fields: list[str],
        filter_: Optional[dict] = None,
        order: Optional[dict] = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> VistaCallResult:
        # `showtotal` is in the params list because the Real client now sends
        # it — the Fake records the same param_keys the Real would, or the
        # recorded-call assertions stop meaning anything.
        return self._resolve("/clientes/listar", ["key", "pesquisa", "showtotal"])

    async def detalhes_cliente(
        self, codigo: str, *, fields: list[str]
    ) -> VistaCallResult:
        return self._resolve("/clientes/detalhes", ["cliente", "key", "pesquisa"])

    async def listar_corretores(
        self,
        *,
        fields: list[str],
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> VistaCallResult:
        return self._resolve("/corretores/listar", ["key", "pesquisa", "showtotal"])

    async def probe(self, endpoint: str) -> dict:
        """Structured status row — never raises (mirrors VistaClient.probe)."""
        try:
            result = self._resolve(endpoint, ["key", "pesquisa"])
            return {
                "endpoint": endpoint,
                "status": "ok",
                "http_status": 200,
                "latency_ms": result.latency_ms,
            }
        except VistaConfigError:
            return {
                "endpoint": endpoint,
                "status": "not_configured",
                "http_status": None,
            }
        except VistaError as exc:
            return {
                "endpoint": endpoint,
                "status": "error",
                "http_status": getattr(exc, "status", None),
            }


__all__ = ["FakeVistaClient"]
