"""Per-deal opt-in for the OPTIONAL certidões (migration 295).

Owner decision 2026-10-21: the previous owners' certidões (last transfer
< 5 years) and the company FGTS regularity certificate are NOT required by
default — "depends on the case". A deal opts IN with two switches stored on
`atendimentos` (`exigir_certidoes_antigos`, `exigir_crf_fgts`); ON restores
the required behaviour, OFF (the default) makes them an `aviso` in readiness
and "Opcional" in the grid.

The ONE reader (`ler`) is shared by the readiness loader and the Certidões
tab so both answer the same question from the same column.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import NotFoundError

from app.services import table_reads

ATENDIMENTOS = "atendimentos"
CAMPOS = ("exigir_certidoes_antigos", "exigir_crf_fgts")


def _linha(client: Any, org_id: UUID, atendimento_id: str) -> dict:
    # Own read (not antigos_proprietarios_service's): that module imports the
    # partes service, which imports this one.
    rows = (
        table_reads.table(client, ATENDIMENTOS).select("*")
        .eq("org_id", str(org_id)).eq("id", str(atendimento_id)).limit(1).execute()
    ).data or []
    if not rows:
        raise NotFoundError(ATENDIMENTOS, str(atendimento_id))
    return rows[0]


def da_linha(row: dict) -> dict:
    """The two switches of an already-loaded `atendimentos` row. A missing
    column (pre-295 payload) reads as the new default: optional."""
    return {c: bool(row.get(c)) for c in CAMPOS}


def ler(client: Any, org_id: UUID, atendimento_id: str) -> dict:
    return da_linha(_linha(client, org_id, str(atendimento_id)))


def definir(
    client: Any,
    org_id: UUID,
    atendimento_id: str,
    *,
    exigir_certidoes_antigos: Optional[bool] = None,
    exigir_crf_fgts: Optional[bool] = None,
) -> dict:
    """`PUT …/certidoes/exigencias` — only the switches sent are written."""
    patch = {
        k: bool(v)
        for k, v in (
            ("exigir_certidoes_antigos", exigir_certidoes_antigos),
            ("exigir_crf_fgts", exigir_crf_fgts),
        )
        if v is not None
    }
    if patch:
        # 404 first for a foreign / unknown deal, same posture as dispensa.
        _linha(client, org_id, str(atendimento_id))
        table_reads.table(client, ATENDIMENTOS).update(patch).eq("org_id", str(org_id)).eq(
            "id", str(atendimento_id)
        ).execute()
    return ler(client, org_id, atendimento_id)
