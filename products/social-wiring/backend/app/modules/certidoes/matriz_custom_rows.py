"""Certidões matriz CUSTOM rows (migration 170) — the READ + FAN-OUT this
module owns so `card_hub` (the matriz's UI/CRUD owner) and `certidoes`'s own
`vincular_parte`/`vincular_cliente`/`vincular_empresa` (the FAN-OUT trigger)
share ONE implementation without either importing the other.

WHY THIS LIVES HERE, NOT IN `card_hub`
----------------------------------------
`card_hub` already depends on `certidoes` (`certidoes.service`/`registry`,
imported throughout `card_hub.empresas_service`/`certidoes_matriz_service`)
— that dependency direction is established and one-way. Owner directive
(2026-09-24, closing the row-then-link gap): "put the read somewhere both
modules can depend on without a cycle ... rather than importing card_hub
from certidoes." Since `certidao_matriz_linhas_customizadas` is just a
table in the SAME `social_wiring` schema every certidões table already
lives in, the read needs no Python import from `card_hub` at all — it
lives on the `certidoes` side of the existing one-way edge, and `card_hub`
imports FROM here (see `certidoes_matriz_service.linhas_customizadas_
ativas`, now a thin re-export of `linhas_customizadas_ativas` below).

THE CARD-RESOLUTION PROBLEM THIS MODULE SOLVES
-------------------------------------------------
A custom row is scoped by `cliente_id` = the CARD's titular
(`atendimentos.cliente_id`) — the same identifier `card_hub.certidoes_
matriz_service.montar_matriz` reads by. But `vincular_parte`/`vincular_
cliente`/`vincular_empresa` only ever hand this module an
`atendimento_parte_id`, a bare `cliente_id` (which — per `CertidoesMatriz
Section`'s own click-through design — may be the titular, a vendedor WITH
their own `atendimento_partes` row, or a vendedor's registered spouse with
NONE, migration 153), or an `empresa_id`. `resolver_card_titular_por_
cliente`/`resolver_card_titular_por_empresa` below are the REVERSE of
`card_hub.empresas_service.pessoas_do_card`'s forward "who is on this
card" walk — deliberately re-implemented in miniature here (not imported)
for the same import-direction reason. Both are BEST-EFFORT: `None` on no
match, NEVER raise — a fan-out failing to resolve a card must never break
the vincular_* write it rides along with (owner directive §6: no new
unaudited mutation; this is a side effect of an already-audited one).
"""
from __future__ import annotations

from typing import Any, Optional

from app.modules.certidoes.registry import CUSTOM_ROW_TIPO
from app.services import table_reads

LINHAS_CUSTOMIZADAS_TABLE = "certidao_matriz_linhas_customizadas"
ATENDIMENTOS_TABLE = "atendimentos"
ATENDIMENTO_PARTES_TABLE = "atendimento_partes"
CLIENTES_TABLE = "clientes"
PARTICIPACOES_TABLE = "cliente_empresa_participacoes"
RESULTADOS_TABLE = "certidao_resultados"

#: Checklist-order base for a custom row's resultado `ordem` (the EMISSION
#: checklist's own display order, unrelated to the matriz's "5.{ordem}" row
#: label) — mirrors `card_hub.certidoes_matriz_linhas_service`'s own
#: constant; the fixed catalogue tops out at 14 (`fgts_regularidade`).
_RESULTADO_ORDEM_BASE = 100


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def linhas_customizadas_ativas(client: Any, org_id: Any, card_cliente_id: Any) -> list[dict]:
    """Every ACTIVE (`excluida_em IS NULL`) custom row for `card_cliente_id`,
    oldest first — the matriz's 5.14, 5.15, ... in creation order."""
    return (
        _t(client, LINHAS_CUSTOMIZADAS_TABLE)
        .select("id, nome, ordem, created_at")
        .eq("org_id", str(org_id))
        .eq("cliente_id", str(card_cliente_id))
        .is_("excluida_em", "null")
        .order("ordem")
        .execute()
    ).data or []


def _titular_via_parte(client: Any, org_id: Any, cliente_id: str) -> Optional[str]:
    """Is `cliente_id` a party (either lado) of an OPEN atendimento? Its
    titular, if so."""
    partes = (
        _t(client, ATENDIMENTO_PARTES_TABLE)
        .select("atendimento_id")
        .eq("org_id", str(org_id))
        .eq("cliente_id", cliente_id)
        .execute()
    ).data or []
    if not partes:
        return None
    atendimento_ids = [p["atendimento_id"] for p in partes]
    atendimentos = (
        _t(client, ATENDIMENTOS_TABLE)
        .select("id, cliente_id")
        .eq("org_id", str(org_id))
        .in_("id", atendimento_ids)
        .is_("substituida_por", "null")
        .eq("arquivado", False)
        .execute()
    ).data or []
    return str(atendimentos[0]["cliente_id"]) if atendimentos else None


def _e_titular(client: Any, org_id: Any, cliente_id: str) -> bool:
    """Is `cliente_id` itself the titular of an OPEN atendimento?"""
    rows = (
        _t(client, ATENDIMENTOS_TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("cliente_id", cliente_id)
        .is_("substituida_por", "null")
        .eq("arquivado", False)
        .limit(1)
        .execute()
    ).data or []
    return bool(rows)


def resolver_card_titular_por_cliente(client: Any, org_id: Any, cliente_id: Any) -> Optional[str]:
    """Given ANY person's `cliente_id` on a card (the titular, a vendedor
    with their own `atendimento_partes` row, or a vendedor's registered
    spouse with none), the CARD's titular — or `None` (never raises). See
    the module docstring."""
    cid = str(cliente_id)
    if _e_titular(client, org_id, cid):
        return cid

    titular = _titular_via_parte(client, org_id, cid)
    if titular:
        return titular

    # A registered spouse with NO atendimento_partes row of their own
    # (migration 153's link, written symmetrically — `compradores_service.
    # _casar`) — walk to the OTHER side of the marriage and retry.
    conjuge_rows = (
        _t(client, CLIENTES_TABLE)
        .select("id, conjuge_cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", cid)
        .limit(1)
        .execute()
    ).data or []
    conjuge_id = conjuge_rows[0].get("conjuge_cliente_id") if conjuge_rows else None
    if not conjuge_id or str(conjuge_id) == cid:
        return None
    conjuge_id = str(conjuge_id)
    if _e_titular(client, org_id, conjuge_id):
        return conjuge_id
    return _titular_via_parte(client, org_id, conjuge_id)


def resolver_card_titular_por_empresa(client: Any, org_id: Any, empresa_id: Any) -> Optional[str]:
    """The card behind an `empresas` row — via any of its owners
    (`cliente_empresa_participacoes`), each resolved the same way
    `resolver_card_titular_por_cliente` resolves a person."""
    participacoes = (
        _t(client, PARTICIPACOES_TABLE)
        .select("cliente_id")
        .eq("org_id", str(org_id))
        .eq("empresa_id", str(empresa_id))
        .execute()
    ).data or []
    for participacao in participacoes:
        titular = resolver_card_titular_por_cliente(client, org_id, participacao["cliente_id"])
        if titular:
            return titular
    return None


def fan_out_linhas_customizadas(
    client: Any, org_id: Any, consulta_id: str, card_cliente_id: str,
) -> int:
    """One `pendente` placeholder resultado per ACTIVE custom row of
    `card_cliente_id` this consulta does not already carry — idempotent
    (checks existing `linha_customizada_id`s first, mirroring `routers.
    certidoes._fan_out_tipos_manuais`'s own idempotent-insert shape).
    Returns the number of placeholders written."""
    linhas = linhas_customizadas_ativas(client, org_id, card_cliente_id)
    if not linhas:
        return 0

    existentes = (
        _t(client, RESULTADOS_TABLE)
        .select("linha_customizada_id")
        .eq("consulta_id", consulta_id)
        .eq("org_id", str(org_id))
        .execute()
    ).data or []
    ja_tem = {r["linha_customizada_id"] for r in existentes if r.get("linha_customizada_id")}

    novos = [
        {
            "consulta_id": consulta_id,
            "org_id": str(org_id),
            "tipo": CUSTOM_ROW_TIPO,
            "linha_customizada_id": str(linha["id"]),
            "nome_display": f"Outras: {linha['nome']}",
            "ordem": _RESULTADO_ORDEM_BASE + linha["ordem"],
            "status": "pendente",
        }
        for linha in linhas
        if str(linha["id"]) not in ja_tem
    ]
    if novos:
        _t(client, RESULTADOS_TABLE).insert(novos).execute()
    return len(novos)


__all__ = [
    "fan_out_linhas_customizadas",
    "linhas_customizadas_ativas",
    "resolver_card_titular_por_cliente",
    "resolver_card_titular_por_empresa",
]
