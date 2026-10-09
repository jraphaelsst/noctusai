"""`org_imobiliarias` (migration 215) — the org's registry of signing companies
and the ONE rule that says which of them signs a given contract.

`resolver` is the single resolution function: the contract GET route, the
generator's loader (hence readiness, the aditivo and the proveniência) all go
through it, so the "exactly one active company => auto-select" rule is never
re-derived. Identity per company lives here; the org-wide operational fields
(`plataforma_assinatura_*`, `posse_multa_diaria`, `prazo_pendencias_padrao_dias`,
`suporte_*`) stay on `org_dados_cadastrais`.

Resolution (CONTRACT.md):
  - `atendimento_contratos.imobiliaria_id` set  -> that row, even if soft-deleted,
    origem "selecionada";
  - else exactly ONE active company in the org  -> that row, origem "unica"
    (read-time, never persisted);
  - else                                         -> (None, None).
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.services import table_reads

TABLE = "org_imobiliarias"

ORIGEM_SELECIONADA = "selecionada"
ORIGEM_UNICA = "unica"

#: Identity columns a caller may set (org_id / audit columns come from the token).
CAMPOS: tuple[str, ...] = (
    "razao_social",
    "nome_fantasia",
    "cnpj",
    "creci_pj",
    "creci_pj_regiao",
    "responsavel_nome",
    "responsavel_creci",
    "responsavel_creci_regiao",
    "telefone",
    "email",
    "endereco_cep",
    "endereco_logradouro",
    "endereco_numero",
    "endereco_complemento",
    "endereco_bairro",
    "endereco_cidade",
    "endereco_uf",
)

#: The fields the contract REQUIRES (same list `derivacao._imobiliaria` gates).
CAMPOS_OBRIGATORIOS: tuple[str, ...] = (
    "razao_social",
    "cnpj",
    "responsavel_nome",
    "responsavel_creci",
    "endereco_cidade",
)


def faltando(row: dict) -> list[str]:
    """Derived, never stored: the required fields that are empty."""
    return [c for c in CAMPOS_OBRIGATORIOS if not (row.get(c) or "").strip()]


def imobiliaria_out(row: dict) -> dict:
    saida = {"id": row.get("id")}
    saida.update({campo: row.get(campo) for campo in CAMPOS})
    saida["faltando"] = faltando(row)
    saida["created_at"] = row.get("created_at")
    saida["updated_at"] = row.get("updated_at")
    return saida


def listar_ativas(client: Any, org_id: UUID) -> list[dict]:
    """Every active (not soft-deleted) company, oldest first, paged."""
    rows = table_reads.paged_rows(
        client, TABLE, org_id, refine=lambda q: q.is_("excluida_em", "null")
    )
    return sorted(rows, key=lambda r: r.get("created_at") or "")


def obter(client: Any, org_id: UUID, imobiliaria_id: Any) -> Optional[dict]:
    """A company of THIS org by id, soft-deleted ones included; None if it
    does not exist or belongs to another org."""
    rows = (
        table_reads.table(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(imobiliaria_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def resolver(
    client: Any, org_id: UUID, imobiliaria_id: Any
) -> tuple[Optional[dict], Optional[str]]:
    """THE resolution rule. `imobiliaria_id` is the contract's stored choice."""
    if imobiliaria_id:
        escolhida = obter(client, org_id, imobiliaria_id)
        if escolhida is not None:
            return escolhida, ORIGEM_SELECIONADA
    # No stored choice (the FK guarantees a stored one resolves; a row outside
    # this org is treated as unchosen rather than leaking another tenant's).
    ativas = (
        table_reads.table(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .is_("excluida_em", "null")
        .limit(2)
        .execute()
    ).data or []
    if len(ativas) == 1:
        return ativas[0], ORIGEM_UNICA
    return None, None


def contrato_imobiliaria_out(row: Optional[dict], origem: Optional[str]) -> dict:
    """The `ContratoImobiliaria` payload."""
    if row is None:
        return {"imobiliaria": None, "origem": None}
    return {
        "imobiliaria": {
            "id": row.get("id"),
            "razao_social": row.get("razao_social"),
            "nome_fantasia": row.get("nome_fantasia"),
            "cnpj": row.get("cnpj"),
            "excluida": bool(row.get("excluida_em")),
            "faltando": faltando(row),
        },
        "origem": origem,
    }
