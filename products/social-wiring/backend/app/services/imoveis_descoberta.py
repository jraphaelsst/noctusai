"""Discovery of NEW Vista listings when `/imoveis/listar` cannot enumerate the catalog.

`listar` is the only endpoint that lists. While it is silent (2026-10-23 on, a Vista-side outage) a new listing can only
be found by other means. Two named seams, each `async (adapter, conhecidos, report) -> {codigo: Imovel | None}` (the
imóvel when the discoverer already fetched it -- the forward probe does -- else None so the walk fetches it); the day
`listar` returns, the auto path stops calling them and the listar sync enumerates again.

  por_destaques   `/imoveis/destaques` (the featured listings -- at most a handful: a tripwire, not a census)
  por_sonda       a FORWARD PROBE above the highest known numeric suffix of each prefix (ONE####, CA####...): probe
                  prefix+(max+1), +2 ... and stop after `max_falhas` CONSECUTIVE misses. A miss is "does not exist" or
                  "exists but unpublished" (an unpublished record is not a listing we may mirror).

Why a gap-tolerant stop and not "first miss": codes are issued sequentially but a record can be deleted or kept
unpublished, so the sequence has holes. `max_falhas` is the width of the largest hole the probe will cross; the default
(40) is an upper bound chosen conservatively -- see `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/vista.md` § 6c for the measured
gaps. A hole wider than `max_falhas` is invisible until the sequence is probed again after the code issuer passes it.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Awaitable, Callable, Optional

from noctusai_lib.domain.real_estate import Imovel
from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.vista.client import VistaNotFound, VistaRecordUnpublished

logger = logging.getLogger(__name__)

VISTA_RATE_BUCKET = "vista"
#: Consecutive misses after which the forward probe of one prefix stops.
SONDA_MAX_FALHAS_PADRAO = 40
_CODIGO = re.compile(r"^([A-Z]{2,4})(\d{3,6})$")

Descobridor = Callable[[Any, set[str], Any], Awaitable[dict[str, Optional[Imovel]]]]


def maiores_por_prefixo(conhecidos: set[str]) -> dict[str, tuple[int, int]]:
    """prefix -> (highest numeric suffix, digit width) over the known codes (only `PPP####`-shaped ones count)."""
    out: dict[str, tuple[int, int]] = {}
    for codigo in conhecidos:
        m = _CODIGO.match(codigo.strip().upper())
        if not m:
            continue
        prefixo, digitos = m.group(1), m.group(2)
        atual = out.get(prefixo)
        if atual is None or int(digitos) > atual[0]:
            out[prefixo] = (int(digitos), len(digitos))
    return out


async def por_destaques(adapter: Any, conhecidos: set[str], report: Any) -> dict[str, Optional[Imovel]]:
    """Featured codes not yet in the mirror."""
    await rate_limit.acquire_async(VISTA_RATE_BUCKET)
    report.chamadas["destaques"] = report.chamadas.get("destaques", 0) + 1
    codigos = await adapter.list_destaques()
    return {c: None for c in codigos if c.strip().upper() not in conhecidos}


def criar_sonda(max_falhas: int = SONDA_MAX_FALHAS_PADRAO) -> Descobridor:
    """The forward probe as a `Descobridor` with `max_falhas` bound."""

    async def por_sonda(adapter: Any, conhecidos: set[str], report: Any) -> dict[str, Optional[Imovel]]:
        achados: dict[str, Optional[Imovel]] = {}

        async def varrer(prefixo: str, maior: int, largura: int) -> None:
            falhas, n = 0, maior
            while falhas < max_falhas:
                n += 1
                codigo = f"{prefixo}{n:0{largura}d}"
                await rate_limit.acquire_async(VISTA_RATE_BUCKET)
                report.chamadas["sonda"] = report.chamadas.get("sonda", 0) + 1
                try:
                    imovel = await adapter.refresh_imovel(codigo)
                except (VistaNotFound, VistaRecordUnpublished):
                    falhas += 1
                    continue
                except Exception as exc:  # a transport failure is not a miss: stop THIS prefix, say so
                    report.sonda_falhas.append(f"{codigo}: {type(exc).__name__}")
                    logger.warning("imoveis probe: %s failed (%s) -- prefix %s stopped", codigo, type(exc).__name__, prefixo)
                    return
                falhas = 0
                achados[codigo] = imovel

        await asyncio.gather(*(varrer(p, m, w) for p, (m, w) in maiores_por_prefixo(conhecidos).items()))
        return achados

    return por_sonda


__all__ = ["Descobridor", "SONDA_MAX_FALHAS_PADRAO", "criar_sonda", "maiores_por_prefixo", "por_destaques"]
