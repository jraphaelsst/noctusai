"""The commercial terms of one atendimento, and who gets what (migration 077).

Valor negociado, % de comissão, parceria, formas de pagamento, parcelas,
financiamento e FGTS — plus the computed breakdown the card renders.

🔴 THE PERCENTAGES ARE COPIED AT CREATION, NEVER RE-READ
--------------------------------------------------------
`negociacao_defaults` is the org's CURRENT rule. It is read exactly once per
negociação — when the row is created — and the values are written onto the
row. Changing the org default afterwards must not rewrite what was agreed on
a past deal, and a commission split is a record of an agreement rather than a
current setting.

🔴 MONEY IS `Decimal`, AND THE PARTS ALWAYS SUM TO THE WHOLE
-------------------------------------------------------------
Floats cannot represent centavos, and three independent
`round(total * pct / 100, 2)` calls do not add back up to `total` — they are
short or over by a centavo or two, unpredictably. On a R$ 500.000 sale with a
6% commission that is small money and a large problem: the agency's ledger
and the sum of its parts disagree, and nobody can tell which is right.

So every division here goes through `_ratear`, which allocates with the
largest-remainder method: each share is floored to the centavo, and the
leftover centavos are handed out one at a time to the largest remainders. The
result is exact by construction — `sum(parts) == total`, always, and a test
pins it on a deliberately awkward number.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import ValidationError_

from app.modules.card_hub import services as svc
from app.services import table_reads

TABLE = "atendimento_negociacao"
DEFAULTS_TABLE = "negociacao_defaults"

CENTAVO = Decimal("0.01")

#: 🔴 The canonical business rule, in code — NOT a coincidence copied from
#: consumer #1 (`KB § PATTERNS/architect/seed-canonical-defaults.md`).
#:
#: An org with no `negociacao_defaults` row uses exactly this, so a brand-new
#: org works with no data step and the override table means only "we differ".
#:
#: `pct_comissao` is absent on purpose: the user specified the SPLIT (50/45/5,
#: parceria 50) and never a commission RATE. Inventing one would put a number
#: nobody chose onto every new deal.
DEFAULTS: dict[str, Decimal] = {
    "pct_parceria": Decimal("50"),
    "pct_agencia": Decimal("50"),
    "pct_agentes": Decimal("45"),
    "pct_captador": Decimal("5"),
}

#: The percentages a caller may set. `pct_comissao` is here; the derived money
#: values are not — they are computed, never stored, so they cannot drift from
#: the inputs that produced them.
CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "imovel_codigo",
    "valor_negociado",
    "pct_comissao",
    "tem_parceria",
    "pct_parceria",
    "pct_agencia",
    "pct_agentes",
    "pct_captador",
    "formas_pagamento",
    "parcelas",
    "financiamento",
    "fgts",
    "observacoes",
)

_PERCENTUAIS_INTERNOS = ("pct_agencia", "pct_agentes", "pct_captador")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _t(client: Any, name: str):
    return table_reads.table(client, name)


def _dec(value: Any) -> Optional[Decimal]:
    """Coerce to `Decimal` via `str`, never via `float`.

    `Decimal(0.07)` is 0.070000000000000006938893903907228377647697925567626953125.
    `Decimal("0.07")` is 0.07. PostgREST hands numerics back as strings or
    floats depending on the driver, so the coercion has to be explicit.
    """
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _ratear(total: Decimal, pesos: list[Decimal]) -> list[Decimal]:
    """Split `total` across `pesos` so the parts sum EXACTLY to `total`.

    Largest-remainder allocation: floor every share to the centavo, then hand
    the leftover centavos out one at a time, biggest remainder first.

    🔴 The naive alternative — rounding each share independently — is short or
    over by a few centavos depending on the numbers, so the agency's total and
    the sum of its parts disagree and neither is obviously wrong. That is the
    kind of discrepancy someone finds at payout time and cannot reconstruct.
    """
    soma_pesos = sum(pesos)
    if total <= 0 or soma_pesos <= 0:
        return [Decimal("0.00") for _ in pesos]

    exatos = [total * p / soma_pesos for p in pesos]
    pisos = [e.quantize(CENTAVO, rounding=ROUND_DOWN) for e in exatos]
    restante = int(((total - sum(pisos)) / CENTAVO).to_integral_value())

    # Biggest fractional remainder first; index breaks ties so the result is
    # deterministic rather than dependent on sort stability.
    ordem = sorted(
        range(len(pesos)),
        key=lambda i: (exatos[i] - pisos[i], -i),
        reverse=True,
    )
    for k in range(restante):
        pisos[ordem[k % len(pisos)]] += CENTAVO
    return pisos


def resolver_defaults(client: Any, org_id: UUID) -> dict[str, Decimal]:
    """The org's split rule — its override row, else the code constants."""
    rows = (
        _t(client, DEFAULTS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .limit(1)
        .execute()
    ).data or []
    resolvido = dict(DEFAULTS)
    resolvido["pct_comissao"] = None  # type: ignore[assignment]
    if rows:
        row = rows[0]
        for campo in ("pct_parceria", *_PERCENTUAIS_INTERNOS, "pct_comissao"):
            valor = _dec(row.get(campo))
            if valor is not None:
                resolvido[campo] = valor
    return resolvido


def _linha(client: Any, org_id: UUID, atendimento_id: UUID) -> Optional[dict]:
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _membros(client: Any, org_id: UUID, cliente_id: UUID) -> list[dict]:
    """The funnel card's membros — the agents the agentes slice is split among.

    Read through `card_hub.services.get_membros` rather than re-querying
    `cliente_membros` here: that function already knows the table has no `id`
    column and pages on `lead_corretor_id`, and a second copy of that would be
    a second place to get it wrong.
    """
    return svc.get_membros(client, org_id, cliente_id)["items"]


def _captador(client: Any, org_id: UUID, imovel_codigo: Optional[str]) -> Optional[str]:
    if not imovel_codigo:
        return None
    rows = (
        _t(client, "imovel_dados")
        .select("captador_user_id")
        .eq("org_id", str(org_id))
        .eq("codigo", imovel_codigo)
        .limit(1)
        .execute()
    ).data or []
    return rows[0].get("captador_user_id") if rows else None


def calcular(
    row: dict,
    *,
    membros: list[dict],
    captador: Optional[dict],
) -> dict:
    """The money breakdown. Pure — no I/O, so it is trivially testable.

    Every amount is a string, not a float: this crosses JSON, and a float
    would reintroduce exactly the representation error `Decimal` was chosen to
    avoid the moment it is parsed on the other side.
    """
    valor = _dec(row.get("valor_negociado")) or Decimal("0")
    pct_comissao = _dec(row.get("pct_comissao"))

    if pct_comissao is None or valor <= 0:
        # Not an error — terms are routinely drafted before a price is agreed.
        # Returning zeroes rather than nulls would claim a split was computed.
        return {
            "calculavel": False,
            "motivo": "informe valor negociado e % de comissão",
            "comissao_total": None,
            "parceria": None,
            "nossa_parte": None,
            "agencia": None,
            "agentes_total": None,
            "agentes": [],
            "captador_total": None,
            "captador": captador,
        }

    comissao_total = (valor * pct_comissao / 100).quantize(CENTAVO)

    tem_parceria = bool(row.get("tem_parceria"))
    pct_parceria = _dec(row.get("pct_parceria")) or Decimal("0")
    if tem_parceria:
        parceria, nossa_parte = _ratear(
            comissao_total, [pct_parceria, Decimal("100") - pct_parceria]
        )
    else:
        parceria, nossa_parte = Decimal("0.00"), comissao_total

    agencia, agentes_total, captador_total = _ratear(
        nossa_parte,
        [
            _dec(row.get("pct_agencia")) or Decimal("0"),
            _dec(row.get("pct_agentes")) or Decimal("0"),
            _dec(row.get("pct_captador")) or Decimal("0"),
        ],
    )

    # The agentes slice, split equally among the card's membros. With no
    # membros the slice is reported as UNALLOCATED rather than quietly folded
    # into the agency's share — the money is owed to somebody who has not been
    # named yet, and saying so is the difference between a gap and a silent
    # reassignment.
    if membros:
        partes = _ratear(agentes_total, [Decimal("1")] * len(membros))
        agentes = [
            {"id": m["id"], "nome": m["nome"], "valor": str(v)}
            for m, v in zip(membros, partes)
        ]
    else:
        agentes = []

    return {
        "calculavel": True,
        "motivo": None,
        "comissao_total": str(comissao_total),
        "parceria": str(parceria),
        "nossa_parte": str(nossa_parte),
        "agencia": str(agencia),
        "agentes_total": str(agentes_total),
        "agentes": agentes,
        # Null captador means the 5% is unallocated, never silently the
        # agency's — same reason migration 075 leaves `captador_user_id` null.
        "captador_total": str(captador_total),
        "captador": captador,
    }


def _saida(
    row: Optional[dict],
    atendimento_id: UUID,
    *,
    defaults: dict,
    membros: list[dict],
    captador: Optional[dict],
) -> dict:
    """An atendimento with no negociação row yet reads as the DEFAULTS, empty.

    Not a 404 and not `{}`: no terms recorded is the normal state of a new
    deal, and the percentages a user would start from are the org's rule.
    """
    if row is None:
        row = {
            "atendimento_id": str(atendimento_id),
            "imovel_codigo": None,
            "valor_negociado": None,
            "pct_comissao": (
                str(defaults["pct_comissao"])
                if defaults.get("pct_comissao") is not None
                else None
            ),
            "tem_parceria": False,
            "pct_parceria": str(defaults["pct_parceria"]),
            "pct_agencia": str(defaults["pct_agencia"]),
            "pct_agentes": str(defaults["pct_agentes"]),
            "pct_captador": str(defaults["pct_captador"]),
            "formas_pagamento": None,
            "parcelas": None,
            "financiamento": False,
            "fgts": False,
            "observacoes": None,
            "created_at": None,
            "updated_at": None,
            "existe": False,
        }
    else:
        row = {**row, "existe": True}

    out = {
        k: row.get(k)
        for k in (
            "atendimento_id",
            "imovel_codigo",
            "valor_negociado",
            "pct_comissao",
            "tem_parceria",
            "pct_parceria",
            "pct_agencia",
            "pct_agentes",
            "pct_captador",
            "formas_pagamento",
            "parcelas",
            "financiamento",
            "fgts",
            "observacoes",
            "created_at",
            "updated_at",
            "existe",
        )
    }
    out["calculo"] = calcular(row, membros=membros, captador=captador)
    return out


def obter(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """The terms of this card's atendimento, plus the computed split."""
    atendimento_id = svc.resolve_atendimento_id(client, org_id, cliente_id)
    row = _linha(client, org_id, UUID(str(atendimento_id)))
    defaults = resolver_defaults(client, org_id)
    membros = _membros(client, org_id, cliente_id)
    captador_id = _captador(client, org_id, (row or {}).get("imovel_codigo"))
    captador = table_reads.actor(
        table_reads.resolve_actors({captador_id} if captador_id else set()),
        captador_id,
    )
    return _saida(
        row,
        UUID(str(atendimento_id)),
        defaults=defaults,
        membros=membros,
        captador=captador,
    )


def atualizar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    """Create or update this atendimento's terms. Absence means "leave alone"."""
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))

    recusados = sorted(set(valores) - set(CAMPOS_EDITAVEIS))
    if recusados:
        raise ValidationError_(
            f"Campos não editáveis: {', '.join(recusados)}", field=recusados[0]
        )

    atual = _linha(client, org_id, atendimento_id)
    patch = {k: v for k, v in valores.items() if k in CAMPOS_EDITAVEIS}

    # Decimals cross the wire as strings so PostgREST stores them exactly.
    for campo in ("valor_negociado", "pct_comissao", "pct_parceria", *_PERCENTUAIS_INTERNOS):
        if campo in patch and patch[campo] is not None:
            patch[campo] = str(_dec(patch[campo]))

    if atual is None:
        # 🔴 The one moment the org defaults are read for this row. From here
        # on the percentages are this agreement's own, and swapping the org
        # rule never touches them.
        defaults = resolver_defaults(client, org_id)
        base = {
            "atendimento_id": str(atendimento_id),
            "org_id": str(org_id),
            "tem_parceria": False,
            "financiamento": False,
            "fgts": False,
            "pct_parceria": str(defaults["pct_parceria"]),
            "pct_agencia": str(defaults["pct_agencia"]),
            "pct_agentes": str(defaults["pct_agentes"]),
            "pct_captador": str(defaults["pct_captador"]),
            "created_at": _now(),
            "created_por": str(usuario_id) if usuario_id else None,
        }
        if defaults.get("pct_comissao") is not None:
            base["pct_comissao"] = str(defaults["pct_comissao"])
        linha = {**base, **patch}
        _validar_split(linha)
        _t(client, TABLE).insert(linha).execute()
    else:
        _validar_split({**atual, **patch})
        patch["updated_at"] = _now()
        patch["updated_por"] = str(usuario_id) if usuario_id else None
        _t(client, TABLE).update(patch).eq("org_id", str(org_id)).eq(
            "atendimento_id", str(atendimento_id)
        ).execute()

    return obter(client, org_id, cliente_id)


def _validar_split(linha: dict) -> None:
    """The in-house split must total 100%.

    The DB has the same CHECK. This exists so the caller gets a named,
    actionable 400 instead of a driver-level 500 — the constraint is the
    backstop, not the message.
    """
    soma = sum(
        (_dec(linha.get(c)) or Decimal("0")) for c in _PERCENTUAIS_INTERNOS
    )
    if soma != Decimal("100"):
        raise ValidationError_(
            "A divisão interna (agência + agentes + captador) precisa somar "
            f"100% — informado: {soma}%",
            field="pct_agencia",
        )


def obter_defaults(client: Any, org_id: UUID) -> dict:
    resolvido = resolver_defaults(client, org_id)
    return {
        k: (str(v) if v is not None else None) for k, v in resolvido.items()
    }


def atualizar_defaults(
    client: Any, org_id: UUID, *, valores: dict, usuario_id: Optional[UUID]
) -> dict:
    """Swap the org's business rule.

    🔴 Existing negociações are NOT touched — that is the entire reason the
    percentages are copied onto each row. This changes what the NEXT deal
    starts from.
    """
    permitidos = ("pct_comissao", "pct_parceria", *_PERCENTUAIS_INTERNOS)
    recusados = sorted(set(valores) - set(permitidos))
    if recusados:
        raise ValidationError_(
            f"Campos não editáveis: {', '.join(recusados)}", field=recusados[0]
        )

    atual = (
        _t(client, DEFAULTS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .limit(1)
        .execute()
    ).data or []

    patch = {
        k: (str(_dec(v)) if v is not None else None) for k, v in valores.items()
    }
    _validar_split({**(atual[0] if atual else _defaults_como_linha()), **patch})

    if atual:
        patch["updated_at"] = _now()
        patch["updated_por"] = str(usuario_id) if usuario_id else None
        _t(client, DEFAULTS_TABLE).update(patch).eq("org_id", str(org_id)).execute()
    else:
        linha = {
            "org_id": str(org_id),
            **_defaults_como_linha(),
            **patch,
            "created_at": _now(),
            "updated_por": str(usuario_id) if usuario_id else None,
        }
        _t(client, DEFAULTS_TABLE).insert(linha).execute()

    return obter_defaults(client, org_id)


def _defaults_como_linha() -> dict:
    return {k: str(v) for k, v in DEFAULTS.items()}


__all__ = [
    "CAMPOS_EDITAVEIS",
    "DEFAULTS",
    "TABLE",
    "atualizar",
    "atualizar_defaults",
    "calcular",
    "obter",
    "obter_defaults",
    "resolver_defaults",
]
