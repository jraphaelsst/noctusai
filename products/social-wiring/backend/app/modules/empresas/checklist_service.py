"""One empresa's document checklist (slice D, P0c follow-on).

Same UX SHAPE as `card_hub.documento_checklist_service` — an `item_key` +
`satisfeito` row a panel renders as a checked/unchecked line — but NOT a
fork of that 1000-line engine: `documento_checklist_service.ITENS` derives
from `clientes` columns (identidade, qualificação civil, endereço, ...)
that have no `empresas` analogue, so wiring an empresa through it would mean
either widening its `_CLIENTE_COLUNAS` machinery to a second, structurally
unrelated table or hand-waving a translation layer that buys nothing this
module doesn't already give directly.

TODAY, ONE ITEM: `cartao_cnpj` — always required, satisfied by a non-
deleted `empresa_documentos` row of that `tipo_documento` existing (the
upload slot `EmpresaCartaoSlot` already renders IS this item; this endpoint
exists so the checklist reads the same "ticked/not" signal a slot alone
does not carry on its own).

🔴 SCOPE CUT (this dispatch, 2026-09-24) — the brief's PJ-vendedor-
conditional items ("Contrato social / última alteração", "Dados
cadastrais", "Sócios / representantes") are NOT built here: they trigger
"only when the vendedor IS A PJ", and no `tipo_pessoa`/`pessoa_juridica`/PJ-
vs-PF marker exists anywhere on `clientes`/`atendimento_partes` in this
product (searched: no `cnpj` column on `clientes`, no `tipo_pessoa` /
`pessoa_juridica` / `is_pj` name anywhere in `products/social-wiring/
backend`). Per the brief's own instruction ("if no such notion exists,
STOP and report instead of inventing one"), this is surfaced as unresolved
in the delivery note rather than invented here.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.empresas import dados_service
from app.services import table_reads

TABLE = "empresa_documentos"


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def listar(client: Any, org_id: UUID, empresa_id: UUID) -> dict:
    """Every checklist item for this empresa. `dados_service.ensure_empresa`
    raises `NotFoundError` for an unknown/cross-org empresa_id — same 404
    every other `/api/empresas/{id}/...` route gives."""
    dados_service.ensure_empresa(client, org_id, empresa_id)

    docs = (
        _t(client, TABLE)
        .select("id, extracao_status")
        .eq("org_id", str(org_id))
        .eq("empresa_id", str(empresa_id))
        .eq("tipo_documento", "cartao_cnpj")
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    cartao = docs[0] if docs else None

    items = [
        {
            "item_key": "cartao_cnpj",
            "titulo": "Cartão CNPJ",
            "satisfeito": cartao is not None,
            "documento_id": (cartao or {}).get("id"),
            "obrigatorio": True,
        }
    ]
    return {"items": items, "total": len(items)}


__all__ = ["listar"]
