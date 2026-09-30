"""One final legal review per generated contract version (owner decision
2026-09-30, migration 177).

The owner, verbatim: asked "replace the per-field confirmations with one final
review of the finished contract by the legal team?" → "yes". With
`Politica.revisao_final_unica` (the default), `service.gerar` no longer waits
for a per-field accept/reject of every machine-extracted value: it renders,
and the version records which values were machine-derived and not yet
validated (`atendimento_contrato_versoes.revisao_juridica_campos`). This
module is the ONE human act that follows:

`aprovar` — "Aprovar revisão jurídica":
  1. refuses unless the version is awaiting the review (409 `..._JA_APROVADA`
     / `..._NAO_EXIGIDA`);
  2. `validacao_extracao.confirmar_por_revisao` confirms each recorded value
     on its own row (the same write a per-field accept makes) and logs one
     `extracao_validacoes` row per value tagged with this version — after
     refusing, with NOTHING written, if any value changed since the rendering
     (409 `REVISAO_JURIDICA_VERSAO_DESATUALIZADA`: the reviewer read a PDF
     that no longer matches the data, so a new version is due);
  3. stamps `revisado_por/_em` on the version — LAST.

🔴 NOT ONE DATABASE TRANSACTION, AND ORDERED FOR THAT. PostgREST has no
multi-statement transaction, and the confirmations span up to ten
provenance tables (`validacao_extracao.TABELAS`) — the same sequential
writes the per-field `decidir` makes. The order makes a partial run safe
and truthful: a value is confirmed BEFORE the version claims to be reviewed,
so an interrupted approval leaves the version still "aguardando" (the gates
keep holding) with some values honestly confirmed by the reviewer; a retry
skips those (no longer pending, unchanged) and finishes the rest. The
opposite order could leave a "reviewed" version over unconfirmed values.

Authorization lives in the router (admin/owner, trusted DB row).
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException

from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub.contrato_gerador import validacao_extracao
from app.modules.card_hub.contrato_gerador.carregador import carregar
from app.services import table_reads
from app.services.documento_store import now_iso


class RevisaoJuridicaJaAprovada(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="REVISAO_JURIDICA_JA_APROVADA",
            message="A revisão jurídica desta versão já foi aprovada.",
            status_code=409,
        )


class RevisaoJuridicaNaoExigida(AppException):
    """Nothing machine-derived was left unvalidated when this version was
    rendered (an upload, a signed copy, a per-field-mode or pre-177
    rendering) — there is nothing for the review to vouch for, and stamping
    it would claim a review that covered nothing."""

    def __init__(self) -> None:
        super().__init__(
            code="REVISAO_JURIDICA_NAO_EXIGIDA",
            message="Esta versão não tem dados extraídos automaticamente a revisar.",
            status_code=409,
        )


def aprovar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    versao_id: UUID,
    *,
    usuario_id: Optional[Any],
) -> dict:
    # 404 for a foreign/deleted contract (carregar → exigir_contrato), then
    # for a version that is not this contract's.
    dados, atendimento_id = carregar(client, org_id, cliente_id, contrato_id, usuario_id=usuario_id)
    versao = contratos_svc.VERSOES_STORE.exigir(client, org_id, UUID(str(contrato_id)), versao_id)

    estado = contratos_svc.revisao_juridica_status(versao)
    if estado == contratos_svc.REVISAO_APROVADA:
        raise RevisaoJuridicaJaAprovada()
    if estado == contratos_svc.REVISAO_NAO_EXIGIDA:
        raise RevisaoJuridicaNaoExigida()

    confirmados = validacao_extracao.confirmar_por_revisao(
        client,
        org_id,
        dados,
        contrato_id,
        str(versao_id),
        contratos_svc.revisao_juridica_campos(versao),
        usuario_id=usuario_id,
    )

    (
        table_reads.table(client, contratos_svc.VERSOES_STORE.table)
        .update({"revisado_por": str(usuario_id) if usuario_id else None, "revisado_em": now_iso()})
        .eq("org_id", str(org_id))
        .eq("id", str(versao_id))
        .execute()
    )

    contrato = contratos_svc.exigir_contrato(client, org_id, atendimento_id, contrato_id)
    return {"contrato": contratos_svc.saida(client, org_id, contrato), "confirmados": confirmados}


__all__ = ["RevisaoJuridicaJaAprovada", "RevisaoJuridicaNaoExigida", "aprovar"]
