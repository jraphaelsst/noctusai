"""Roteiro approval (CoreStudio S3): the seed ``approvals`` organ bound to ``cs_roteiros``.

Owner rules (2026-11-13): ANY org member may approve; approval is ALWAYS required. A roteiro is a subject
``("roteiro", roteiro_id)`` whose ``versao`` is the roteiro's own ``versao`` column, so editing after approval
(``salvar`` bumps ``versao`` and resubmits) invalidates the approval. Every change is an immutable event in
``apr_events`` (``submitted`` = ``roteiro_gerado`` / ``roteiro_editado``, ``approved`` = ``roteiro_aprovado``,
``rejected`` = ``roteiro_reprovado``) written atomically by the ``apr_record`` RPC -- never a status column.

Reads go straight through the org-scoped table store (so the Esteira gate needs nothing but the db client);
the atomic write is the ledger (Real = ``apr_record`` RPC, Fake = the same refusals over the table).

Seam for the chat / any caller: :func:`solicitar_aprovacao_roteiro` (put a ``completo`` roteiro's current versao up
for approval) and :func:`estado_aprovacao_roteiro` / :func:`roteiro_aprovado` (where it stands).
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.domain.approvals import ApprovalService, ApprovalState, ApprovalsConfig, build_approvals_store

SUBJECT_KIND = "roteiro"
CFG = ApprovalsConfig(schema="social_wiring")
ROTEIROS = "cs_roteiros"

#: pt-BR labels of the events as the roteiro lifecycle names them (CORESTUDIO-STRUCTURE.md 2.3).
EVENTO_ROTEIRO = {"submitted": "roteiro_gerado", "approved": "roteiro_aprovado", "rejected": "roteiro_reprovado"}
NOTA_GERADO = "roteiro_gerado"
NOTA_EDITADO = "roteiro_editado"


class AprovacaoRoteiroError(Exception):
    """A refusal of the approval step: ``status`` + stable ``codigo`` + pt-BR ``mensagem`` (the router maps it)."""

    def __init__(self, status: int, codigo: str, mensagem: str):
        super().__init__(f"{codigo}: {mensagem}")
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem


def make_approvals(db: Any, *, store: Any = None) -> ApprovalService:
    """The approvals service over ``db`` (a service-role, schema-pinned client). ``store`` injects a Fake in tests."""
    return ApprovalService(store or build_approvals_store(CFG, supabase_client=db), CFG)


def present_estado(state: ApprovalState) -> dict[str, Any]:
    """The wire shape of where the CURRENT versao stands. ``status``: none | pending | approved | rejected."""
    return {
        "status": state.status,
        "versao": state.versao,
        "decidido_por": state.decided_by,
        "decidido_em": state.decided_at,
        "motivo": state.motivo,
    }


def _roteiro(db: Any, org_id: str, roteiro_id: str) -> dict[str, Any]:
    rows = db.table(ROTEIROS).select("id,status,versao").eq("id", str(roteiro_id)).eq("org_id", str(org_id)).execute().data
    if not rows:
        raise AprovacaoRoteiroError(404, "roteiro_nao_encontrado", "Roteiro não encontrado")
    return rows[0]


def estado_aprovacao_roteiro(db: Any, org_id: str, roteiro_id: str, *, approvals: Optional[ApprovalService] = None) -> dict[str, Any]:
    """Where the roteiro's current versao stands. A roteiro nobody submitted is ``none`` (never approved)."""
    _roteiro(db, org_id, roteiro_id)
    return present_estado((approvals or make_approvals(db)).state(str(org_id), SUBJECT_KIND, str(roteiro_id)))


def roteiro_aprovado(db: Any, org_id: str, roteiro_id: str, *, approvals: Optional[ApprovalService] = None) -> bool:
    """True only when the roteiro is ``completo`` AND its CURRENT ``versao`` is approved (the Esteira gate)."""
    rows = db.table(ROTEIROS).select("id,status,versao").eq("id", str(roteiro_id)).eq("org_id", str(org_id)).execute().data
    if not rows or rows[0].get("status") != "completo":
        return False
    return (approvals or make_approvals(db)).is_approved(str(org_id), SUBJECT_KIND, str(roteiro_id), int(rows[0].get("versao") or 1))


def solicitar_aprovacao_roteiro(
    db: Any, org_id: str, roteiro_id: str, *, actor_id: Optional[str] = None, nota: str = NOTA_GERADO,
    approvals: Optional[ApprovalService] = None,
) -> dict[str, Any]:
    """Put the roteiro's CURRENT versao up for approval (idempotent: the same versao again is a no-op).

    Only a ``completo`` roteiro can be submitted (409 ``roteiro_incompleto``). Returns :func:`present_estado`
    (``status`` ``pending`` unless already decided). This is the function the chat calls after creating a card."""
    row = _roteiro(db, org_id, roteiro_id)
    if row.get("status") != "completo":
        raise AprovacaoRoteiroError(409, "roteiro_incompleto", "O roteiro ainda não está pronto para aprovação.")
    svc = approvals or make_approvals(db)
    return present_estado(svc.submit(str(org_id), SUBJECT_KIND, str(roteiro_id), int(row.get("versao") or 1), actor_id=actor_id, note=nota))


__all__ = [
    "AprovacaoRoteiroError", "CFG", "EVENTO_ROTEIRO", "NOTA_EDITADO", "NOTA_GERADO", "SUBJECT_KIND", "estado_aprovacao_roteiro",
    "make_approvals", "present_estado", "roteiro_aprovado", "solicitar_aprovacao_roteiro",
]
