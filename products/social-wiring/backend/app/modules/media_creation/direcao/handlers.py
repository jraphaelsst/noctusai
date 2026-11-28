"""Step handlers of the ``reel_dirigido`` route: the Diretor de Edição's stages over the four seams.

A handler receives a seed ``StepContext`` (its dependencies' outputs under their step names) and returns a ``StepResult``
carrying MEASURED figures. The handlers decide NOTHING audiovisual: they call a port, validate what came back with the
decision-free guards, and record. Failures are coded ``StepError`` (``falhou(codigo)`` on the card); a message never carries
script text.

* Ports are blocking: each call runs in a thread; a ``DirecaoError`` becomes a coded ``StepError`` (retryable when it says so).
* A local / deterministic stage records an explicit ``custo_usd = 0`` (a fact). A stage whose port reports no cost leaves it
  ``None`` and the runner names it ``nao_medido`` -- never an estimate.
* A synthetic (Fake) result is refused at ``checagens`` unless ``permitir_sintetico`` (a test / local-dev opt-in): a Fake never
  reaches the review queue.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Optional

from noctusai_lib.domain.media_production import StepContext, StepError, StepRegistry, StepResult

from app.modules.media_creation.direcao import passos as ps
from app.modules.media_creation.direcao.portas import Adaptadores, DirecaoError
from app.modules.media_creation.direcao.tipos import EntradaCongelada, EstiloRef, MidiaGerada, Montagem, PlanoDeCenas
from app.modules.media_creation.direcao.validacao import (
    Alvos,
    avaliar_medicoes,
    avisos_nao_medidos,
    cobertura,
    validar_plano,
)

logger = logging.getLogger(__name__)

SEM_FALA = "roteiro_sem_fala"
ENTRADA_INVALIDA = "entrada_invalida"
PLANO_INVALIDO = "plano_invalido"
SAIDA_SINTETICA = "saida_sintetica"
CHECAGEM_REPROVADA = "checagem_reprovada"
PASSO_ANTERIOR_SEM_SAIDA = "passo_anterior_sem_saida"

#: ``registrar_asset(org_id, post_id, arquivo_chave, medicoes) -> {"id": ...}``: the product registers the assembled file as
#: the post's media asset (the review UI reads it). Injected: the skeleton never touches storage or ``cs_post_assets``.
RegistrarAsset = Callable[[str, str, str, dict], dict]


@dataclass
class DirecaoDeps:
    adaptadores: Adaptadores
    permitir_sintetico: bool = False
    alvos: Alvos = field(default_factory=Alvos)
    registrar_asset: Optional[RegistrarAsset] = None


async def _porta(fn: Callable[..., Any], *args: Any) -> Any:
    try:
        return await asyncio.to_thread(fn, *args)
    except DirecaoError as exc:
        raise StepError(exc.codigo, str(exc), retryable=exc.retryable) from exc


def _dep(ctx: StepContext, passo: str, chave: str) -> dict:
    saida = ctx.entradas.get(passo)
    if not saida or chave not in saida:
        raise StepError(PASSO_ANTERIOR_SEM_SAIDA, f"{passo} não produziu {chave}")
    return saida[chave]


def build_handlers_direcao(deps: DirecaoDeps) -> StepRegistry:
    reg = StepRegistry()
    a = deps.adaptadores

    async def recepcao(ctx: StepContext) -> StepResult:
        e = EntradaCongelada.de_dict(ctx.entradas["entrada"])
        if not e.palavras:
            raise StepError(SEM_FALA, "o roteiro não tem texto de fala")
        if e.ids() != [f"w{i}" for i in range(len(e.palavras))] or (e.org_id, e.post_id) != (ctx.org_id, ctx.post_id):
            raise StepError(ENTRADA_INVALIDA, "a entrada congelada não corresponde ao post")
        return StepResult(
            saida={"entrada": e.para_dict()},
            medicoes={"palavras": len(e.palavras), "roteiro_versao": e.roteiro_versao, "roteiro_sha256": e.roteiro_sha256},
            custo_usd=Decimal("0"),
        )

    async def estilo(ctx: StepContext) -> StepResult:
        e = EntradaCongelada.de_dict(_dep(ctx, ps.PASSO_RECEPCAO, "entrada"))
        est: EstiloRef = await _porta(a.resolvedor.resolver, e)
        return StepResult(
            saida={"estilo": est.para_dict()},
            medicoes={"estilo_id": est.id, "estilo_versao": est.versao, "estilo_origem": est.origem},
            custo_usd=Decimal("0"),
        )

    async def plano(ctx: StepContext) -> StepResult:
        e = EntradaCongelada.de_dict(_dep(ctx, ps.PASSO_RECEPCAO, "entrada"))
        est = EstiloRef.de_dict(_dep(ctx, ps.PASSO_ESTILO, "estilo"))
        p: PlanoDeCenas = await _porta(a.planejador.planejar, e, est)
        violacoes = validar_plano(e, p)
        if violacoes:
            logger.warning("direcao.plano_invalido post=%s violacoes=%s", ctx.post_id, [str(v) for v in violacoes])
            raise StepError(PLANO_INVALIDO, ",".join(sorted({v.codigo for v in violacoes})))
        return StepResult(
            saida={"plano": p.para_dict()},
            vendor=p.planejador, modelo=p.versao,
            medicoes={"planejador": p.planejador, "versao": p.versao, "n_cenas": len(p.cenas), **cobertura(e, p)},
            custo_usd=p.custo_usd,
        )

    async def midia(ctx: StepContext) -> StepResult:
        e = EntradaCongelada.de_dict(_dep(ctx, ps.PASSO_RECEPCAO, "entrada"))
        p = PlanoDeCenas.de_dict(_dep(ctx, ps.PASSO_PLANO, "plano"))
        m: MidiaGerada = await _porta(a.gerador.gerar, e, p)
        return StepResult(
            saida={"midia": m.para_dict()}, vendor=m.gerador, modelo=m.versao, request_id=m.request_id,
            unidades=m.unidades or None, custo_usd=m.custo_usd,
        )

    async def montagem(ctx: StepContext) -> StepResult:
        e = EntradaCongelada.de_dict(_dep(ctx, ps.PASSO_RECEPCAO, "entrada"))
        p = PlanoDeCenas.de_dict(_dep(ctx, ps.PASSO_PLANO, "plano"))
        m = MidiaGerada.de_dict(_dep(ctx, ps.PASSO_MIDIA, "midia"))
        mt: Montagem = await _porta(a.montador.montar, e, p, m)
        return StepResult(
            saida={"montagem": mt.para_dict()}, vendor=mt.montador, modelo=mt.versao,
            medicoes=dict(mt.medicoes), custo_usd=mt.custo_usd,
        )

    async def checagens(ctx: StepContext) -> StepResult:
        m = MidiaGerada.de_dict(_dep(ctx, ps.PASSO_MIDIA, "midia"))
        mt = Montagem.de_dict(_dep(ctx, ps.PASSO_MONTAGEM, "montagem"))
        if (m.sintetico or mt.sintetico) and not deps.permitir_sintetico:
            raise StepError(SAIDA_SINTETICA, "a saída é sintética e não pode ir para revisão")
        violacoes = avaliar_medicoes(mt.medicoes, deps.alvos)
        if violacoes:
            logger.warning("direcao.checagem_reprovada post=%s violacoes=%s", ctx.post_id, [str(v) for v in violacoes])
            raise StepError(CHECAGEM_REPROVADA, ",".join(sorted({v.codigo for v in violacoes})))
        avisos = avisos_nao_medidos(mt.medicoes)
        return StepResult(
            saida={"checagens": {"ok": True, "avisos_nao_medidos": avisos}},
            medicoes={"avisos_nao_medidos": avisos}, custo_usd=Decimal("0"),
        )

    async def pacote(ctx: StepContext) -> StepResult:
        e = EntradaCongelada.de_dict(_dep(ctx, ps.PASSO_RECEPCAO, "entrada"))
        p = PlanoDeCenas.de_dict(_dep(ctx, ps.PASSO_PLANO, "plano"))
        m = MidiaGerada.de_dict(_dep(ctx, ps.PASSO_MIDIA, "midia"))
        mt = Montagem.de_dict(_dep(ctx, ps.PASSO_MONTAGEM, "montagem"))
        chk = _dep(ctx, ps.PASSO_CHECAGENS, "checagens")
        asset_id = None
        if deps.registrar_asset is not None:
            asset = await asyncio.to_thread(deps.registrar_asset, ctx.org_id, ctx.post_id, mt.arquivo_chave, dict(mt.medicoes))
            asset_id = asset.get("id")
        pac = {
            "arquivo_chave": mt.arquivo_chave, "asset_id": asset_id, "sintetico": bool(m.sintetico or mt.sintetico),
            "estilo": p.estilo.para_dict(), "planejador": {"id": p.planejador, "versao": p.versao},
            "gerador": {"id": m.gerador, "versao": m.versao}, "montador": {"id": mt.montador, "versao": mt.versao},
            "n_cenas": len(p.cenas), "medicoes": dict(mt.medicoes), "avisos_nao_medidos": chk["avisos_nao_medidos"],
            "roteiro_versao": e.roteiro_versao, "roteiro_sha256": e.roteiro_sha256,
        }
        return StepResult(saida={"pacote": pac}, medicoes={"asset_id": asset_id}, custo_usd=Decimal("0"))

    reg.register_step(ps.PASSO_RECEPCAO, recepcao)
    reg.register_step(ps.PASSO_ESTILO, estilo)
    reg.register_step(ps.PASSO_PLANO, plano)
    reg.register_step(ps.PASSO_MIDIA, midia)
    reg.register_step(ps.PASSO_MONTAGEM, montagem)
    reg.register_step(ps.PASSO_CHECAGENS, checagens)
    reg.register_step(ps.PASSO_PACOTE, pacote)
    return reg


__all__ = ["DirecaoDeps", "RegistrarAsset", "build_handlers_direcao"]
