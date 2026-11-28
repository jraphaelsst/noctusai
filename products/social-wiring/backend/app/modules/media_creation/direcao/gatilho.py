"""The approval -> production trigger (project ``diretor-edicao-reels``, contract section 3).

Rule: when a post's headline AND roteiro are both approved, ask for ONE production run, once, by itself. Everything here is
decision-free plumbing:

* **Event-oriented.** The request is the intent-named event ``direcao_solicitada`` (``cs_post_eventos``, migration 373), written
  by ``cs_direcao_evento`` with the idempotency key as a database fact (a partial UNIQUE index): a repeated trigger -- the double
  click, the retried request, the reconcile sweep -- writes nothing and queues nothing. A refusal is the event
  ``direcao_recusada`` with its code.
* **Idempotent by key.** ``chave = direcao:<post>:h<headline>:r<roteiro>:v<roteiro versao>``: an EDITED and re-approved roteiro is a
  new request (new versao), the same approval pair never is. A crash between the event and the enqueue is healed by the next
  trigger: the event exists but the step ledger has no graph, so the enqueue is repeated (the enqueue itself is idempotent).
* **Opt-in twice.** A route starts by itself only when its data says so (``Rota.gatilho_automatico``; only ``reel_dirigido``) AND
  the switch is on (default OFF). Nothing about ``reel_narrado``, which spends credits on a human's explicit "iniciar", changes.
* **Never fails the approval.** The approval is already durable when this runs: every outcome is a value (:class:`Resultado`),
  a coded refusal is recorded and logged, and :func:`acionar_apos_aprovacao` swallows nothing silently (it logs the exception).

Ports (all injected; tests use in-memory doubles, production wiring is :func:`construir_gatilho`): the switch, the event writer,
the enqueue, the "does a graph already exist" read, and the approvals organ.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Protocol

from noctusai_lib.domain.approvals import ApprovalService

from app.modules.media_creation import criacao_estado as est
from app.modules.media_creation.criacao_rotas import rota_da_chave
from app.modules.media_creation.direcao.passos import ROTA_DIRIGIDO
from app.modules.media_creation.services.headline_aprovacao import headline_aprovada
from app.modules.media_creation.services.roteiro_aprovacao import roteiro_aprovado

logger = logging.getLogger(__name__)

POSTS = "cs_posts"
ROTEIROS = "cs_roteiros"

# outcome enum of ONE evaluation (closed)
DISPARADO = "disparado"
JA_SOLICITADO = "ja_solicitado"
DESLIGADO = "desligado"
SEM_GATILHO_NA_ROTA = "sem_gatilho_na_rota"
APROVACOES_PENDENTES = "aprovacoes_pendentes"
RECUSADO = "recusado"
POST_NAO_ENCONTRADO = "post_nao_encontrado"
RESULTADOS = (
    DISPARADO, JA_SOLICITADO, DESLIGADO, SEM_GATILHO_NA_ROTA, APROVACOES_PENDENTES, RECUSADO, POST_NAO_ENCONTRADO,
)

#: criacao_estado values from which a post may still need its first enqueue (the reconcile sweep's candidates).
ESTADOS_SEM_FILA = (None, est.AGUARDANDO_APROVACAO, est.REFINANDO, est.APROVADO, est.CANCELADO)


@dataclass(frozen=True)
class Resultado:
    resultado: str
    post_id: str
    chave: Optional[str] = None
    codigo: Optional[str] = None  # the refusal's code (resultado == recusado)


class Solicitacoes(Protocol):
    def solicitar(self, org_id: str, post_id: str, chave: str, dados: dict[str, Any]) -> bool:
        """Record ``direcao_solicitada``; True = newly recorded, False = this chave was already requested."""

    def recusar(self, org_id: str, post_id: str, chave: str, codigo: str, dados: dict[str, Any]) -> None:
        """Record ``direcao_recusada`` with ``codigo``."""


class SupabaseSolicitacoes:
    """Real writer: migration 373's definer RPC (event + idempotency in one statement)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def _rpc(self, org_id: str, post_id: str, tipo: str, chave: str, dados: dict[str, Any]) -> bool:
        out = self._db.rpc(
            "cs_direcao_evento",
            {"p_org": str(org_id), "p_post": str(post_id), "p_tipo": tipo, "p_chave": chave, "p_dados": dados, "p_ator": None},
        ).execute()
        return bool(out.data)

    def solicitar(self, org_id: str, post_id: str, chave: str, dados: dict[str, Any]) -> bool:
        return self._rpc(org_id, post_id, "direcao_solicitada", chave, dados)

    def recusar(self, org_id: str, post_id: str, chave: str, codigo: str, dados: dict[str, Any]) -> None:
        self._rpc(org_id, post_id, "direcao_recusada", chave, {**dados, "codigo": codigo})


Enfileirador = Callable[[str, str, Optional[str]], Awaitable[dict]]  # (post_id, org_id, ator_id) -> response
GrafoExistente = Callable[[str, str], Awaitable[bool]]  # (org_id, post_id) -> a graph row already exists


def _codigo_da_excecao(exc: BaseException) -> str:
    """The stable code of a refusal (never its text): ``CriacaoError.code`` or the ``detail['code']`` of a coded refusal."""
    codigo = getattr(exc, "code", None) or getattr(exc, "codigo", None)
    if not codigo:
        detalhe = getattr(exc, "detail", None)
        if isinstance(detalhe, dict):
            codigo = detalhe.get("code")
    return str(codigo) if codigo else "erro_interno"


class GatilhoDirecao:
    def __init__(
        self, db: Any, *, habilitado: Callable[[str], bool], solicitacoes: Solicitacoes, enfileirar: Enfileirador,
        grafo_existente: GrafoExistente, approvals: Optional[ApprovalService] = None,
    ) -> None:
        self._db, self._habilitado, self._sol = db, habilitado, solicitacoes
        self._enfileirar, self._grafo, self._approvals = enfileirar, grafo_existente, approvals

    # ── reading ─────────────────────────────────────────────────────────────────────────────────────────────────────

    def _post(self, org_id: str, post_id: str) -> Optional[dict]:
        rows = (
            self._db.table(POSTS).select("id,org_id,formato,criacao_rota,criacao_estado,headline_id,roteiro_id")
            .eq("id", str(post_id)).eq("org_id", str(org_id)).execute().data
        )
        return rows[0] if rows else None

    def _versao_roteiro(self, org_id: str, roteiro_id: str) -> int:
        rows = self._db.table(ROTEIROS).select("versao").eq("id", str(roteiro_id)).eq("org_id", str(org_id)).execute().data
        return int((rows[0] if rows else {}).get("versao") or 1)

    def _aprovado(self, org_id: str, post: dict) -> bool:
        if not post.get("headline_id") or not post.get("roteiro_id"):
            return False
        return headline_aprovada(self._db, org_id, str(post["headline_id"]), approvals=self._approvals) and roteiro_aprovado(
            self._db, org_id, str(post["roteiro_id"]), approvals=self._approvals
        )

    # ── the one decision ────────────────────────────────────────────────────────────────────────────────────────────

    async def avaliar_post(self, org_id: str, post_id: str, *, ator_id: Optional[str] = None) -> Resultado:
        org_id, post_id = str(org_id), str(post_id)
        post = await asyncio.to_thread(self._post, org_id, post_id)
        if post is None:
            return Resultado(POST_NAO_ENCONTRADO, post_id)
        rota = rota_da_chave(post.get("criacao_rota"))
        if rota is None or not rota.gatilho_automatico:
            return Resultado(SEM_GATILHO_NA_ROTA, post_id)
        if not self._habilitado(org_id):
            return Resultado(DESLIGADO, post_id)
        if not await asyncio.to_thread(self._aprovado, org_id, post):
            return Resultado(APROVACOES_PENDENTES, post_id)

        versao = await asyncio.to_thread(self._versao_roteiro, org_id, str(post["roteiro_id"]))
        chave = f"direcao:{post_id}:h{post['headline_id']}:r{post['roteiro_id']}:v{versao}"
        dados = {"rota": rota.chave, "headline_id": str(post["headline_id"]), "roteiro_id": str(post["roteiro_id"]), "roteiro_versao": versao}
        novo = await asyncio.to_thread(self._sol.solicitar, org_id, post_id, chave, dados)
        if not novo and await self._grafo(org_id, post_id):
            return Resultado(JA_SOLICITADO, post_id, chave)  # requested before AND a graph exists: nothing to do
        try:
            resposta = await self._enfileirar(post_id, org_id, ator_id)
        except Exception as exc:  # noqa: BLE001 - coded + recorded + logged, never raised into the approval
            codigo = _codigo_da_excecao(exc)
            logger.warning("direcao.gatilho.recusado post=%s codigo=%s", post_id, codigo, exc_info=codigo == "erro_interno")
            await asyncio.to_thread(self._sol.recusar, org_id, post_id, chave, codigo, dados)
            return Resultado(RECUSADO, post_id, chave, codigo)
        if isinstance(resposta, dict) and resposta.get("ja_em_andamento"):
            return Resultado(JA_SOLICITADO, post_id, chave)
        return Resultado(DISPARADO, post_id, chave)

    # ── entry points by the approved subject, and the reconcile sweep ───────────────────────────────────────────────

    async def avaliar_por(self, org_id: str, coluna: str, valor: str, *, ator_id: Optional[str] = None) -> list[Resultado]:
        """Every post of the org that carries this headline / roteiro (``coluna`` = ``headline_id`` | ``roteiro_id``)."""
        assert coluna in ("headline_id", "roteiro_id")
        rows = await asyncio.to_thread(
            lambda: self._db.table(POSTS).select("id").eq(coluna, str(valor)).eq("org_id", str(org_id)).execute().data
        )
        return [await self.avaliar_post(org_id, str(r["id"]), ator_id=ator_id) for r in rows]

    async def reconciliar(self, org_id: str) -> list[Resultado]:
        """Re-evaluate the org's ``reel_dirigido`` posts that never got a queue (a missed approval path, a crash). Idempotent."""
        rows = await asyncio.to_thread(
            lambda: self._db.table(POSTS).select("id,criacao_estado").eq("org_id", str(org_id)).eq("criacao_rota", ROTA_DIRIGIDO).execute().data
        )
        return [await self.avaliar_post(org_id, str(r["id"])) for r in rows if r.get("criacao_estado") in ESTADOS_SEM_FILA]


# ── production wiring ──────────────────────────────────────────────────────────────────────────────────────────────────


def construir_gatilho(db: Any, *, approvals: Optional[ApprovalService] = None) -> GatilhoDirecao:
    """The Real wiring: the config switch, the 373 RPC, the ONE enqueue (``criacao_service.enfileirar``), the step ledger."""
    from app.config import settings
    from app.modules.media_creation.criacao_ports import SupabaseLedger

    async def enfileirar(post_id: str, org_id: str, ator_id: Optional[str]) -> dict:
        from app.modules.media_creation.services import criacao_service as cs

        return await cs.enfileirar(post_id, org_id=org_id, ator_id=ator_id, db=db)

    async def grafo_existente(org_id: str, post_id: str) -> bool:
        return bool(await SupabaseLedger(db).carregar(org_id, post_id))

    return GatilhoDirecao(
        db, habilitado=lambda _org: bool(settings.direcao_gatilho_ativo), solicitacoes=SupabaseSolicitacoes(db),
        enfileirar=enfileirar, grafo_existente=grafo_existente, approvals=approvals,
    )


async def acionar_apos_aprovacao(
    db: Any, org_id: str, *, post_id: Optional[str] = None, headline_id: Optional[str] = None,
    roteiro_id: Optional[str] = None, ator_id: Optional[str] = None, gatilho: Optional[GatilhoDirecao] = None,
    ligado: Optional[bool] = None,
) -> list[Resultado]:
    """The call the approval endpoints make AFTER a decision is durable. Never raises: a failure is logged with its traceback
    (the approval stays valid; the reconcile sweep picks the post up). ``ligado`` / ``gatilho`` are the DI seams (tests)."""
    from app.config import settings

    if not (settings.direcao_gatilho_ativo if ligado is None else ligado):
        return []  # switch off: not even a DB read on the approval path
    try:
        g = gatilho or construir_gatilho(db)
        if post_id:
            return [await g.avaliar_post(org_id, post_id, ator_id=ator_id)]
        if headline_id:
            return await g.avaliar_por(org_id, "headline_id", headline_id, ator_id=ator_id)
        if roteiro_id:
            return await g.avaliar_por(org_id, "roteiro_id", roteiro_id, ator_id=ator_id)
        return []
    except Exception:  # noqa: BLE001
        logger.exception("direcao.gatilho.falhou org=%s post=%s", org_id, post_id)
        return []


__all__ = [
    "DESLIGADO", "DISPARADO", "ESTADOS_SEM_FILA", "GatilhoDirecao", "JA_SOLICITADO", "APROVACOES_PENDENTES", "POST_NAO_ENCONTRADO",
    "RECUSADO", "RESULTADOS", "Resultado", "SEM_GATILHO_NA_ROTA", "Solicitacoes", "SupabaseSolicitacoes", "acionar_apos_aprovacao",
    "construir_gatilho",
]
