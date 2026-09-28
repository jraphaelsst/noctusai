"""Member portal — contract §Member portal, slice BE-A
(`GET /api/portal/minha-conta` only; `POST /api/portal/assinatura/
cancelar` is slice BE-B's).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.services.acesso_service import nivel_grupoterapia

_PLANOS_TABLE = "planos"
_ASSINATURAS_TABLE = "assinaturas"
_PAGAMENTOS_TABLE = "pagamentos"

_MEMBRO_FIELDS = ("id", "nome", "email", "telefone", "status", "entrou_em")
_ASSINATURA_FIELDS = (
    "id", "estado", "metodo", "proxima_cobranca", "pago_ate", "carencia_ate",
    "cancelada_em", "gateway",
)
_PAGAMENTO_FIELDS = ("id", "valor_centavos", "estado", "metodo", "vencimento", "pago_em", "url_fatura")

_PAGAMENTOS_LIMITE = 12


async def minha_conta(client: Any, *, org_id: UUID, membro: dict) -> dict:
    """Assemble `GET /api/portal/minha-conta`.

    `client` is the ADMIN (service-role) client — `membro` already comes
    from `get_membro_context`'s own RLS-checked read (the caller genuinely
    owns this row), and a member's assigned plan may not satisfy
    `planos_select_ativos_membro`'s `ativo` predicate if it was later
    deactivated. Every read below is explicitly scoped to THIS org and
    THIS membro's id, never a bare unscoped select.
    """
    org = str(org_id)
    membro_id = str(membro["id"])
    membro_out = {k: membro.get(k) for k in _MEMBRO_FIELDS}

    plano_out = None
    if membro.get("plano_id"):
        plano = (
            client.table(_PLANOS_TABLE)
            .select("*")
            .eq("org_id", org)
            .eq("id", str(membro["plano_id"]))
            .maybe_single()
            .execute()
        ).data
        if plano:
            plano_out = {
                "id": plano["id"], "nome": plano["nome"],
                "preco_centavos": plano["preco_centavos"], "ciclo": plano["ciclo"],
                "nivel_grupoterapia": nivel_grupoterapia(membro, plano),
            }

    assinaturas = (
        client.table(_ASSINATURAS_TABLE)
        .select("*")
        .eq("org_id", org)
        .eq("membro_id", membro_id)
        .neq("estado", "expirada")
        .execute()
        .data
        or []
    )
    assinaturas.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    assinatura_out = None
    if assinaturas:
        a = assinaturas[0]
        assinatura_out = {k: a.get(k) for k in _ASSINATURA_FIELDS}

    pagamentos = (
        client.table(_PAGAMENTOS_TABLE)
        .select("*")
        .eq("org_id", org)
        .eq("membro_id", membro_id)
        .execute()
        .data
        or []
    )
    pagamentos.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    pagamentos_out = [
        {k: p.get(k) for k in _PAGAMENTO_FIELDS} for p in pagamentos[:_PAGAMENTOS_LIMITE]
    ]

    planos_disponiveis = (
        client.table(_PLANOS_TABLE)
        .select("*")
        .eq("org_id", org)
        .eq("ativo", True)
        .execute()
        .data
        or []
    )
    planos_disponiveis.sort(key=lambda r: r.get("ordem") or 0)
    planos_out = [
        {
            "id": p["id"], "nome": p["nome"], "descricao": p.get("descricao"),
            "preco_centavos": p["preco_centavos"], "ciclo": p["ciclo"],
            "nivel_grupoterapia": (p.get("entitlements") or {}).get("grupoterapia", "nenhum"),
        }
        for p in planos_disponiveis
    ]

    return {
        "membro": membro_out, "plano": plano_out, "assinatura": assinatura_out,
        "pagamentos": pagamentos_out, "planos_disponiveis": planos_out,
    }
