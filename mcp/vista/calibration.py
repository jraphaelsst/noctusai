"""Per-tenant field-set calibration — addresses the gap in vista.md § 6.

**Why this module exists.** PROJECT.md §2 (`projects/vista-api-mcp/`) and
`KB § INTEGRATIONS/vista.md § 6` both name per-tenant calibration as
mandatory. The ERP showcase adapter does NOT implement it — it uses
hardcoded constants for `oneconsu-rest`. Phase 4.5 of the showcase
shipped a 422 surface for `VistaFieldNotAvailable` so drift is recoverable,
but the constants don't auto-correct.

This module is the in-repo MCP server's solution: an actual probe-based
discovery routine that runs on first real call and caches the resulting
safe field set per tenant key for the process lifetime.

**Algorithm (per vista.md § 6 sketch):**
1. Start from a CANDIDATE set: public-doc full superset PLUS NoctusAI-known
   fields (the constants from the showcase adapter — known to work for at
   least one tenant).
2. Send the bundle to the endpoint. On 200 → done, cache.
3. On `VistaFieldNotAvailable(field=X)` → drop `X`, retry.
4. Loop until 200 or until field count hits the floor `["Codigo"]`.

**Caching.** Results live in-process for the process lifetime (no TTL).
Tenant key rotation is rare; on rotation, restart the MCP server (or
invoke `Calibrator.reset()` from a tooling path).

Call from a tool handler:
    fields = await calibrator.get_imovel_list_fields(client)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from noctusai_lib.integrations.vista import (
    VistaClient,
    VistaConfigError,
    VistaFieldNotAvailable,
    VistaUpstreamError,
)

logger = logging.getLogger(__name__)


# ─── Candidate sets — public-doc superset + showcase-known fields ───────


# Public-doc /imoveis/listar fields known to work on at least one tenant
# (the showcase calibrated set for `oneconsu-rest` plus public-doc additions
# that may unlock on tenants with broader permissions).
CANDIDATE_IMOVEL_LIST_FIELDS: list[Any] = [
    "Codigo", "TituloSite", "Categoria", "Finalidade", "Status",
    "Cidade", "Bairro", "Endereco", "CEP", "UF", "Estado",
    "ValorVenda", "ValorLocacao",
    "AreaTotal", "AreaPrivativa", "AreaConstruida",
    "Dormitorios", "Suites", "Vagas",
    "Banheiros", "BanheiroSocial",
    "Foto", "FotoDestaque", "FotoPrincipal",
    "Latitude", "Longitude",
    "DataCadastro", "DataAtualizacao",
    "Slug", "PalavrasChave", "CodigoImobiliaria",
    # Nested relation — sub-field set is showcase-proven on `oneconsu-rest`.
    # Other tenants may accept additional sub-fields (Fone, Creci) — Phase 2
    # adds nested-sub-field calibration.
    {"Corretor": ["Nome", "Email"]},
]

CANDIDATE_IMOVEL_DETAIL_FIELDS: list[Any] = [
    "Codigo", "TituloSite", "Categoria", "Finalidade", "Status",
    "Cidade", "Bairro", "Endereco", "Numero", "Complemento", "CEP", "UF", "Estado",
    "ValorVenda", "ValorLocacao",
    "AreaTotal", "AreaPrivativa", "AreaConstruida",
    "Dormitorios", "Suites", "Vagas",
    "Banheiros", "BanheiroSocial",
    "Latitude", "Longitude",
    "DataCadastro", "DataAtualizacao",
    "Caracteristicas",
    "Empreendimento", "Construtora",
    {"Corretor": ["Nome", "Email", "Fone"]},
]

CANDIDATE_USUARIO_FIELDS: list[str] = [
    "Codigo", "Nome", "Email", "Foto", "FotoPequena", "Setor",
    "Apelido", "Login", "DataCadastro", "CodigoImobiliaria",
]

CANDIDATE_AGENCIA_FIELDS: list[str] = [
    "Codigo", "Nome", "Endereco", "Cidade", "Bairro", "Site",
    "Estado", "UF", "CEP", "Telefone", "Email", "Foto", "Logo",
    "Status", "DataCadastro",
]

CANDIDATE_CONTEUDO_FIELDS: list[str] = ["Status", "Categoria", "Cidade", "Bairro"]

# Floor — if calibration drops everything except the primary id, this is
# what survives. Used as a sentinel to abort the probe loop.
FLOOR_FIELDS: list[Any] = ["Codigo"]


# ─── Calibrator ──────────────────────────────────────────────────────────


@dataclass
class CalibrationResult:
    """The cached outcome of one calibration pass for one endpoint family."""

    endpoint: str
    safe_fields: list[Any]
    rejected: list[str] = field(default_factory=list)
    calibrated_at: Optional[str] = None  # ISO timestamp


class Calibrator:
    """Per-process cache of per-tenant safe field sets.

    Lazy: the first call to `get_*_fields` triggers the probe; subsequent
    calls use the cache. Concurrent first-callers are serialized via per-key
    `asyncio.Lock` so we don't probe the same endpoint N times in parallel.
    """

    def __init__(self) -> None:
        self._cache: dict[str, CalibrationResult] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def reset(self, key: Optional[str] = None) -> None:
        """Invalidate the cache. With no key, clears all."""
        if key is None:
            self._cache.clear()
            self._locks.clear()
        else:
            self._cache.pop(key, None)
            self._locks.pop(key, None)

    def snapshot(self) -> dict[str, CalibrationResult]:
        """Read-only view for diagnostics."""
        return dict(self._cache)

    # ─── Public per-endpoint accessors ──────────────────────────────────

    async def get_imovel_list_fields(self, client: VistaClient) -> list[Any]:
        return await self._calibrate(
            client,
            cache_key="imoveis_list",
            endpoint="/imoveis/listar",
            candidates=CANDIDATE_IMOVEL_LIST_FIELDS,
            requester=lambda fields: client.listar_imoveis(
                fields=fields, page=1, page_size=1
            ),
        )

    async def get_imovel_detail_fields(self, client: VistaClient) -> list[Any]:
        # Detail probing requires a real Codigo. We use the lightest-weight
        # sample: probe listar first (already cached after first imoveis call),
        # take its first Codigo, then probe detalhes.
        list_fields = await self.get_imovel_list_fields(client)
        try:
            list_call = await client.listar_imoveis(
                fields=list_fields, page=1, page_size=1
            )
        except VistaUpstreamError as e:
            logger.warning(
                "calibration: cannot probe detail fields — listar failed: %s", e
            )
            return list(FLOOR_FIELDS)
        items = []
        if isinstance(list_call.data, dict):
            for k, v in list_call.data.items():
                if k in {"total", "paginas", "pagina", "quantidade"}:
                    continue
                if isinstance(v, dict):
                    items.append(v)
                    break
        if not items:
            logger.warning(
                "calibration: listar returned 0 imoveis — cannot probe detail fields"
            )
            return list(FLOOR_FIELDS)
        sample_codigo = items[0].get("Codigo") or "CA2830"

        return await self._calibrate(
            client,
            cache_key="imoveis_detail",
            endpoint="/imoveis/detalhes",
            candidates=CANDIDATE_IMOVEL_DETAIL_FIELDS,
            requester=lambda fields: client.detalhes_imovel(
                sample_codigo, fields=fields
            ),
        )

    async def get_imovel_conteudo_fields(self, client: VistaClient) -> list[str]:
        result = await self._calibrate(
            client,
            cache_key="imoveis_conteudo",
            endpoint="/imoveis/listarConteudo",
            candidates=CANDIDATE_CONTEUDO_FIELDS,
            requester=lambda fields: client.listar_conteudo_imoveis(fields=fields),
        )
        # listarConteudo only takes plain strings — drop any nested dicts.
        return [f for f in result if isinstance(f, str)]

    async def get_usuario_fields(self, client: VistaClient) -> list[str]:
        result = await self._calibrate(
            client,
            cache_key="usuarios",
            endpoint="/usuarios/listar",
            candidates=CANDIDATE_USUARIO_FIELDS,
            requester=lambda fields: client.listar_usuarios(fields=fields),
        )
        return [f for f in result if isinstance(f, str)]

    async def get_agencia_fields(self, client: VistaClient) -> list[str]:
        result = await self._calibrate(
            client,
            cache_key="agencias",
            endpoint="/agencias/listar",
            candidates=CANDIDATE_AGENCIA_FIELDS,
            requester=lambda fields: client.listar_agencias(fields=fields),
        )
        return [f for f in result if isinstance(f, str)]

    # ─── Core probe loop ────────────────────────────────────────────────

    async def _calibrate(
        self,
        client: VistaClient,
        *,
        cache_key: str,
        endpoint: str,
        candidates: list[Any],
        requester,
    ) -> list[Any]:
        cached = self._cache.get(cache_key)
        if cached is not None:
            return list(cached.safe_fields)

        async with self._lock(cache_key):
            # Re-check after acquiring lock — another coroutine may have
            # finished while we were waiting.
            cached = self._cache.get(cache_key)
            if cached is not None:
                return list(cached.safe_fields)

            if not client.configured:
                # Don't probe with no key — return the floor and don't cache.
                logger.info(
                    "calibration[%s]: client not configured; returning floor", cache_key
                )
                return list(FLOOR_FIELDS)

            current = list(candidates)
            rejected: list[str] = []
            max_iterations = len(candidates) + 2  # safety bound
            for i in range(max_iterations):
                if not current:
                    break
                try:
                    await requester(current)
                except VistaFieldNotAvailable as e:
                    field_name = e.field
                    if field_name == "<unknown>":
                        # Can't recover — bail to floor and record what we had.
                        logger.warning(
                            "calibration[%s]: 400 with unparseable field; falling back to floor",
                            cache_key,
                        )
                        current = list(FLOOR_FIELDS)
                        break
                    rejected.append(field_name)
                    current = _drop_field(current, field_name)
                    if not current or current == FLOOR_FIELDS:
                        break
                    continue
                except (VistaConfigError, VistaUpstreamError) as e:
                    logger.warning(
                        "calibration[%s]: probe failed with non-field error %s; using current set",
                        cache_key, type(e).__name__,
                    )
                    break
                else:
                    # Success — cache and return.
                    break
            else:
                logger.warning(
                    "calibration[%s]: hit max iterations (%d); using current set",
                    cache_key, max_iterations,
                )

            now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            self._cache[cache_key] = CalibrationResult(
                endpoint=endpoint,
                safe_fields=list(current),
                rejected=rejected,
                calibrated_at=now_iso,
            )
            logger.info(
                "calibration[%s]: %d safe / %d rejected",
                cache_key, len(current), len(rejected),
            )
            return list(current)


def _drop_field(fields: list[Any], name: str) -> list[Any]:
    """Drop a field by name from the candidate list.

    Handles three shapes:
    - Plain string: dropped if equal to `name`.
    - Nested relation `{"Relation": ["sub1", "sub2", ...]}`: dropped entirely
      if `name == "Relation"`. If `name` is a sub-field, the relation is
      kept but `name` is removed from its sub-list. If the sub-list becomes
      empty, the relation is dropped entirely.
    """
    out: list[Any] = []
    for f in fields:
        if isinstance(f, str):
            if f != name:
                out.append(f)
        elif isinstance(f, dict):
            if name in f:
                # Top-level relation match — drop the whole relation.
                continue
            # Check if `name` is a sub-field of any relation.
            new_dict = {}
            modified = False
            for rel_name, sub_fields in f.items():
                if isinstance(sub_fields, list) and name in sub_fields:
                    pruned = [s for s in sub_fields if s != name]
                    modified = True
                    if pruned:
                        new_dict[rel_name] = pruned
                else:
                    new_dict[rel_name] = sub_fields
            if modified:
                if new_dict:
                    out.append(new_dict)
                # else: every sub-list became empty, drop the relation
            else:
                out.append(f)
        else:
            out.append(f)
    return out


# Module-level singleton — one cache per process is the right scope. If
# multi-tenant multi-key lands later, swap this for a {tenant_key: Calibrator}
# map keyed by the API key hash.
calibrator = Calibrator()


__all__ = [
    "Calibrator",
    "CalibrationResult",
    "calibrator",
    "FLOOR_FIELDS",
]
