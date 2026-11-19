"""The chat saga's steps 4-7 for BOTH directions (``specs/estruturas-contract.md`` 9.2 steps 4-7 and 16.6).

Plugged into :attr:`FluxoService.continuacao` by ``routers/chat.py``: it runs after the claim, the save (headline or
roteiro) and the pre-flight, holding the lease. The roteiro-first headline step and the finalizer run as queue jobs
(``services/fluxo_finalizar.py``), which re-enter the SAME step functions here (:meth:`SagaFluxo.concluir`).

Headline-first: 4 roteiro (``RoteiroService.create``; lookup first) -> 5 card (``EsteiraService.criar`` + ``vincular_roteiro``;
an existing card is adopted) -> 6 finalizer job (``dedupe_key = "fluxo:" + proposta_id``) -> 7 the ``roteiro_gerado``
message, once.
Roteiro-first: 4 the headline job (``fluxo.headline_do_roteiro``; ``dedupe_key = "fluxo-h:" + proposta_id``, a re-click
after ``headline_invalida`` uses the next attempt key) -> the job writes the headline and runs 5-7.

Every step is lookup-or-create, so a crash between two steps is repaired by the next click or job tick; progress
(``fluxo_etapa``) and its intent-named event are written by ONE definer RPC per step (``cs_chat_fluxo_registrar``,
migration ``cs_fluxo_saga``): forward-only, the event once. A coded refusal of a step is recorded as ``falhou`` with
its code (the response tells the truth); an unknown failure propagates.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi.concurrency import run_in_threadpool

from noctusai_lib.domain.jobs import JobRepository
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.modules.media_creation.estruturas_formatos import formato_do_post
from app.modules.media_creation.prompts.roteiro_geracao import ESTRUTURA_PADRAO
from app.modules.media_creation.schemas.esteira import PostCreate
from app.modules.media_creation.schemas.roteiros import RoteiroCreate
from app.modules.media_creation.services.esteira_service import EsteiraError, EsteiraService
from app.modules.media_creation.services.post_ref import post_refs
from app.modules.media_creation.services.publicacao_service import PublicacaoService
from app.modules.media_creation.services.roteiro_service import RoteiroError, RoteiroService

logger = logging.getLogger(__name__)

PROPOSTAS = "cs_chat_propostas"
PROPOSTA_ESTRUTURAS = "cs_chat_proposta_estruturas"
MENSAGENS = "cs_chat_mensagens"
EVENTOS = "cs_fluxo_eventos"
ROTEIROS = "cs_roteiros"
REGISTRAR_RPC = "cs_chat_fluxo_registrar"

JOB_FINALIZAR = "fluxo.finalizar_card"
JOB_HEADLINE = "fluxo.headline_do_roteiro"

PROPOSTA_COLS = (
    "id,org_id,marca_id,conversa_id,texto,status,fluxo_etapa,fluxo_erro_codigo,headline_id,tipo,roteiro_id,escolhida_por"
)
ROTEIRO_COLS = "id,marca_id,status,formato,versao,conteudo,headline_id,headline_texto,conversa_id"

MSG_HEADLINE_PRIMEIRO = "Criei o roteiro desta headline e o card na Esteira."
MSG_ROTEIRO_PRIMEIRO = "Salvei este roteiro, criei a headline e o card na Esteira."

#: ``(db, org_id, user_id) -> RoteiroService`` -- the step-4 seam (the router passes the request's cfg / jobs / IA check).
RoteiroFactory = Callable[[Any, str, str], RoteiroService]


def _tipo(proposta: dict[str, Any]) -> str:
    return proposta.get("tipo") or "headline"


def _codigo(detail: Any, padrao: str) -> str:
    if isinstance(detail, dict) and detail.get("code"):
        return str(detail["code"])
    return padrao


def chave_headline(proposta_id: str, tentativa: int) -> str:
    """The headline job's dedupe key: the contract's ``fluxo-h:<id>`` for the first attempt, ``:<n>`` after a failure."""
    return f"fluxo-h:{proposta_id}" if tentativa == 0 else f"fluxo-h:{proposta_id}:{tentativa}"


class SagaFluxo:
    """The step functions, scoped to one org and the user who chose the proposta (``escolhida_por``)."""

    def __init__(self, db: Any, org_id: str, user_id: str, *, jobs: Optional[JobRepository]) -> None:
        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.jobs = jobs

    # ── reads ────────────────────────────────────────────────────────────────────────────────────────

    def proposta(self, proposta_id: str) -> Optional[dict[str, Any]]:
        rows = (
            self.db.table(PROPOSTAS).select(PROPOSTA_COLS).eq("id", proposta_id).eq("org_id", self.org_id).execute().data
        )
        return rows[0] if rows else None

    def estruturas_citadas(self, proposta_id: str) -> list[str]:
        """The proposta's Estruturas, principal first, then by ``ordem``."""
        rows = (
            self.db.table(PROPOSTA_ESTRUTURAS).select("estrutura_id,ordem,principal").eq("proposta_id", proposta_id)
            .execute().data or []
        )
        rows.sort(key=lambda r: (not r.get("principal"), int(r.get("ordem") or 0)))
        return [str(r["estrutura_id"]) for r in rows]

    def roteiro_do_fluxo(self, proposta: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Roteiro-first: the saved script (``roteiro_id``); headline-first: the roteiro of the headline in this chat."""
        q = self.db.table(ROTEIROS).select(ROTEIRO_COLS).eq("org_id", self.org_id)
        if _tipo(proposta) == "roteiro":
            if not proposta.get("roteiro_id"):
                return None
            rows = q.eq("id", str(proposta["roteiro_id"])).limit(1).execute().data
        else:
            if not proposta.get("headline_id"):
                return None
            rows = (
                q.eq("headline_id", str(proposta["headline_id"])).eq("conversa_id", str(proposta["conversa_id"]))
                .order("created_at", desc=True).limit(1).execute().data
            )
        return rows[0] if rows else None

    def post_do_roteiro(self, roteiro_id: str) -> Optional[str]:
        post = post_refs(self.db, self.org_id, "roteiro_id", [roteiro_id]).get(str(roteiro_id))
        return str(post["id"]) if post else None

    def eventos(self, proposta_id: str, tipo: str) -> list[str]:
        rows = (
            self.db.table(EVENTOS).select("codigo,created_at").eq("proposta_id", proposta_id).eq("tipo", tipo)
            .order("created_at").execute().data or []
        )
        return [str(r.get("codigo") or "") for r in rows]

    # ── the one write path for progress ──────────────────────────────────────────────────────────────

    def registrar(
        self, proposta_id: str, tipo: str, *, etapa: Optional[str] = None, erro: Optional[str] = None,
        headline: Optional[str] = None, roteiro: Optional[str] = None, post: Optional[str] = None,
        codigo: Optional[str] = None,
    ) -> dict[str, Any]:
        res = self.db.rpc(REGISTRAR_RPC, {
            "p_proposta": proposta_id, "p_org": self.org_id, "p_user": self.user_id, "p_tipo": tipo, "p_etapa": etapa,
            "p_erro": erro, "p_headline": headline, "p_roteiro": roteiro, "p_post": post, "p_codigo": codigo,
        }).execute()
        data = getattr(res, "data", None)
        if isinstance(data, list):
            data = data[0] if data else None
        return data if isinstance(data, dict) else {}

    # ── step 4 (headline-first): the roteiro ─────────────────────────────────────────────────────────

    async def passo_roteiro(self, proposta: dict[str, Any], roteiros: RoteiroFactory) -> Optional[dict[str, Any]]:
        pid = str(proposta["id"])
        roteiro = await run_in_threadpool(self.roteiro_do_fluxo, proposta)
        if roteiro is None:
            estrutura_ids = await run_in_threadpool(self.estruturas_citadas, pid)
            body = RoteiroCreate(
                marca_id=proposta["marca_id"], headline_id=proposta["headline_id"], headline_texto=proposta["texto"],
                duracao="auto", estrutura=ESTRUTURA_PADRAO, estrutura_ids=estrutura_ids or None, gerar_perguntas=False,
                conversa_id=proposta["conversa_id"],
            )
            try:
                await roteiros(self.db, self.org_id, self.user_id).create(body)
            except RoteiroError as exc:
                codigo = _codigo(exc.detail, "limite_diario_roteiros" if exc.status == 429 else "roteiro_recusado")
                logger.warning("fluxo %s: roteiro recusado (%s)", pid, codigo)
                await run_in_threadpool(self.registrar, pid, "roteiro_falhou", etapa="falhou", erro=codigo, codigo=codigo)
                return None
            roteiro = await run_in_threadpool(self.roteiro_do_fluxo, proposta)
            if roteiro is None:  # created a moment ago: its absence is a bug, never a silent skip
                raise RuntimeError(f"fluxo {pid}: o roteiro criado não foi encontrado")
        await run_in_threadpool(self.registrar, pid, "roteiro_criado", etapa="roteiro_criado", roteiro=str(roteiro["id"]))
        return roteiro

    # ── step 5: the card ─────────────────────────────────────────────────────────────────────────────

    def passo_card(self, proposta: dict[str, Any], roteiro: dict[str, Any]) -> Optional[str]:
        """Lookup-or-create the Esteira card for the roteiro; an existing card holding the headline or the roteiro is
        adopted (409 ``headline_ja_em_post`` / ``roteiro_ja_em_post`` carry its id)."""
        pid, rid = str(proposta["id"]), str(roteiro["id"])
        post_id = self.post_do_roteiro(rid)
        if post_id is None:
            esteira = EsteiraService(self.db, self.org_id, self.user_id)
            try:
                criado = esteira.criar(PostCreate(
                    marca_id=proposta["marca_id"], headline_id=proposta["headline_id"],
                    formato=formato_do_post(roteiro.get("formato") or "reels"),
                ))
                post_id = str(criado["id"])
            except EsteiraError as exc:
                if _codigo(exc.detail, "") == "headline_ja_em_post" and exc.detail.get("post_id"):
                    post_id = str(exc.detail["post_id"])
                else:
                    return self._card_falhou(pid, exc)
            try:
                esteira.vincular_roteiro(post_id, rid)
            except EsteiraError as exc:
                if _codigo(exc.detail, "") == "roteiro_ja_em_post" and exc.detail.get("post_id"):
                    post_id = str(exc.detail["post_id"])
                else:
                    return self._card_falhou(pid, exc)
        # S9: the Diretor's Publicação block (caption, 5 hashtags, first comment) lands on the card while its caption is empty
        PublicacaoService(self.db, self.org_id, self.user_id).aplicar_no_card(proposta, post_id)
        self.registrar(pid, "card_criado", etapa="card_criado", roteiro=rid, post=post_id)
        return post_id

    def _card_falhou(self, proposta_id: str, exc: EsteiraError) -> None:
        codigo = _codigo(exc.detail, "card_recusado")
        logger.warning("fluxo %s: card recusado (%s)", proposta_id, codigo)
        self.registrar(proposta_id, "card_falhou", etapa="falhou", erro=codigo, codigo=codigo)
        return None

    # ── step 6: the finalizer job ────────────────────────────────────────────────────────────────────

    async def passo_finalizador(self, proposta: dict[str, Any]) -> None:
        if self.jobs is None:
            raise RuntimeError("fluxo: sem fila de jobs para o finalizador")
        pid = str(proposta["id"])
        await self.jobs.enqueue(
            type=JOB_FINALIZAR, payload={"proposta_id": pid, "org_id": self.org_id},
            dedupe_key=f"fluxo:{pid}", max_retries=3,
        )

    # ── step 7: the roteiro_gerado message, once ─────────────────────────────────────────────────────

    def passo_mensagem(self, proposta: dict[str, Any]) -> None:
        pid = str(proposta["id"])
        if self.db.table(MENSAGENS).select("id").eq("proposta_id", pid).eq("org_id", self.org_id).execute().data:
            return
        texto = MSG_ROTEIRO_PRIMEIRO if _tipo(proposta) == "roteiro" else MSG_HEADLINE_PRIMEIRO
        try:
            self.db.table(MENSAGENS).insert({
                "id": str(uuid.uuid4()), "org_id": self.org_id, "conversa_id": str(proposta["conversa_id"]),
                "role": "assistant", "conteudo": texto, "referencias": [], "status": "completa", "truncada": False,
                "tipo": "roteiro_gerado", "proposta_id": pid, "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as exc:  # noqa: BLE001 - only the UNIQUE (proposta_id) race is a no-op; anything else raises
            if not is_unique_violation(exc):
                raise
            logger.info("fluxo %s: mensagem roteiro_gerado já existia (corrida)", pid)

    # ── 5-7 together (both directions once the roteiro and the headline exist) ──────────────────────

    async def concluir(self, proposta: dict[str, Any], roteiro: dict[str, Any]) -> None:
        post_id = await run_in_threadpool(self.passo_card, proposta, roteiro)
        if post_id is None:
            return
        await self.passo_finalizador(proposta)
        await run_in_threadpool(self.passo_mensagem, proposta)

    # ── step 4 (roteiro-first): the headline job ─────────────────────────────────────────────────────

    async def passo_headline(self, proposta: dict[str, Any]) -> None:
        if self.jobs is None:
            raise RuntimeError("fluxo: sem fila de jobs para a headline")
        pid = str(proposta["id"])
        tentativas = await run_in_threadpool(self.eventos, pid, "headline_gerando")
        nova = proposta.get("fluxo_etapa") == "falhou"
        n = len(tentativas) if nova else max(len(tentativas) - 1, 0)
        chave = chave_headline(pid, n)
        await self.jobs.enqueue(
            type=JOB_HEADLINE, payload={"proposta_id": pid, "org_id": self.org_id}, dedupe_key=chave, max_retries=2,
        )
        await run_in_threadpool(self.registrar, pid, "headline_gerando", codigo=chave)


class FluxoContinuacao(SagaFluxo):
    """``FluxoService.continuacao``: ``await continuacao(proposta)`` after the pre-flight passed."""

    def __init__(self, db: Any, org_id: str, user_id: str, *, jobs: Optional[JobRepository], roteiros: RoteiroFactory) -> None:
        super().__init__(db, org_id, user_id, jobs=jobs)
        self.roteiros = roteiros

    async def __call__(self, proposta: dict[str, Any]) -> None:
        pid = str(proposta["id"])
        atual = await run_in_threadpool(self.proposta, pid)
        if atual is None:  # claimed a moment ago: its absence is a bug, never a 404
            raise RuntimeError(f"fluxo {pid}: proposta desapareceu depois do claim")
        if atual.get("fluxo_etapa") == "concluido":
            return
        if _tipo(atual) == "roteiro":
            if not atual.get("headline_id"):
                await self.passo_headline(atual)
                return
            roteiro = await run_in_threadpool(self.roteiro_do_fluxo, atual)
            if roteiro is None:
                raise RuntimeError(f"fluxo {pid}: roteiro salvo não encontrado")
        else:
            if not atual.get("headline_id"):  # step 2 saved it a moment ago: its absence is a bug, never an orphan roteiro
                raise RuntimeError(f"fluxo {pid}: headline salva não encontrada")
            roteiro = await self.passo_roteiro(atual, self.roteiros)
            if roteiro is None:
                return
        await self.concluir(atual, roteiro)


__all__ = [
    "FluxoContinuacao", "JOB_FINALIZAR", "JOB_HEADLINE", "MSG_HEADLINE_PRIMEIRO", "MSG_ROTEIRO_PRIMEIRO", "RoteiroFactory",
    "SagaFluxo", "chave_headline",
]
