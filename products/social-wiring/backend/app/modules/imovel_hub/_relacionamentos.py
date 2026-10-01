"""Shared building blocks of the imóvel↔pessoa relationship services.

`atendimento_imoveis_service`, `interesses_service` and `proprietarios_service`
(contract `atendimento-partes-imoveis` §3-§4) all need the same three things:
the 404 for a código the registry does not know (with the contract's exact
copy), the `ImovelLinhaPessoa` row shape (§0.2), and an ISO clock. Written once
here — three copies of the message is how the three endpoints would drift apart
the first time the copy is edited.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException

from app.modules.imovel_hub import busca_service
from app.services import table_reads

REGISTRY_TABLE = busca_service.REGISTRY_TABLE


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def imovel_nao_encontrado(codigo: str) -> AppException:
    """404 `NOT_FOUND` with the contract's exact copy (§3.2 / §4.1)."""
    return AppException(
        code="NOT_FOUND",
        message=(
            f"Imóvel {codigo} não encontrado. "
            "Selecione um imóvel do catálogo ou cadastre-o."
        ),
        status_code=404,
        details={"resource": "imovel_registry", "codigo": codigo},
    )


def exigir_imovel_cadastrado(client: Any, org_id: UUID, codigo: str) -> str:
    """The canonical código, or the contract's 404.

    Checked explicitly rather than left to the FK: a foreign-key violation
    surfaces as a driver-level 500 that names a constraint, and "imóvel não
    encontrado" is a 404 the picker can act on.
    """
    canonico = busca_service.canonical(codigo or "")
    if not canonico:
        raise imovel_nao_encontrado(codigo or "")
    rows = (
        table_reads.table(client, REGISTRY_TABLE)
        .select("codigo_canonical")
        .eq("org_id", str(org_id))
        .eq("codigo_canonical", canonico)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise imovel_nao_encontrado(canonico)
    return canonico


def linha_pessoa(row: dict, imovel: Optional[dict], **extras: Any) -> dict:
    """`ImovelLinhaPessoa` (§0.2): `{id, codigo, origem, created_at,
    created_by, imovel}` + the endpoint's own extras.

    `imovel` is never null on the wire (the FK guarantees a registry row); a
    code that `enriquecer` somehow did not resolve gets the honest
    `fonte: "nenhuma"` shape rather than a null the FE would crash on.
    """
    codigo = str(row["codigo"])
    return {
        "id": str(row["id"]),
        "codigo": codigo,
        "origem": row.get("origem"),
        "created_at": row.get("created_at"),
        "created_by": str(row["created_by"]) if row.get("created_by") else None,
        **extras,
        "imovel": imovel
        or {"codigo": codigo, "registrado": False, "fonte": "nenhuma"},
    }
