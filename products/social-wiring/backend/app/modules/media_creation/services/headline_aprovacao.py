"""Headline approval (criacao-pipeline-contract 1, owner decision 10.6): the seed ``approvals`` organ bound to ``cs_headlines``.

Sibling of :mod:`roteiro_aprovacao` and the other half of the Criação gate: no card enters Criação unless its headline
AND its roteiro are approved. A headline is a subject ``("headline", headline_id)`` at ``versao`` 1 -- a headline is
immutable once saved (a different text is a different headline row), so there is nothing to invalidate. Every change is
an immutable event in ``apr_events`` (``submitted`` / ``approved`` / ``rejected``) -- never a status column.

Seam: :func:`solicitar_aprovacao_headline` (the saga / chat calls it when it creates the card),
:func:`estado_aprovacao_headline`, :func:`headline_aprovada` (the gate), and the human decisions
:func:`aprovar_headline` / :func:`reprovar_headline` (any org member, like the roteiro).
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.domain.approvals import ApprovalError, ApprovalService

from app.modules.media_creation.services.roteiro_aprovacao import AprovacaoRoteiroError, make_approvals, present_estado

SUBJECT_KIND = "headline"
HEADLINES = "cs_headlines"
VERSAO = 1
NOTA_SOLICITADA = "headline_gerada"


class AprovacaoHeadlineError(AprovacaoRoteiroError):
    """A refusal of the headline approval step (same shape as the roteiro's: ``status`` + ``codigo`` + ``mensagem``)."""


def _existe(db: Any, org_id: str, headline_id: str) -> None:
    rows = db.table(HEADLINES).select("id").eq("id", str(headline_id)).eq("org_id", str(org_id)).execute().data
    if not rows:
        raise AprovacaoHeadlineError(404, "headline_nao_encontrada", "Headline não encontrada")


def _erro(exc: ApprovalError) -> AprovacaoHeadlineError:
    return AprovacaoHeadlineError(exc.status_code, exc.code, exc.message)


def estado_aprovacao_headline(db: Any, org_id: str, headline_id: str, *, approvals: Optional[ApprovalService] = None) -> dict[str, Any]:
    """Where the headline stands. A headline nobody submitted is ``none`` (never approved)."""
    _existe(db, org_id, headline_id)
    return present_estado((approvals or make_approvals(db)).state(str(org_id), SUBJECT_KIND, str(headline_id)))


def headline_aprovada(db: Any, org_id: str, headline_id: str, *, approvals: Optional[ApprovalService] = None) -> bool:
    """True only when the headline exists AND is approved (the Criação gate)."""
    rows = db.table(HEADLINES).select("id").eq("id", str(headline_id)).eq("org_id", str(org_id)).execute().data
    if not rows:
        return False
    return (approvals or make_approvals(db)).is_approved(str(org_id), SUBJECT_KIND, str(headline_id), VERSAO)


def solicitar_aprovacao_headline(
    db: Any, org_id: str, headline_id: str, *, actor_id: Optional[str] = None, approvals: Optional[ApprovalService] = None
) -> dict[str, Any]:
    """Put the headline up for approval (idempotent: submitting the same versao again is a no-op)."""
    _existe(db, org_id, headline_id)
    svc = approvals or make_approvals(db)
    return present_estado(svc.submit(str(org_id), SUBJECT_KIND, str(headline_id), VERSAO, actor_id=actor_id, note=NOTA_SOLICITADA))


def aprovar_headline(
    db: Any, org_id: str, headline_id: str, *, actor_id: str, approvals: Optional[ApprovalService] = None
) -> dict[str, Any]:
    _existe(db, org_id, headline_id)
    svc = approvals or make_approvals(db)
    svc.submit(str(org_id), SUBJECT_KIND, str(headline_id), VERSAO, actor_id=actor_id, note=NOTA_SOLICITADA)  # idempotent
    try:
        return present_estado(svc.approve(str(org_id), SUBJECT_KIND, str(headline_id), VERSAO, actor_id=actor_id))
    except ApprovalError as exc:
        raise _erro(exc) from exc


def reprovar_headline(
    db: Any, org_id: str, headline_id: str, *, actor_id: str, motivo: Optional[str] = None, approvals: Optional[ApprovalService] = None
) -> dict[str, Any]:
    _existe(db, org_id, headline_id)
    svc = approvals or make_approvals(db)
    svc.submit(str(org_id), SUBJECT_KIND, str(headline_id), VERSAO, actor_id=actor_id, note=NOTA_SOLICITADA)  # idempotent
    try:
        return present_estado(svc.reject(str(org_id), SUBJECT_KIND, str(headline_id), VERSAO, actor_id=actor_id, motivo=motivo))
    except ApprovalError as exc:
        raise _erro(exc) from exc


__all__ = [
    "AprovacaoHeadlineError", "SUBJECT_KIND", "aprovar_headline", "estado_aprovacao_headline", "headline_aprovada",
    "reprovar_headline", "solicitar_aprovacao_headline",
]
