"""The real-estate catalogue: social-wiring's ``julia_ferramenta`` read tools behind :class:`CatalogoOpcoes`.

This is where the SW call (timeout, failure -> ``None``) and the criterion -> SW search-parameter mapping live; the
real-estate tools (``oferecer_imoveis`` / ``detalhes_imovel``) and the generic ones (``oferecer_opcoes`` /
``detalhes_opcao``) both go through it.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from app.catalogos.protocolo import Busca, codigo_origem_do_estado, opcao_de_item, perfil_como_texto
from app.clients.social_wiring import JULIA_TOOL_TIMEOUT_SECONDS, SocialWiringClient

logger = logging.getLogger(__name__)

__all__ = ["BUSCA_META", "ImoveisSwCatalogo", "consulta_sw"]

#: The sibling keys of a ``buscar_imoveis`` answer (SW CONTRACT 8.3, v2) the model must see next to the listings:
#: how many more pass (``restantes_estimados``), which axes SW widened to fill the batch (``relaxado`` -- the agent
#: must say what was widened, never present a widened result as an exact match), whether the campaign anchor was
#: found (``similar_a_encontrado``), and the asked items SW's catalogue cannot verify (``itens_nao_verificaveis``:
#: they did not filter the result, the agent confirms them with the lead / broker). Anything else SW adds is NOT
#: forwarded (explicit allowlist).
BUSCA_META = ("restantes_estimados", "relaxado", "similar_a_encontrado", "itens_nao_verificaveis")


def consulta_sw(valores: Mapping[str, Any]) -> dict[str, Any]:
    """The SW search arguments from the lead's COMPUTED values.

    NOC-REMEDIATE[julia-v2-consulta-sw-mapa]: the criterion -> SW parameter mapping is keyed by the v1
    standard's criterion keys here; it belongs on the criterion row (a ``param_sw`` column of
    ``qualificacao_criterios``) so a renamed criterion cannot silently stop filtering -- 2026-10-19
    """
    q: dict[str, Any] = {}
    if valores.get("operacao") in ("compra", "aluguel"):
        q["operacao"] = valores["operacao"]
    if isinstance(valores.get("tipo_imovel"), str):
        q["tipo"] = valores["tipo_imovel"]
    faixa = valores.get("faixa_preco")
    if isinstance(faixa, dict):
        if "min" in faixa:
            q["preco_min"] = faixa["min"]
        if "max" in faixa:
            q["preco_max"] = faixa["max"]
    for src, dst in (("quartos_min", "quartos_min"), ("vagas_min", "vagas_min")):
        if isinstance(valores.get(src), (int, float)) and not isinstance(valores.get(src), bool):
            q[dst] = int(valores[src])
    reg = valores.get("regioes")
    if isinstance(reg, str) and reg.strip():
        q["bairros"] = [reg.strip()]
    elif isinstance(reg, list) and reg:
        q["bairros"] = [str(r) for r in reg][:10]
    # nice-to-haves (SW ranks by them and relaxes them first) vs MUST-haves (SW hard filters, never relaxed)
    for src, dst in (("caracteristicas", "caracteristicas"), ("itens_essenciais", "itens_essenciais")):
        if isinstance(valores.get(src), list) and valores[src]:
            q[dst] = [str(c) for c in valores[src]][:20]
    return q


class ImoveisSwCatalogo:
    """``CatalogoOpcoes`` over a :class:`SocialWiringClient` (the org's token is the client's concern)."""

    chave = "imoveis_sw"

    def __init__(self, sw: SocialWiringClient) -> None:
        self._sw = sw

    async def _chamar(self, org_id: UUID, nome: str, args: dict[str, Any]) -> dict[str, Any] | None:
        try:
            body = await asyncio.wait_for(self._sw.julia_ferramenta(org_id, nome, args), JULIA_TOOL_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 -- a catalogue failure is a result, never a crashed turn
            logger.warning("agents.channel.sw_tool_failed org_id=%s tool=%s error=%s", org_id, nome, type(exc).__name__)
            return None
        if not isinstance(body, dict) or body.get("erro"):
            return None
        return body

    @staticmethod
    def _itens(body: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        return tuple(i for i in (body.get("data") or []) if isinstance(i, dict) and str(i.get("codigo") or "").strip())

    def origem(self, estado: Any) -> str | None:
        return codigo_origem_do_estado(estado)

    async def buscar_origem(self, org_id: UUID, codigo: str, *, interacao_id: str | None = None) -> Busca | None:
        body = await self._chamar(org_id, "imovel_campanha", {"codigo": codigo})
        return None if body is None else Busca(self._itens(body), {k: body[k] for k in BUSCA_META if k in body})

    async def buscar(
        self, org_id: UUID, *, perfil: Mapping[str, Any], excluir: Sequence[str], limite: int,
        similar_a: str | None = None, interacao_id: str | None = None,
    ) -> Busca | None:
        args = consulta_sw(perfil)
        if similar_a:
            args["similar_a"] = similar_a
        args["excluir_codigos"] = list(excluir)[-200:]
        args["limite"] = limite
        if interacao_id:
            args["interacao_id"] = interacao_id
        body = await self._chamar(org_id, "buscar_imoveis", args)
        return None if body is None else Busca(self._itens(body), {k: body[k] for k in BUSCA_META if k in body})

    async def detalhar(
        self, org_id: UUID, codigo: str, *, interacao_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        body = await self._chamar(org_id, "detalhes_imovel", {"codigo": codigo, **({"interacao_id": interacao_id} if interacao_id else {})})
        if body is None:
            return None
        item = body.get("data") if isinstance(body.get("data"), dict) else body
        return item

    def perfil_texto(self, perfil: Mapping[str, Any]) -> str:
        return perfil_como_texto(consulta_sw(perfil))

    def opcao(self, item: Mapping[str, Any]) -> dict[str, Any]:
        return opcao_de_item(item)
