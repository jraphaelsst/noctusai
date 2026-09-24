"""`empresas` — the row itself, its group-level D1 write policy, and the
manual/card-hub link (P0c contract §A.1/§C6/§D1-D2).

GROUP-LEVEL PROVENANCE, NOT PER-FIELD (contract §H12, accepted)
------------------------------------------------------------------
Unlike `clientes`/`imovel_dados`, every machine-read `empresas` column
(`razao_social`, `nome_fantasia`, `natureza_juridica`, `data_abertura`,
`situacao_cadastral`, `data_situacao_cadastral`, `motivo_situacao`, `uf`)
shares ONE `dados_*` provenance quintet. A Cartão CNPJ reads the whole
cadastral block off a single document in a single pass — the group IS the
unit of trust here. A DISAGREEING field still opens its OWN `empresa_campo_
conflitos` row (per field, never per group) through the shared writer
(`app.services.campo_conflitos`, contract §H6).

🔴 SCOPE CUT (owner decision, 2026-09-24, twice-confirmed): the company's
registered ADDRESS — including `uf` — is deliberately NOT modeled at all:
no columns, no write path, nothing on the API response. Every state
certidão this product issues is SP regardless of the empresa's location, so
an address would be reference-only with no process it feeds; the Receita
also masks it on a BAIXADA Cartão (5/5 real samples); and Crednet's own
"Participação Societária UF" column turned out not to even BE the
empresa's registered UF (it is printed beside the participation, not the
company record), closing off the one other candidate source. The raw
Crednet value still travels — inside `cliente_documentos.extracao_crednet`
JSONB, exactly as printed — just never promoted to a semantic `empresas`
column.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import NotFoundError

from app.services import campo_conflitos, table_reads

TABLE = "empresas"

#: Cadastral fields — fill-empty / conflict-on-disagree, per the group
#: provenance rule. No `uf` / address fields — see the module docstring's
#: scope-cut note (`empresas` has neither column).
CAMPOS_CADASTRAIS: tuple[str, ...] = (
    "razao_social", "nome_fantasia", "natureza_juridica", "data_abertura",
    "situacao_cadastral", "data_situacao_cadastral", "motivo_situacao",
)

PROVENIENCIA_COLUNAS: tuple[str, ...] = (
    "dados_origem", "dados_documento_id", "dados_em",
    "dados_confirmado_por", "dados_confirmado_em",
)


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _vazio(valor: Any) -> bool:
    return valor is None or valor == ""


def _serializar(valor: Any) -> Any:
    """A `date`/`datetime` off `CartaoCnpjFields` (`data_abertura`,
    `data_situacao_cadastral`) -> its ISO string, JSON-safe for both a
    PATCH onto `empresas` and a `valor_proposto` on `empresa_campo_
    conflitos` — never a bare `date` object, which the REAL PostgREST
    client (httpx's stdlib JSON encoder) cannot serialise (the mock's own
    `MockSupabaseClient` write-shape assertion catches this too). Anything
    else (a `str`, `None`) passes through unchanged."""
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


def _mesmo_valor(atual: Any, proposto: Any) -> bool:
    if _vazio(atual) or _vazio(proposto):
        return _vazio(atual) and _vazio(proposto)
    if isinstance(atual, str) and isinstance(proposto, str):
        return atual.strip().casefold() == proposto.strip().casefold()
    return atual == proposto


def get_empresa(client: Any, org_id: UUID, empresa_id: UUID) -> Optional[dict]:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(empresa_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def ensure_empresa(client: Any, org_id: UUID, empresa_id: UUID) -> dict:
    empresa = get_empresa(client, org_id, empresa_id)
    if empresa is None:
        raise NotFoundError(TABLE, str(empresa_id))
    return empresa


def criar_ou_vincular_manual(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    cnpj: str,
    razao_social: Optional[str] = None,
    participacao_pct: Optional[float] = None,
    confirmado_por: Optional[Any] = None,
) -> dict:
    """`POST /api/clientes/{cliente_id}/empresas` (contract §D2) — a manual
    link. Upserts the empresa by `(org_id, cnpj)` (fill-empty `razao_social`
    only, never overwriting a machine-provenanced one), then upserts a
    `origem='manual'` participação for this cliente, fill-empty on `pct`.
    """
    from noctusai_lib.integrations.documents.cnpj import normalize as normalize_cnpj

    cnpj_norm = normalize_cnpj(cnpj)
    existentes = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cnpj", cnpj_norm)
        .limit(1)
        .execute()
    ).data or []
    now = _now()
    if existentes:
        empresa = existentes[0]
        if not empresa.get("razao_social") and razao_social:
            _t(client, TABLE).update({"razao_social": razao_social}).eq(
                "id", empresa["id"]
            ).execute()
            empresa = {**empresa, "razao_social": razao_social}
    else:
        empresa = {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "cnpj": cnpj_norm,
            "razao_social": razao_social,
            "dados_origem": "manual",
            "dados_documento_id": None,
            "dados_em": now,
            "dados_confirmado_por": str(confirmado_por) if confirmado_por else None,
            "dados_confirmado_em": now if confirmado_por else None,
            "created_at": now,
        }
        _t(client, TABLE).insert(empresa).execute()

    participacoes_table = "cliente_empresa_participacoes"
    existentes_part = (
        _t(client, participacoes_table)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(cliente_id))
        .eq("empresa_id", str(empresa["id"]))
        .limit(1)
        .execute()
    ).data or []
    if existentes_part:
        parte = existentes_part[0]
        if parte.get("participacao_pct") is None and participacao_pct is not None:
            _t(client, participacoes_table).update(
                {"participacao_pct": participacao_pct}
            ).eq("id", parte["id"]).execute()
    else:
        _t(client, participacoes_table).insert(
            {
                "id": str(uuid4()),
                "org_id": str(org_id),
                "cliente_id": str(cliente_id),
                "empresa_id": str(empresa["id"]),
                "participacao_pct": participacao_pct,
                "desde": None,
                "fonte_documento_id": None,
                "origem": "manual",
                "confirmado_por": str(confirmado_por) if confirmado_por else None,
                "confirmado_em": now if confirmado_por else None,
                "created_at": now,
            }
        ).execute()
    return empresa


#: `aplicar_cartao`'s outcomes.
CNPJ_DIVERGENTE = "cnpj_divergente"
APLICADO = "aplicado"
SEM_MUDANCA = "sem_mudanca"


def aplicar_cartao(
    client: Any,
    org_id: UUID,
    empresa_id: UUID,
    leitura: Any,
    *,
    documento_id: UUID,
    notify_one=None,
) -> dict:
    """The Cartão CNPJ's D1 apply, group-level (contract §C6). Never raises
    for a disagreement — that is a conflict, a normal outcome.

    `leitura` is a `CartaoCnpjFields`-shaped object (duck-typed — this
    module never imports the seed's dataclass; see `crednet_service`'s own
    note on the same pattern).

    Returns `{"status": ..., "aviso": Optional[str], "conflitos": [...]}`.
    """
    empresa = ensure_empresa(client, org_id, empresa_id)

    from noctusai_lib.integrations.documents.cnpj import normalize as normalize_cnpj

    if leitura.cnpj and normalize_cnpj(leitura.cnpj) != empresa["cnpj"]:
        return {"status": CNPJ_DIVERGENTE, "aviso": "cnpj_divergente", "conflitos": []}

    patch: dict[str, Any] = {}
    conflitos: list[dict] = []
    for campo in CAMPOS_CADASTRAIS:
        proposto = _serializar(getattr(leitura, campo, None))
        if _vazio(proposto):
            continue
        atual = empresa.get(campo)
        if _vazio(atual):
            patch[campo] = proposto
            continue
        if _mesmo_valor(atual, proposto):
            continue
        confianca = (getattr(leitura, "confiancas", None) or {}).get(campo)
        novo = campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, org_id, empresa_id, campo,
            valor_anterior=atual,
            origem_anterior=empresa.get("dados_origem"),
            valor_proposto=proposto,
            origem_proposto="cartao_cnpj",
            confianca_proposta=getattr(confianca, "value", confianca),
            fonte_tabela="empresa_documentos",
            fonte_id=documento_id,
        )
        if novo is not None:
            conflitos.append(novo)

    if patch:
        now = _now()
        patch["dados_origem"] = "cartao_cnpj"
        patch["dados_documento_id"] = str(documento_id)
        patch["dados_em"] = now
        patch["dados_confirmado_por"] = None
        patch["dados_confirmado_em"] = None
        patch["updated_at"] = now
        _t(client, TABLE).update(patch).eq("id", str(empresa_id)).execute()

    return {
        "status": APLICADO if patch else SEM_MUDANCA,
        "aviso": None,
        "conflitos": conflitos,
    }


def confirmar_dados(
    client: Any, org_id: UUID, empresa_id: UUID, *, confirmado_por: Any
) -> dict:
    """`POST /api/empresas/{id}/documentos/{doc_id}/extracao/confirmar`
    (contract §D4) — a human vouches for the currently machine-pending
    group. No-op (not re-stamped) when already confirmed or when there is
    nothing machine-sourced to confirm (`dados_origem` NULL or 'manual')."""
    empresa = ensure_empresa(client, org_id, empresa_id)
    if not empresa.get("dados_origem") or empresa.get("dados_origem") == "manual":
        return empresa
    if empresa.get("dados_confirmado_em"):
        return empresa
    now = _now()
    patch = {
        "dados_confirmado_por": str(confirmado_por) if confirmado_por else None,
        "dados_confirmado_em": now,
        "updated_at": now,
    }
    _t(client, TABLE).update(patch).eq("id", str(empresa_id)).execute()
    return {**empresa, **patch}


__all__ = [
    "APLICADO",
    "CAMPOS_CADASTRAIS",
    "CNPJ_DIVERGENTE",
    "PROVENIENCIA_COLUNAS",
    "SEM_MUDANCA",
    "TABLE",
    "aplicar_cartao",
    "confirmar_dados",
    "criar_ou_vincular_manual",
    "ensure_empresa",
    "get_empresa",
]
