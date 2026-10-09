"""Which of the org's registered companies (`org_imobiliarias`, migration 215)
signs THIS contract — the per-contract choice stored on
`atendimento_contratos.imobiliaria_id`.

Reads go through `imobiliarias_service.resolver` (the ONE resolution rule);
this module only adds the contract-scoped GET/PUT around it.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.card_hub import contratos_service as contratos_svc
from app.services import imobiliarias_service as imobiliarias_svc
from app.services import table_reads
from app.services.documento_store import now_iso


class ImobiliariaSelecionadaInvalida(AppException):
    def __init__(self, motivo: str) -> None:
        super().__init__(
            code="IMOBILIARIA_SELECIONADA_INVALIDA",
            message=motivo,
            status_code=400,
        )


def obter(client: Any, org_id: UUID, atendimento_id: UUID, contrato_id: UUID) -> dict:
    contrato = contratos_svc.exigir_contrato(client, org_id, atendimento_id, contrato_id)
    row, origem = imobiliarias_svc.resolver(client, org_id, contrato.get("imobiliaria_id"))
    return imobiliarias_svc.contrato_imobiliaria_out(row, origem)


def definir(
    client: Any,
    org_id: UUID,
    atendimento_id: UUID,
    contrato_id: UUID,
    *,
    imobiliaria_id: Optional[UUID],
) -> dict:
    """Store the choice (`None` clears it). A soft-deleted company cannot be
    newly chosen, but a contract that already holds it may be re-saved."""
    contrato = contratos_svc.exigir_contrato(client, org_id, atendimento_id, contrato_id)
    if imobiliaria_id is not None:
        alvo = imobiliarias_svc.obter(client, org_id, imobiliaria_id)
        if alvo is None:
            raise NotFoundError(imobiliarias_svc.TABLE, str(imobiliaria_id))
        ja_possui = str(contrato.get("imobiliaria_id") or "") == str(imobiliaria_id)
        if alvo.get("excluida_em") and not ja_possui:
            raise ImobiliariaSelecionadaInvalida(
                f"{alvo.get('razao_social') or 'Imobiliária'} foi removida do cadastro "
                "e não pode ser escolhida para um novo contrato."
            )
    (
        table_reads.table(client, contratos_svc.TABLE)
        .update(
            {
                "imobiliaria_id": str(imobiliaria_id) if imobiliaria_id else None,
                "updated_at": now_iso(),
            }
        )
        .eq("org_id", str(org_id))
        .eq("id", str(contrato_id))
        .execute()
    )
    return obter(client, org_id, atendimento_id, contrato_id)
