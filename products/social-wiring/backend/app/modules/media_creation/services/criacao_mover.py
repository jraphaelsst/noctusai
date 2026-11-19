"""The system mover of the criação pipeline (criacao-pipeline-contract 1 "Movers", 3 "Live streaming").

The actor ``system`` moves cards as the worker progresses: every move goes through the SAME service as a human's
(:class:`EsteiraService.mover`, so the Criação gate, the history row and the ``pipeline.card_moved`` publish are the
seed ``move_card``'s -- never re-implemented) with ``user_id=SISTEMA_ATOR_ID`` and ``motivo='auto:<evento>'``. A stage the
route skips is TRAVERSED (``motivo='rota:pulado'``), so the history shows the card passed there.

Writes, per transition: the card move (``pipeline_movimentos``, by ``move_card``), the sub-state + its intent-named event
(``cs_post_criacao_transicionar``, migration 369: one transaction), and -- for a move -- a ``card_movido_automaticamente``
event. Live: ``pipeline.card_moved`` (by ``move_card``) and ``pipeline.card_state`` (the progress bar) on the pipeline scope.

Every refusal is a coded :class:`CriacaoError` / the gate's coded :class:`EsteiraError` -- never exception text.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.domain.pipeline import CARD_STATE_EVENT, list_stages, make_pipeline_publisher

from app.modules.media_creation import criacao_estado as est
from app.modules.media_creation.criacao_rotas import Rota, resolver_rota, rota_da_chave
from app.modules.media_creation.esteira_config import (
    PIPELINE_ESTEIRA,
    ROLE_APROVACAO_MIDIA,
    ROLE_CRIACAO,
    ROLE_EDICAO,
    ROLE_GRAVACAO,
    ROLE_PRONTO,
)
from app.modules.media_creation.schemas.esteira import MoverEtapaRequest
from app.modules.media_creation.services.esteira_service import EsteiraError, EsteiraService, coded

logger = logging.getLogger(__name__)

#: The ``system`` actor (``responsavel_id`` of the history row, ``ator_id`` of the events it writes). A fixed id with no
#: FK anywhere (history outlives people), so "who moved this card" is always answerable: a person's uuid or this one.
SISTEMA_ATOR_ID = "00000000-0000-0000-0000-00000000c0de"
MOTIVO_PULADO = "rota:pulado"
POSTS = "cs_posts"
EVENTOS = "cs_post_eventos"


class CriacaoError(EsteiraError):
    """A coded refusal of the criação mover (same ``detail`` shape as the Esteira's: ``{code, detail, ...extra}``)."""


def _recusa(status: int, code: str, message: str, **extra: Any) -> CriacaoError:
    base = coded(status, code, message, **extra)
    return CriacaoError(base.status, base.detail)


class CriacaoMover:
    def __init__(self, db: Any, org_id: str, *, bus: Any = None):
        self.db = db
        self.org_id = str(org_id)
        self.bus = bus
        self.svc = EsteiraService(db, self.org_id, SISTEMA_ATOR_ID, bus=bus)

    # ── lookups ─────────────────────────────────────────────────────────────

    def _post(self, post_id: str) -> dict:
        return self.svc._row(post_id)

    def _etapa_do_papel(self, papel: str, *, alias: Optional[str] = None) -> dict:
        stages = [s for s in list_stages(self.db, PIPELINE_ESTEIRA, org_id=self.org_id) if s.get("ativo", True)]
        for p in (papel, alias):
            achada = next((s for s in stages if p and s.get("papel") == p), None)
            if achada:
                return achada
        raise _recusa(409, "etapa_sem_papel", "O quadro não tem uma etapa com este papel.", papel=papel)

    def _rota(self, row: dict) -> Rota:
        rota = rota_da_chave(row.get("criacao_rota")) or resolver_rota(row.get("formato"))
        if rota is None:
            raise _recusa(422, "sem_rota_de_criacao", "Este formato não tem rota automática de criação.", formato=row.get("formato"))
        return rota

    # ── writers ─────────────────────────────────────────────────────────────

    def _estado(
        self, row: dict, para: str, *, tipo: Optional[str] = None, dados: Optional[dict] = None,
        falha_codigo: Optional[str] = None, ator: Optional[str] = None, rota: Optional[str] = None,
    ) -> Optional[str]:
        """Write the sub-state + its event, one transaction (migration 369). Returns the previous state."""
        de = row.get("criacao_estado")
        if not est.transicao_valida(de, para):
            raise _recusa(409, "transicao_invalida", "Esta mudança de estado da criação não é permitida.", de=de, para=para)
        try:
            tipo_evento = est.evento_da_entrada(para, tipo)
        except ValueError as exc:  # a programming error surfaced as a coded 500-class refusal, never swallowed
            raise _recusa(500, "evento_sem_tipo", str(exc), para=para) from exc
        try:
            self.db.rpc(
                "cs_post_criacao_transicionar",
                {
                    "p_org": self.org_id, "p_post": str(row["id"]), "p_de": de, "p_para": para, "p_tipo": tipo_evento,
                    "p_dados": dados or {}, "p_falha_codigo": falha_codigo, "p_ator": ator or SISTEMA_ATOR_ID, "p_rota": rota,
                },
            ).execute()
        except Exception as exc:  # noqa: BLE001 - mapped to a code; anything unmapped is re-raised
            if "estado_mudou" in str(exc):
                raise _recusa(409, "estado_mudou", "Outro processo já mudou o estado deste post; recarregue.", post_id=str(row["id"])) from exc
            raise
        row["criacao_estado"] = para
        return de

    def _mover(self, row: dict, papel: str, evento: str, *, alias: Optional[str] = None) -> dict:
        """Move the card to the stage with ``papel`` (traversing skipped stages), as ``system``."""
        rota = rota_da_chave(row.get("criacao_rota"))
        alvo = self._etapa_do_papel(papel, alias=alias)
        stages = [s for s in list_stages(self.db, PIPELINE_ESTEIRA, org_id=self.org_id) if s.get("ativo", True)]
        ordem = [s["id"] for s in stages]
        atual = row.get("etapa_id")
        if atual == alvo["id"]:
            return row
        if atual in ordem and ordem.index(atual) < ordem.index(alvo["id"]):
            # forward: every stage strictly between is traversed; it must be one the route skips
            for meio in stages[ordem.index(atual) + 1 : ordem.index(alvo["id"])]:
                if rota is None or meio.get("papel") not in rota.etapas_puladas:
                    raise _recusa(409, "percurso_invalido", "Há uma etapa no caminho que esta rota não pula.", etapa=meio.get("papel"))
                self._mover_uma(row, meio, MOTIVO_PULADO)
        self._mover_uma(row, alvo, f"auto:{evento}")
        return row

    def _mover_uma(self, row: dict, alvo: dict, motivo: str) -> None:
        de = row.get("etapa_id")
        self.svc.mover(str(row["id"]), MoverEtapaRequest(para_etapa_id=str(alvo["id"]), motivo=motivo))
        row["etapa_id"] = alvo["id"]
        try:
            self.db.table(EVENTOS).insert(
                {
                    "org_id": self.org_id, "post_id": str(row["id"]), "tipo": "card_movido_automaticamente",
                    "de": str(de) if de else None, "para": str(alvo["id"]),
                    "dados": {"motivo": motivo, "papel": alvo.get("papel")}, "ator_id": SISTEMA_ATOR_ID,
                }
            ).execute()
        except Exception:  # noqa: BLE001 - the move is already durable; the gap is logged with its context, never silent
            logger.exception("card_movido_automaticamente event not written org=%s post=%s para=%s", self.org_id, row["id"], alvo["id"])

    # ── live (card_state) ───────────────────────────────────────────────────

    def publicar_estado(self, post_id: str, estado: dict[str, Any]) -> None:
        """Push the card's live sub-state (status line + bar) -- ``pipeline.card_state``. Best-effort: the stream is a
        view of the DB, a bus failure is logged by the publisher and never fails the work."""
        if self.bus is None:
            return
        publish = make_pipeline_publisher(self.bus, self.org_id, PIPELINE_ESTEIRA.pipeline)
        publish(CARD_STATE_EVENT, {"card_id": str(post_id), "state": dict(estado)})

    def _snapshot(self, row: dict, **extra: Any) -> dict[str, Any]:
        return {"criacao_estado": row.get("criacao_estado"), "falha_codigo": row.get("falha_codigo"), **extra}

    # ── movers ──────────────────────────────────────────────────────────────

    def entrar_em_criacao(self, post_id: str) -> dict:
        """Roteiro -> Criação, once headline AND roteiro are approved (the gate refuses otherwise: coded 409
        ``pendencias`` with ``faltando`` naming ``headline_nao_aprovado`` / ``roteiro_nao_aprovado``). Queues the job."""
        row = self._post(post_id)
        rota = self._rota(row)
        self._mover(row, ROLE_CRIACAO, "criacao_enfileirada", alias=ROLE_GRAVACAO)
        if row.get("criacao_estado") in (None, est.AGUARDANDO_APROVACAO, est.REFINANDO, est.CANCELADO):
            # both approvals stand (the gate above passed): record the sub-state; the approvals' own record is apr_events
            self._estado(row, est.APROVADO, ator=SISTEMA_ATOR_ID)
        if row.get("criacao_estado") != est.NA_FILA:  # idempotent: already queued is a no-op; the matrix refuses the rest
            self._estado(row, est.NA_FILA, dados={"rota": rota.chave, "passos": list(rota.passos)}, rota=rota.chave)
        self.publicar_estado(post_id, self._snapshot(row, rota=rota.chave, progresso=0, mensagem="Na fila"))
        return row

    def iniciar_geracao(self, post_id: str) -> dict:
        row = self._post(post_id)
        self._estado(row, est.GERANDO)
        self.publicar_estado(post_id, self._snapshot(row, progresso=0, mensagem="Gerando"))
        return row

    def progresso(self, post_id: str, *, passo: str, rodada: int, progresso: float, mensagem: str, terminal: bool = False) -> None:
        """The progress bar of a running step: pure publish (the DB already holds the step in ``cs_criacao_jobs``)."""
        self.publicar_estado(
            post_id,
            {"passo": passo, "rodada": rodada, "progresso": max(0.0, min(1.0, float(progresso))), "mensagem": mensagem, "terminal": terminal},
        )

    def concluir_geracao(self, post_id: str) -> dict:
        """Every step done: -> Edição (route with a sub-step, e.g. avatar captions) else -> Aprovação final."""
        row = self._post(post_id)
        rota = self._rota(row)
        if rota.subpasso_edicao:
            self._estado(row, est.AGUARDANDO_EDICAO, dados={"subpasso": rota.subpasso_edicao})
            self._mover(row, ROLE_EDICAO, "criacao_concluida")
            msg = "Aguardando edição"
        else:
            self._estado(row, est.AGUARDANDO_APROVACAO_MIDIA)
            self._mover(row, ROLE_APROVACAO_MIDIA, "criacao_concluida")
            msg = "Aguardando aprovação final"
        self.publicar_estado(post_id, self._snapshot(row, progresso=1, mensagem=msg, terminal=True))
        return row

    def concluir_edicao(self, post_id: str) -> dict:
        row = self._post(post_id)
        self._estado(row, est.AGUARDANDO_APROVACAO_MIDIA)
        self._mover(row, ROLE_APROVACAO_MIDIA, "edicao_concluida")
        self.publicar_estado(post_id, self._snapshot(row, progresso=1, mensagem="Aguardando aprovação final", terminal=True))
        return row

    def falhar(self, post_id: str, *, codigo: str, mensagem: str) -> dict:
        """A step failed terminally: the card stays in Criação, state ``falhou`` + the machine code (visible on the card)."""
        row = self._post(post_id)
        self._estado(row, est.FALHOU, falha_codigo=codigo, dados={"mensagem": mensagem})
        self.publicar_estado(post_id, self._snapshot(row, mensagem=mensagem, terminal=True))
        return row

    def decidir_midia(self, post_id: str, *, aprovada: bool, user_id: str, motivo: Optional[str] = None) -> dict:
        """The human's final decision (the person is the event's actor; the system performs the move).

        Approved -> Pronto. Rejected -> back to Criação with the reason (required), re-queued; only the rejected step
        re-runs (S6 reads ``dados.motivo``)."""
        row = self._post(post_id)
        if aprovada:
            self._estado(row, est.MIDIA_APROVADA, ator=user_id)
            self._mover(row, ROLE_PRONTO, "midia_aprovada")
            self.publicar_estado(post_id, self._snapshot(row, mensagem="Mídia aprovada", terminal=True))
            return row
        motivo = (motivo or "").strip()
        if not motivo:
            raise _recusa(422, "motivo_obrigatorio", "Informe o motivo da reprovação.")
        self._estado(row, est.MIDIA_REPROVADA, ator=user_id, dados={"motivo": motivo})
        self._mover(row, ROLE_CRIACAO, f"midia_reprovada: {motivo}"[:200], alias=ROLE_GRAVACAO)
        self._estado(row, est.NA_FILA, dados={"motivo": motivo, "reprocessar": True})
        self.publicar_estado(post_id, self._snapshot(row, progresso=0, mensagem="Na fila (refazendo)"))
        return row


__all__ = ["CriacaoError", "CriacaoMover", "MOTIVO_PULADO", "SISTEMA_ATOR_ID"]
