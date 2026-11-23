"""The eval-loop REFINE step, orchestration (owner 2026-11-19; contract: ``products/agents/docs/eval-loop-gate-contract.md`` § Refine step).

After a round of an AUTOMATIC loop closes below the target without stopping the loop, the driver calls :meth:`RefinoService.refinar`
before it books the next round. One pass:

1. is there a round to refine from? (:func:`~app.studio.eval_loop_refino.deve_refinar`: active automatic loop, last closed round
   measured, below target, failing cases, no refine decision for that round yet);
2. is the draft still what that round measured? (someone edited it meanwhile -> the step stands down: it never races a human);
3. read the failing cases of the round + the loop agent's OWN draft rows;
4. ask the refiner (an LLM call through the seed entry points) for ONE bounded edit, capped by what the loop budget has left;
5. validate it (:func:`~app.studio.eval_loop_refino.validar_proposta`); 6. write it to the DRAFT and record the event + the spend in
   ONE transaction (:class:`~app.stores.studio_eval_refino.RefinoStore`). Never publishes.

Every outcome is an event with its cost: ``refinamento_proposto`` (the diff), ``refinamento_recusado`` (why) or
``refinamento_sem_edicao`` (the refiner found nothing to fix in the prompt: the cases look wrong or hostile, a person should look),
so the spend always reaches the loop budget and the owner can read what the step did and why. A refine never raises into the driver.

Refused BEFORE the model call, at zero cost (red-team hardening 2026-11-19): a base layer (platform-scope definition, or an agent that is the
parent of another: an edit there reaches every agent that inherits it) and a loop that already made :data:`MAX_REFINOS_POR_LOOP` edits.
The rows the loop already edited are not offered to the model again (one edit per row per loop).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

import anyio.to_thread

from app.stores._db_errors import StudioConflict
from app.stores.errors import NotFound
from app.stores.studio_eval_loops import LoopRecord, LoopStore
from app.stores.studio_eval_refino import EscritaLinha, RefinoStore
from app.studio.eval_loop_refinador import EntradaRefino, Refinador
from app.studio.eval_loop_refino import (
    EVENTOS_REFINO, MAX_CASOS, MAX_REFINOS_POR_LOOP, CasoFalhando, RefinoRecusado, deve_refinar, detalhe_proposto, detalhe_recusado,
    detalhe_sem_edicao, linhas_do_rascunho, mensagem_refino, validar_proposta,
)

logger = logging.getLogger(__name__)

__all__ = ["RefinoService", "MIN_ORCAMENTO_REFINO_USD"]

#: below this much budget left the step does not even try (the next round would find the budget spent)
MIN_ORCAMENTO_REFINO_USD = 0.02

#: what the RPC refuses by itself (nothing was written): recorded as a refusal, the model call was paid for
_CONFLITOS_SEM_GRAVAR = frozenset({
    "conflito_de_versao", "linha_alterada", "loop_encerrado", "linha_protegida", "camada_base", "versao_de_outro_agente",
    "limite_de_refinos", "linha_ja_refinada"})

LerCasos = Callable[[LoopRecord, UUID], list[CasoFalhando]]
#: re-stamp the draft's ``compiled_hash`` from a fresh compile (``_refresh_draft_hash``) and return the hash: ``(agent_id, draft_id)``
CarimbarHash = Callable[[UUID, UUID, UUID], str]


class RefinoService:
    def __init__(
        self, *, loops: LoopStore, defs: Any, refinador: Refinador, refino: RefinoStore, ler_casos: LerCasos,
        carimbar_hash: CarimbarHash,
    ) -> None:
        self._loops = loops
        self._defs = defs
        self._refinador = refinador
        self._refino = refino
        self._ler_casos = ler_casos
        self._carimbar_hash = carimbar_hash

    async def refinar(self, rec: LoopRecord) -> str:
        """Run one refine pass if one is due. Returns ``nada`` | ``proposto`` | ``sem_edicao`` | ``recusado:<codigo>`` | ``ja_registrado`` (tests / logs).
        Never raises: an unexpected failure is logged and the loop carries on (it re-measures, as it did before this step existed)."""
        try:
            return await self._refinar(rec)
        except Exception:  # noqa: BLE001 -- the step must never take the driver down; logged with the traceback
            logger.exception("agents.eval_loop.refino_falhou loop_id=%s", rec.id)
            return "erro"

    async def _refinar(self, rec: LoopRecord) -> str:
        t = anyio.to_thread.run_sync
        rodadas = await t(lambda: self._loops.list_rodadas(rec.org_id, rec.id))
        eventos = await t(lambda: self._loops.listar_eventos(rec.org_id, rec.id, eventos=EVENTOS_REFINO, limite=1000))
        base = deve_refinar(status=rec.status, modo=rec.modo, alvo=rec.alvo, rodadas=rodadas, eventos=eventos)
        if base is None:
            return "nada"
        # the budget as it stands NOW (a round just closed and added its cost)
        rec = await t(lambda: self._loops.get_loop(rec.org_id, rec.agent_id, rec.id))
        if rec.status != "ativo":
            return "nada"

        async def recusar(codigo: str, *, custo: float = 0.0, mensagem: str | None = None, modelo: str | None = None, n: int = 0) -> str:
            det = detalhe_recusado(codigo, mensagem or mensagem_refino(codigo), suite=rec.suite, score_base=base.score,
                                   hash_base=base.compiled_hash, custo_usd=custo, modelo=modelo, n_casos_falhando=n)
            try:
                await t(lambda: self._refino.registrar(
                    rec.org_id, rec.id, base.seq, evento="refinamento_recusado", detalhe=det, custo_usd=custo, escrita=None))
            except StudioConflict as exc:
                if exc.code == "refino_ja_registrado":
                    return "ja_registrado"
                raise
            return f"recusado:{codigo}"

        async def sem_edicao(motivo: str, suspeitos: list[str], *, custo: float, modelo: str | None, n: int) -> str:
            det = detalhe_sem_edicao(motivo, suspeitos, suite=rec.suite, score_base=base.score, hash_base=base.compiled_hash,
                                     custo_usd=custo, modelo=modelo, n_casos_falhando=n)
            try:
                await t(lambda: self._refino.registrar(
                    rec.org_id, rec.id, base.seq, evento="refinamento_sem_edicao", detalhe=det, custo_usd=custo, escrita=None))
            except StudioConflict as exc:
                if exc.code == "refino_ja_registrado":
                    return "ja_registrado"
                raise
            return "sem_edicao"

        try:
            agent = await t(lambda: self._defs.get_agent_by_id(rec.agent_id))
        except NotFound:
            return await recusar("agente_sem_linhas")
        if agent.definition_scope == "instancia" or agent.definition_mode != "studio" or agent.conteudo_modo != "linhas":
            return await recusar("agente_sem_linhas")
        # a base layer = the parent of another agent (an edit there reaches every inheritor); platform scope alone is NOT one
        irmaos = await t(lambda: self._defs.list_agents(rec.org_id))
        if any(a.pai_agent_id == agent.id for a in irmaos):
            return await recusar("camada_base")
        propostos = [e for e in eventos if e.get("evento") == "refinamento_proposto"]
        if len(propostos) >= MAX_REFINOS_POR_LOOP:
            return await recusar("limite_de_refinos")
        # the rows this loop already edited, with their text as it was when the loop started (the first edit's ``antes``)
        ja_refinadas: dict[tuple[str, str], str] = {}
        for e in propostos:
            d = e.get("detalhe") or {}
            alvo_e = d.get("alvo") or {}
            if alvo_e.get("tipo") and alvo_e.get("chave"):
                ja_refinadas.setdefault((alvo_e["tipo"], alvo_e["chave"]), str((d.get("diff") or {}).get("antes") or ""))
        draft = await t(lambda: self._defs.get_draft(rec.org_id, rec.agent_id))
        if draft is None:
            return await recusar("sem_rascunho")
        hash_atual = await t(lambda: self._carimbar_hash(rec.org_id, rec.agent_id, draft.id))
        if hash_atual != base.compiled_hash:
            return await recusar("rascunho_alterado")

        todos = await t(lambda: self._ler_casos(rec, base.run_id))
        if not todos:
            return await recusar("sem_casos")
        casos = tuple(todos[:MAX_CASOS])
        if _tem_pii(casos):
            return await recusar("pii_nos_casos", n=len(todos))
        linhas = await t(lambda: linhas_do_rascunho(self._defs, rec.org_id, draft.id, hash_atual))

        restante = rec.definicao().restante_usd
        if restante < MIN_ORCAMENTO_REFINO_USD:
            return await recusar("orcamento_insuficiente", n=len(todos))
        entrada = EntradaRefino(
            org_id=rec.org_id, agente_chave=rec.agente_chave, suite=rec.suite, rodada=base.seq, score=base.score, alvo=rec.alvo,
            casos=casos, linhas=linhas.sem(ja_refinadas))
        try:
            res = await self._refinador.propor(entrada, limite_usd=restante)
        except Exception:  # noqa: BLE001 -- a refiner crash costs nothing we can measure; logged, recorded as a refusal
            logger.exception("agents.eval_loop.refinador_falhou loop_id=%s", rec.id)
            return await recusar("refinador_falhou", n=len(todos))
        if res.saida is None:
            return await recusar(res.codigo or "saida_invalida", custo=res.custo_usd, modelo=res.modelo, n=len(todos))
        if res.saida.sem_edicao:
            slugs = {x.slug for x in todos}
            return await sem_edicao(res.saida.motivo or "", [c for c in res.saida.casos_suspeitos if c in slugs],
                                    custo=res.custo_usd, modelo=res.modelo, n=len(todos))
        try:
            proposta = validar_proposta(res.saida, linhas, casos, ja_refinadas=ja_refinadas)
        except RefinoRecusado as exc:
            return await recusar(exc.code, custo=res.custo_usd, mensagem=exc.mensagem, modelo=res.modelo, n=len(todos))

        det = detalhe_proposto(proposta, suite=rec.suite, score_base=base.score, hash_base=base.compiled_hash,
                               custo_usd=res.custo_usd, modelo=res.modelo, n_casos_falhando=len(todos), version_id=draft.id)
        escrita = EscritaLinha(
            version_id=draft.id, tipo=proposta.tipo, chave=proposta.chave, antes=proposta.antes, depois=proposta.depois,
            expected_hash=hash_atual)
        try:
            await t(lambda: self._refino.registrar(
                rec.org_id, rec.id, base.seq, evento="refinamento_proposto", detalhe=det, custo_usd=res.custo_usd, escrita=escrita))
        except StudioConflict as exc:
            if exc.code == "refino_ja_registrado":
                return "ja_registrado"
            if exc.code in _CONFLITOS_SEM_GRAVAR:
                # nothing was written (one transaction): record the refusal, the model call was paid for
                return await recusar(exc.code, custo=res.custo_usd, modelo=res.modelo, n=len(todos))
            raise
        try:  # the draft changed: re-stamp its hash (the next booking recompiles anyway; a miss is logged, never fatal)
            await t(lambda: self._carimbar_hash(rec.org_id, rec.agent_id, draft.id))
        except Exception:  # noqa: BLE001
            logger.warning("agents.eval_loop.refino_hash_nao_atualizado loop_id=%s", rec.id, exc_info=True)
        return "proposto"


def _tem_pii(casos: tuple[CasoFalhando, ...]) -> bool:
    from app.studio.eval_pii import achar_pii

    for c in casos:
        textos = [*c.textos_livres(), json.dumps(c.esperado, ensure_ascii=False, default=str) if c.esperado is not None else ""]
        if any(achar_pii(x) for x in textos if x):
            return True
    return False

