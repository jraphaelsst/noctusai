"""Negociação estruturada — the deal terms a contract instrument needs
(migration 108): structured parcelas, favorecidos, intermediários, and the
org's standing testemunhas.

WHAT THIS ADDS ON TOP OF `negociacao_service.py`
--------------------------------------------------
`negociacao_service` owns `atendimento_negociacao` — the one-row-per-deal
commercial terms (valor, comissão, split) plus its free-text
`formas_pagamento`/`parcelas` columns. This module owns the STRUCTURED
successors of those free-text columns: a real installment schedule, who each
payment is owed to, and who else brokered the deal. `org_testemunhas` (the
one org-scoped registry here) is handled in `settings_router.py`, mirroring
`org_dados_cadastrais`/`agentes_financeiros` (100) — a settings-page form, not
a card_hub write.

🔴 `saldo_nao_alocado` AND `completude` NEVER BLOCK A SAVE
-------------------------------------------------------------
Every write here accepts a partial state — a parcela with no `vencimento`, a
schedule that does not yet cover `valor_negociado`. `saldo_nao_alocado`
(valor_negociado − Σ parcelas) and `completude` (what a contract still
lacks) are REPORTED, never enforced: terms are drafted over several
sittings, same posture `negociacao_service`'s own docstring states for its
row and `org_dados_cadastrais`'s migration-100 comment states for its form.

Auth is not re-tested here — `test_auth_boundary.py` (existing) and
`test_auth_boundary_negociacao_estruturada.py` (new, this migration's routes)
enumerate every mounted card_hub route and assert a strict 401 on each.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.domain.real_estate import dividir_em_parcelas_iguais
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub import negociacao_service
from app.modules.card_hub import services as svc
from app.services import table_reads

TABLE_PARCELAS = "atendimento_negociacao_parcelas"
TABLE_FAVORECIDOS = "atendimento_favorecidos"
TABLE_INTERMEDIARIOS = "atendimento_intermediarios"

TIPOS_PARCELA: tuple[str, ...] = (
    "sinal", "intermediaria", "financiamento", "fgts", "saldo", "direta",
)
TIPOS_INTERMEDIARIO: tuple[str, ...] = ("percentual", "valor_fixo")

#: The erp-imobiliario vocabulary, verbatim
#: (`erp-imobiliario/frontend/src/pages/Financeiro.tsx::FORMAS_PAGAMENTO`).
#: A SUGGESTED list for the dropdown, not a CHECK — erp itself does not
#: constrain the column either. See migration 108's header.
FORMAS_PAGAMENTO_SUGERIDAS: tuple[str, ...] = (
    "Dinheiro",
    "PIX",
    "Cartão de Crédito",
    "Cartão de Débito",
    "Transferência",
    "Boleto",
    "Cheque",
)

_PARCELA_CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "tipo", "valor", "vencimento", "evento", "forma_pagamento",
    "favorecido_id", "confissao_divida", "ordem",
)
_FAVORECIDO_CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "nome", "cpf_cnpj", "banco", "agencia", "conta", "pix",
)
_INTERMEDIARIO_CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "corretor_id", "nome", "creci", "tipo", "valor",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _dec(value: Any) -> Optional[Decimal]:
    """Coerce to `Decimal` via `str`, never via `float` — same rationale as
    `negociacao_service._dec`: PostgREST hands numerics back as strings or
    floats depending on the driver, and `Decimal(0.07)` is not `0.07`."""
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _somar_meses(d: date, meses: int) -> date:
    """`d` plus `meses` calendar months, clamping the day to the target
    month's length (31 Jan + 1 mês -> 28/29 Fev, never a `ValueError`).

    Stdlib-only (`calendar.monthrange`) — this module intentionally does not
    add `python-dateutil` as a dependency for one date computation; it is not
    currently installed for this product (unlike `erp-imobiliario`, whose
    `contratos_service.gerar_parcelas` uses `dateutil.relativedelta` for the
    identical shape).
    """
    mes_total = d.month - 1 + meses
    ano = d.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(d.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


# ─── favorecidos ──────────────────────────────────────────────────────────


def _favorecido_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "nome": row["nome"],
        "cpf_cnpj": row.get("cpf_cnpj"),
        "banco": row.get("banco"),
        "agencia": row.get("agencia"),
        "conta": row.get("conta"),
        "pix": row.get("pix"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _listar_favorecidos_rows(client: Any, org_id: UUID, atendimento_id: UUID) -> list[dict]:
    rows = table_reads.paged_rows(
        client, TABLE_FAVORECIDOS, org_id,
        eq_filters={"atendimento_id": str(atendimento_id)},
    )
    rows.sort(key=lambda r: r["created_at"])
    return rows


def _exigir_favorecido(
    client: Any, org_id: UUID, atendimento_id: UUID, favorecido_id: UUID
) -> dict:
    """404 for a wrong org, a wrong atendimento, or an unknown id — same
    non-distinguishing shape `contratos_service._exigir_contrato` uses."""
    rows = (
        _t(client, TABLE_FAVORECIDOS)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("id", str(favorecido_id))
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(TABLE_FAVORECIDOS, str(favorecido_id))
    return rows[0]


def criar_favorecido(
    client: Any, org_id: UUID, cliente_id: UUID, *, valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "atendimento_id": str(atendimento_id),
        **{k: valores.get(k) for k in _FAVORECIDO_CAMPOS_EDITAVEIS if k in valores},
        "created_at": _now(),
        "created_por": str(usuario_id) if usuario_id else None,
    }
    _t(client, TABLE_FAVORECIDOS).insert(row).execute()
    return obter_estruturada(client, org_id, cliente_id)


def atualizar_favorecido(
    client: Any, org_id: UUID, cliente_id: UUID, favorecido_id: UUID, *,
    valores: dict, usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    _exigir_favorecido(client, org_id, atendimento_id, favorecido_id)
    patch = {k: v for k, v in valores.items() if k in _FAVORECIDO_CAMPOS_EDITAVEIS}
    patch["updated_at"] = _now()
    patch["updated_por"] = str(usuario_id) if usuario_id else None
    _t(client, TABLE_FAVORECIDOS).update(patch).eq("org_id", str(org_id)).eq(
        "id", str(favorecido_id)
    ).execute()
    return obter_estruturada(client, org_id, cliente_id)


def remover_favorecido(
    client: Any, org_id: UUID, cliente_id: UUID, favorecido_id: UUID,
) -> None:
    """204, no body — same convention `contratos_service.remover_contrato`
    uses for a delete on this module."""
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    _exigir_favorecido(client, org_id, atendimento_id, favorecido_id)
    # Hard delete — no soft-delete column on this table (unlike the LGPD
    # document tables): a favorecido is a term of the deal, not a file with
    # an access log to preserve. Any parcela pointing at it goes NULL via the
    # migration's `ON DELETE SET NULL`, never orphaned or blocked.
    _t(client, TABLE_FAVORECIDOS).delete().eq("org_id", str(org_id)).eq(
        "id", str(favorecido_id)
    ).execute()


# ─── intermediários ───────────────────────────────────────────────────────


def _intermediario_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "corretor_id": row.get("corretor_id"),
        "nome": row["nome"],
        "creci": row.get("creci"),
        "tipo": row.get("tipo", "percentual"),
        "valor": None if row.get("valor") is None else str(_dec(row.get("valor"))),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _listar_intermediarios_rows(client: Any, org_id: UUID, atendimento_id: UUID) -> list[dict]:
    rows = table_reads.paged_rows(
        client, TABLE_INTERMEDIARIOS, org_id,
        eq_filters={"atendimento_id": str(atendimento_id)},
    )
    rows.sort(key=lambda r: r["created_at"])
    return rows


def _exigir_intermediario(
    client: Any, org_id: UUID, atendimento_id: UUID, intermediario_id: UUID
) -> dict:
    rows = (
        _t(client, TABLE_INTERMEDIARIOS)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("id", str(intermediario_id))
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(TABLE_INTERMEDIARIOS, str(intermediario_id))
    return rows[0]


def _validar_intermediario_valor(tipo: str, valor: Optional[Decimal]) -> None:
    """The DB CHECK has the same rule. This exists so the caller gets a
    named, actionable 400 instead of a driver-level 500 — same posture as
    `negociacao_service._validar_split`."""
    if valor is None:
        return
    if tipo == "percentual" and not (Decimal("0") <= valor <= Decimal("100")):
        raise ValidationError_(
            "valor percentual deve estar entre 0 e 100", field="valor"
        )
    if tipo == "valor_fixo" and valor < 0:
        raise ValidationError_("valor fixo não pode ser negativo", field="valor")


def criar_intermediario(
    client: Any, org_id: UUID, cliente_id: UUID, *, valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    tipo = valores.get("tipo", "percentual")
    _validar_intermediario_valor(tipo, _dec(valores.get("valor")))
    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "atendimento_id": str(atendimento_id),
        "corretor_id": (
            str(valores["corretor_id"]) if valores.get("corretor_id") else None
        ),
        "nome": valores["nome"],
        "creci": valores.get("creci"),
        "tipo": tipo,
        "valor": (
            str(_dec(valores["valor"])) if valores.get("valor") is not None else None
        ),
        "created_at": _now(),
        "created_por": str(usuario_id) if usuario_id else None,
    }
    _t(client, TABLE_INTERMEDIARIOS).insert(row).execute()
    return obter_estruturada(client, org_id, cliente_id)


def atualizar_intermediario(
    client: Any, org_id: UUID, cliente_id: UUID, intermediario_id: UUID, *,
    valores: dict, usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    atual = _exigir_intermediario(client, org_id, atendimento_id, intermediario_id)

    tipo = valores.get("tipo", atual.get("tipo", "percentual"))
    if "valor" in valores:
        _validar_intermediario_valor(tipo, _dec(valores.get("valor")))

    patch: dict = {}
    for campo in _INTERMEDIARIO_CAMPOS_EDITAVEIS:
        if campo not in valores:
            continue
        if campo == "corretor_id":
            patch[campo] = str(valores[campo]) if valores[campo] else None
        elif campo == "valor":
            patch[campo] = (
                str(_dec(valores[campo])) if valores[campo] is not None else None
            )
        else:
            patch[campo] = valores[campo]
    patch["updated_at"] = _now()
    patch["updated_por"] = str(usuario_id) if usuario_id else None
    _t(client, TABLE_INTERMEDIARIOS).update(patch).eq("org_id", str(org_id)).eq(
        "id", str(intermediario_id)
    ).execute()
    return obter_estruturada(client, org_id, cliente_id)


def remover_intermediario(
    client: Any, org_id: UUID, cliente_id: UUID, intermediario_id: UUID,
) -> None:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    _exigir_intermediario(client, org_id, atendimento_id, intermediario_id)
    _t(client, TABLE_INTERMEDIARIOS).delete().eq("org_id", str(org_id)).eq(
        "id", str(intermediario_id)
    ).execute()


# ─── parcelas ─────────────────────────────────────────────────────────────


def _parcela_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "tipo": row["tipo"],
        "valor": str(_dec(row.get("valor")) or Decimal("0")),
        "vencimento": row.get("vencimento"),
        "evento": row.get("evento"),
        "forma_pagamento": row.get("forma_pagamento"),
        "favorecido_id": row.get("favorecido_id"),
        "confissao_divida": bool(row.get("confissao_divida", False)),
        "ordem": row.get("ordem", 0),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _listar_parcelas_rows(client: Any, org_id: UUID, atendimento_id: UUID) -> list[dict]:
    rows = table_reads.paged_rows(
        client, TABLE_PARCELAS, org_id,
        eq_filters={"atendimento_id": str(atendimento_id)},
    )
    rows.sort(key=lambda r: (r.get("ordem", 0), r["created_at"]))
    return rows


def _exigir_parcela(
    client: Any, org_id: UUID, atendimento_id: UUID, parcela_id: UUID
) -> dict:
    rows = (
        _t(client, TABLE_PARCELAS)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .eq("id", str(parcela_id))
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError(TABLE_PARCELAS, str(parcela_id))
    return rows[0]


def criar_parcela(
    client: Any, org_id: UUID, cliente_id: UUID, *, valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    if valores.get("favorecido_id"):
        _exigir_favorecido(client, org_id, atendimento_id, UUID(str(valores["favorecido_id"])))

    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "atendimento_id": str(atendimento_id),
        "tipo": valores["tipo"],
        "valor": str(_dec(valores["valor"])),
        "vencimento": valores.get("vencimento"),
        "evento": valores.get("evento"),
        "forma_pagamento": valores.get("forma_pagamento"),
        "favorecido_id": (
            str(valores["favorecido_id"]) if valores.get("favorecido_id") else None
        ),
        "confissao_divida": bool(valores.get("confissao_divida", False)),
        "ordem": valores.get("ordem", 0),
        "created_at": _now(),
        "created_por": str(usuario_id) if usuario_id else None,
    }
    _t(client, TABLE_PARCELAS).insert(row).execute()
    return obter_estruturada(client, org_id, cliente_id)


def atualizar_parcela(
    client: Any, org_id: UUID, cliente_id: UUID, parcela_id: UUID, *,
    valores: dict, usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    _exigir_parcela(client, org_id, atendimento_id, parcela_id)

    patch: dict = {}
    for campo in _PARCELA_CAMPOS_EDITAVEIS:
        if campo not in valores:
            continue
        if campo == "valor":
            patch[campo] = str(_dec(valores[campo]))
        elif campo == "favorecido_id":
            if valores[campo]:
                _exigir_favorecido(client, org_id, atendimento_id, UUID(str(valores[campo])))
                patch[campo] = str(valores[campo])
            else:
                patch[campo] = None
        else:
            patch[campo] = valores[campo]

    patch["updated_at"] = _now()
    patch["updated_por"] = str(usuario_id) if usuario_id else None
    _t(client, TABLE_PARCELAS).update(patch).eq("org_id", str(org_id)).eq(
        "id", str(parcela_id)
    ).execute()
    return obter_estruturada(client, org_id, cliente_id)


def remover_parcela(
    client: Any, org_id: UUID, cliente_id: UUID, parcela_id: UUID,
) -> None:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    _exigir_parcela(client, org_id, atendimento_id, parcela_id)
    _t(client, TABLE_PARCELAS).delete().eq("org_id", str(org_id)).eq(
        "id", str(parcela_id)
    ).execute()


def dividir_saldo_em_parcelas(
    client: Any, org_id: UUID, cliente_id: UUID, *, num_parcelas: int,
    tipo: str, forma_pagamento: Optional[str], favorecido_id: Optional[UUID],
    vencimento_inicial: Optional[str], usuario_id: Optional[UUID],
) -> dict:
    """Auto-suggest an even split of the CURRENT `saldo_nao_alocado` — a
    starting point, never a completeness gate. See this module's header and
    `noctusai_lib.domain.real_estate.parcelamento`."""
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))

    negociacao = negociacao_service.obter(client, org_id, cliente_id)
    valor_negociado = _dec(negociacao.get("valor_negociado"))
    if valor_negociado is None:
        raise ValidationError_(
            "informe o valor negociado antes de dividir o saldo em parcelas",
            field="valor_negociado",
        )
    parcelas_atuais = _listar_parcelas_rows(client, org_id, atendimento_id)
    ja_alocado = sum((_dec(p.get("valor")) or Decimal("0")) for p in parcelas_atuais)
    saldo = valor_negociado - ja_alocado
    if saldo <= 0:
        raise ValidationError_(
            "não há saldo não alocado para dividir", field="num_parcelas"
        )

    if favorecido_id:
        _exigir_favorecido(client, org_id, atendimento_id, favorecido_id)

    valores = dividir_em_parcelas_iguais(saldo, num_parcelas)
    inicio = date.fromisoformat(vencimento_inicial) if vencimento_inicial else None
    ordem_base = max((p.get("ordem", 0) for p in parcelas_atuais), default=-1) + 1

    rows = []
    for i, valor in enumerate(valores):
        vencimento = _somar_meses(inicio, i).isoformat() if inicio else None
        rows.append({
            "id": str(uuid4()),
            "org_id": str(org_id),
            "atendimento_id": str(atendimento_id),
            "tipo": tipo,
            "valor": str(valor),
            "vencimento": vencimento,
            "evento": None,
            "forma_pagamento": forma_pagamento,
            "favorecido_id": str(favorecido_id) if favorecido_id else None,
            "confissao_divida": False,
            "ordem": ordem_base + i,
            "created_at": _now(),
            "created_por": str(usuario_id) if usuario_id else None,
        })
    _t(client, TABLE_PARCELAS).insert(rows).execute()
    return obter_estruturada(client, org_id, cliente_id)


# ─── the aggregate view ───────────────────────────────────────────────────


def _completude(negociacao: dict, parcelas: list[dict]) -> dict:
    """What this contract's terms still lack. NEVER used to refuse a save —
    see this module's header. An interpretation call: scoped to the fields
    THIS migration manages (valor/parcelas/posse), not the full instrument.
    """
    faltando: list[str] = []
    valor_negociado = _dec(negociacao.get("valor_negociado"))
    if valor_negociado is None:
        faltando.append("valor_negociado")
    if not parcelas:
        faltando.append("parcelas")
    elif valor_negociado is not None:
        soma = sum((_dec(p.get("valor")) or Decimal("0")) for p in parcelas)
        if soma != valor_negociado:
            faltando.append("parcelas_nao_cobrem_valor_negociado")
    if not negociacao.get("posse_data"):
        faltando.append("posse_data")
    return {"completo": not faltando, "faltando": faltando}


def obter_estruturada(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Parcelas + favorecidos + intermediários + the computed saldo and
    completeness block, for one atendimento."""
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    negociacao = negociacao_service.obter(client, org_id, cliente_id)

    parcelas_rows = _listar_parcelas_rows(client, org_id, atendimento_id)
    favorecidos_rows = _listar_favorecidos_rows(client, org_id, atendimento_id)
    intermediarios_rows = _listar_intermediarios_rows(client, org_id, atendimento_id)

    valor_negociado = _dec(negociacao.get("valor_negociado"))
    saldo_nao_alocado: Optional[str] = None
    if valor_negociado is not None:
        alocado = sum((_dec(p.get("valor")) or Decimal("0")) for p in parcelas_rows)
        saldo_nao_alocado = str(valor_negociado - alocado)

    return {
        "atendimento_id": str(atendimento_id),
        "valor_negociado": negociacao.get("valor_negociado"),
        "saldo_nao_alocado": saldo_nao_alocado,
        "posse_data": negociacao.get("posse_data"),
        "posse_condicoes": negociacao.get("posse_condicoes"),
        "permuta_ativo_id": negociacao.get("permuta_ativo_id"),
        "parcelas": [_parcela_out(r) for r in parcelas_rows],
        "favorecidos": [_favorecido_out(r) for r in favorecidos_rows],
        "intermediarios": [_intermediario_out(r) for r in intermediarios_rows],
        "completude": _completude(negociacao, parcelas_rows),
    }


__all__ = [
    "FORMAS_PAGAMENTO_SUGERIDAS",
    "TABLE_FAVORECIDOS",
    "TABLE_INTERMEDIARIOS",
    "TABLE_PARCELAS",
    "TIPOS_INTERMEDIARIO",
    "TIPOS_PARCELA",
    "atualizar_favorecido",
    "atualizar_intermediario",
    "atualizar_parcela",
    "criar_favorecido",
    "criar_intermediario",
    "criar_parcela",
    "dividir_saldo_em_parcelas",
    "obter_estruturada",
    "remover_favorecido",
    "remover_intermediario",
    "remover_parcela",
]
