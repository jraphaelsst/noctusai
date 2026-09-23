"""Negociação estruturada — the deal terms a contract instrument needs
(migration 108): structured parcelas, favorecidos, intermediários, and the
org's standing testemunhas; plus (migration 114) the per-deal CLAUSES the
contract generator prints: posse, itens integrantes / ad corpus, ônus,
confissão de dívida, corretagem, permuta-as-payment, and PF/PJ qualification
of intermediários.

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

`atendimento_negociacao_termos` (114) is a SEPARATE one-row table rather than
more columns on `atendimento_negociacao`, so that table keeps its single
writer (`negociacao_service._gravar`, which materialises the split defaults on
first insert). See migration 114's header.

🔴 `saldo_nao_alocado` AND `completude` NEVER BLOCK A SAVE
-------------------------------------------------------------
Every write here accepts a partial state — a parcela with no `vencimento`, a
schedule that does not yet cover `valor_negociado`, a permuta parcela with no
imóvel linked yet. `saldo_nao_alocado` (valor_negociado − Σ parcelas) and
`completude` (what a contract still lacks) are REPORTED, never enforced:
terms are drafted over several sittings. What IS refused (400) is a value that
is WRONG rather than missing — an invalid CPF, a negative prazo, a marco
'parcela' that does not name its parcela.

🔴 LGPD — favorecidos AND intermediários CARRY PERSONAL DATA
--------------------------------------------------------------
CPF/CNPJ, bank data, e-mail, address. Nothing in this module logs a row or a
field value; only ids and counts may ever be logged (migrations 108 + 114).

Auth is not re-tested here — `test_auth_boundary.py` (existing) and
`test_auth_boundary_negociacao_estruturada.py` (this surface's routes)
enumerate every mounted card_hub route and assert a strict 401 on each.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional
from uuid import UUID, uuid4

from noctusai_lib.domain.real_estate import dividir_em_parcelas_iguais
from noctusai_lib.integrations.documents import cnpj, cpf
from noctusai_lib.primitives.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError_,
)

from app.modules.card_hub import negociacao_service
from app.modules.card_hub import services as svc
from app.services import table_reads

TABLE_PARCELAS = "atendimento_negociacao_parcelas"
TABLE_FAVORECIDOS = "atendimento_favorecidos"
TABLE_INTERMEDIARIOS = "atendimento_intermediarios"
TABLE_TERMOS = "atendimento_negociacao_termos"
TABLE_PARCELA_PERMUTA_ATIVOS = "atendimento_parcela_permuta_ativos"

TIPOS_PARCELA: tuple[str, ...] = (
    "sinal", "intermediaria", "financiamento", "fgts", "saldo", "direta",
    "permuta",
)
TIPOS_INTERMEDIARIO: tuple[str, ...] = ("percentual", "valor_fixo")
PESSOA_TIPOS: tuple[str, ...] = ("pf", "pj")

#: Migration 114 vocabularies — mirrored by the DB CHECKs.
POSSE_MARCOS: tuple[str, ...] = ("assinatura", "parcela", "protocolo_registro")
ONUS_QUITACOES: tuple[str, ...] = (
    "compradores_prazo", "interveniente_quitante", "parcela", "ja_quitado",
)
CORRETAGEM_CONTRATANTES: tuple[str, ...] = ("vendedores", "compradores", "partes")

#: The only `permuta_ativos.natureza` that is payment currency — a property
#: BROUGHT to the deal (101). A catalog `imovel` or an automobile is not.
NATUREZA_PERMUTA_PAGAMENTO = "permuta_imovel"

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
    "favorecido_id", "confissao_divida", "ordem", "dispara_corretagem",
)
#: NOT NULL columns on the parcela row — an explicit `null` in a PATCH is a
#: 400 naming the field, never a driver-level 500.
_PARCELA_CAMPOS_NAO_NULOS: tuple[str, ...] = (
    "tipo", "valor", "confissao_divida", "ordem", "dispara_corretagem",
)
_FAVORECIDO_CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "nome", "cpf_cnpj", "banco", "agencia", "conta", "pix",
)
#: Same column set as `clientes.endereco_*` (097).
ENDERECO_CAMPOS: tuple[str, ...] = (
    "endereco_cep", "endereco_logradouro", "endereco_numero",
    "endereco_complemento", "endereco_bairro", "endereco_cidade", "endereco_uf",
)
_INTERMEDIARIO_QUALIFICACAO: tuple[str, ...] = (
    "favorecido_id", "pessoa_tipo", "documento", "email", *ENDERECO_CAMPOS,
    "representante_nome", "representante_cpf",
)
_INTERMEDIARIO_CAMPOS_EDITAVEIS: tuple[str, ...] = (
    "corretor_id", "nome", "creci", "tipo", "valor", *_INTERMEDIARIO_QUALIFICACAO,
)

#: Every clause `atendimento_negociacao_termos` holds (114). PUT replaces the
#: whole set — an absent key is written as null.
TERMOS_CAMPOS: tuple[str, ...] = (
    "posse_prazo_dias", "posse_marco", "posse_marco_parcela_id",
    "permuta_posse_prazo_dias", "permuta_posse_marco",
    "permuta_posse_marco_parcela_id", "permuta_obrigacoes_entrega",
    "itens_integrantes", "itens_integrantes_ausente_confirmado", "ad_corpus",
    "obrigacoes_vendedor",
    "onus_quitacao", "onus_prazo_dias",
    "confissao_juros_am", "confissao_garantia",
    "corretagem_contratantes", "corretagem_num_parcelas",
)
_TERMOS_TEXTO: tuple[str, ...] = (
    "permuta_obrigacoes_entrega", "itens_integrantes", "obrigacoes_vendedor",
    "confissao_garantia",
)
#: Prazos in days: 0 is meaningful ("imediata"), negative is not.
_TERMOS_PRAZOS: dict[str, str] = {
    "posse_prazo_dias": "o prazo de posse",
    "permuta_posse_prazo_dias": "o prazo de posse do imóvel da permuta",
    "onus_prazo_dias": "o prazo de quitação do ônus",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UF_RE = re.compile(r"^[A-Z]{2}$")


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


def _texto(value: Any) -> Optional[str]:
    """Stripped text; blank is `None` — a cleared field, not an empty string
    a contract would print."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


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
    # an access log to preserve. Any parcela / intermediário pointing at it
    # goes NULL via the migrations' `ON DELETE SET NULL`, never orphaned or
    # blocked.
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
        **{campo: row.get(campo) for campo in _INTERMEDIARIO_QUALIFICACAO},
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


def _normalizar_documento(bruto: str) -> tuple[str, str]:
    """`(documento normalizado, 'pf'|'pj')`, or a named 400.

    Eleven digits is a CPF, fourteen characters a CNPJ (alphanumeric since
    July 2026 — see `noctusai_lib.integrations.documents.cnpj`). Check digits
    are verified: a typo'd document printed into a contract qualifies the
    wrong person.
    """
    s = cnpj.normalize(bruto)
    if len(s) == 11 and s.isdigit():
        if not cpf.is_valid(s):
            raise ValidationError_(
                "CPF inválido: os dígitos verificadores não conferem",
                field="documento",
            )
        return s, "pf"
    if len(s) == 14:
        if not cnpj.is_valid(s):
            raise ValidationError_(
                "CNPJ inválido: os dígitos verificadores não conferem",
                field="documento",
            )
        return s, "pj"
    raise ValidationError_(
        "documento deve ser um CPF (11 dígitos) ou um CNPJ (14 caracteres)",
        field="documento",
    )


def _normalizar_qualificacao(
    client: Any, org_id: UUID, atendimento_id: UUID, valores: dict,
    atual: Optional[dict],
) -> dict:
    """The PF/PJ qualification fields (114) present in `valores`, validated
    and normalised. `atual` is the stored row on an update (None on create) —
    `pessoa_tipo` and `documento` are checked against each other using the
    value that will be stored, whichever side of the pair the caller sent."""
    atual = atual or {}
    out: dict = {}

    for campo in (
        "email", "representante_nome", "endereco_logradouro", "endereco_numero",
        "endereco_complemento", "endereco_bairro", "endereco_cidade",
    ):
        if campo in valores:
            out[campo] = _texto(valores[campo])
    if out.get("email") and not _EMAIL_RE.match(out["email"]):
        raise ValidationError_("e-mail inválido", field="email")

    if "endereco_uf" in valores:
        uf = _texto(valores["endereco_uf"])
        if uf is not None:
            uf = uf.upper()
            if not _UF_RE.match(uf):
                raise ValidationError_("UF deve ter 2 letras", field="endereco_uf")
        out["endereco_uf"] = uf

    if "endereco_cep" in valores:
        cep = _texto(valores["endereco_cep"])
        if cep is not None:
            cep = re.sub(r"\D", "", cep)
            if len(cep) != 8:
                raise ValidationError_("CEP deve ter 8 dígitos", field="endereco_cep")
        out["endereco_cep"] = cep

    if "representante_cpf" in valores:
        rep = _texto(valores["representante_cpf"])
        if rep is not None:
            if not cpf.is_valid(rep):
                raise ValidationError_(
                    "CPF do representante inválido: os dígitos verificadores não conferem",
                    field="representante_cpf",
                )
            rep = cpf.only_digits(rep)
        out["representante_cpf"] = rep

    if "favorecido_id" in valores:
        if valores["favorecido_id"]:
            _exigir_favorecido(
                client, org_id, atendimento_id, UUID(str(valores["favorecido_id"]))
            )
            out["favorecido_id"] = str(valores["favorecido_id"])
        else:
            out["favorecido_id"] = None

    pessoa_tipo = (
        valores.get("pessoa_tipo") if "pessoa_tipo" in valores
        else atual.get("pessoa_tipo")
    )
    if pessoa_tipo is not None and pessoa_tipo not in PESSOA_TIPOS:
        raise ValidationError_(
            f"pessoa_tipo inválido: {pessoa_tipo!r}. Permitidos: pf, pj",
            field="pessoa_tipo",
        )
    documento = atual.get("documento")
    if "documento" in valores:
        bruto = _texto(valores["documento"])
        if bruto is None:
            documento = None
        else:
            documento, tipo_do_documento = _normalizar_documento(bruto)
            # The document says which kind of person this is when the caller
            # did not — never the other way round (see the mismatch below).
            if pessoa_tipo is None and "pessoa_tipo" not in valores:
                pessoa_tipo = tipo_do_documento
                out["pessoa_tipo"] = pessoa_tipo
        out["documento"] = documento
    if "pessoa_tipo" in valores:
        out["pessoa_tipo"] = pessoa_tipo

    if documento:
        esperado = "pf" if len(documento) == 11 else "pj"
        if pessoa_tipo is None:
            raise ValidationError_(
                "informe se o intermediário é pessoa física (pf) ou jurídica (pj)",
                field="pessoa_tipo",
            )
        if pessoa_tipo != esperado:
            raise ValidationError_(
                "pessoa física exige CPF (11 dígitos)" if pessoa_tipo == "pf"
                else "pessoa jurídica exige CNPJ (14 caracteres)",
                field="documento",
            )
    return out


def criar_intermediario(
    client: Any, org_id: UUID, cliente_id: UUID, *, valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    tipo = valores.get("tipo") or "percentual"
    _validar_intermediario_valor(tipo, _dec(valores.get("valor")))
    # A create body is `model_dump()`ed, so every omitted field arrives as
    # None — on a CREATE that means "not sent" (nothing to clear), and
    # treating it as an explicit null would stop `pessoa_tipo` being inferred
    # from the documento.
    qualificacao = _normalizar_qualificacao(
        client, org_id, atendimento_id,
        {k: v for k, v in valores.items() if v is not None}, None,
    )
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
        **{campo: qualificacao.get(campo) for campo in _INTERMEDIARIO_QUALIFICACAO},
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

    for campo in ("nome", "tipo"):
        if campo in valores and valores[campo] is None:
            raise ValidationError_(f"{campo} não pode ser nulo", field=campo)

    tipo = valores.get("tipo", atual.get("tipo", "percentual"))
    if "valor" in valores:
        _validar_intermediario_valor(tipo, _dec(valores.get("valor")))

    patch: dict = _normalizar_qualificacao(
        client, org_id, atendimento_id, valores, atual
    )
    for campo in ("corretor_id", "nome", "creci", "tipo", "valor"):
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


# ─── permuta: parcela <-> permuta_ativos (114) ────────────────────────────


def _links_por_parcela(
    client: Any, org_id: UUID, parcela_ids: Iterable[str]
) -> dict[str, list[str]]:
    """`{parcela_id: [permuta_ativo_id, ...]}` for the given parcelas, in
    link-creation order. Batched `.in_()` (URL-length cap) over the seed pager
    (row cap) — `KB § PATTERNS/backend/postgrest-row-cap.md`."""
    ids = [str(p) for p in parcela_ids]
    mapa: dict[str, list[str]] = {pid: [] for pid in ids}
    if not ids:
        return mapa
    rows: list[dict] = []
    for lote in table_reads.batched(ids):
        rows.extend(
            table_reads.paged_rows(
                client, TABLE_PARCELA_PERMUTA_ATIVOS, org_id,
                refine=lambda q, lote=lote: q.in_("parcela_id", lote),
            )
        )
    rows.sort(key=lambda r: r.get("created_at") or "")
    for r in rows:
        mapa.setdefault(str(r["parcela_id"]), []).append(str(r["permuta_ativo_id"]))
    return mapa


def _validar_ativos_permuta(
    client: Any, org_id: UUID, atendimento_id: UUID, ativo_ids: Iterable[Any],
    *, parcela_id: Optional[UUID] = None,
) -> list[str]:
    """The de-duplicated ids, once each is proven linkable:

    - 404 naming the id for an unknown ativo OR one of another org (the same
      non-distinguishing shape every `_exigir_*` here uses — RLS-shaped);
    - 400 when the ativo is not `natureza='permuta_imovel'` — a catalog
      listing or an automobile is not currency this contract can print;
    - 400 when the ativo already pays ANOTHER parcela of this deal.

    The DB trigger in migration 114 holds the first two for writers that
    bypass this; the third is service-only (see that header).
    """
    unicos = list(dict.fromkeys(str(a) for a in ativo_ids))
    if not unicos:
        return []
    encontrados: dict[str, dict] = {}
    for lote in table_reads.batched(unicos):
        # postgrest-unbounded-ok: `id` is the primary key and `lote` is one
        # `batched()` chunk, so the result has at most len(lote) rows.
        rows = (
            _t(client, "permuta_ativos")
            .select("id, natureza")
            .eq("org_id", str(org_id))
            .in_("id", lote)
            .execute()
        ).data or []
        encontrados.update({str(r["id"]): r for r in rows})
    for ativo_id in unicos:
        linha = encontrados.get(ativo_id)
        if linha is None:
            raise NotFoundError("permuta_ativos", ativo_id)
        if linha.get("natureza") != NATUREZA_PERMUTA_PAGAMENTO:
            raise ValidationError_(
                f"o ativo {ativo_id} não é um imóvel de permuta "
                "(natureza permuta_imovel) e não pode pagar uma parcela",
                field="permuta_ativo_ids",
            )

    outras = [
        str(p["id"]) for p in _listar_parcelas_rows(client, org_id, atendimento_id)
        if str(p["id"]) != str(parcela_id)
    ]
    em_uso = {
        a for lista in _links_por_parcela(client, org_id, outras).values()
        for a in lista
    }
    for ativo_id in unicos:
        if ativo_id in em_uso:
            raise ValidationError_(
                f"o imóvel de permuta {ativo_id} já está vinculado a outra "
                "parcela desta negociação",
                field="permuta_ativo_ids",
            )
    return unicos


def _gravar_links(
    client: Any, org_id: UUID, parcela_id: str, ativo_ids: list[str],
    *, usuario_id: Optional[UUID],
) -> None:
    if not ativo_ids:
        return
    _t(client, TABLE_PARCELA_PERMUTA_ATIVOS).insert([
        {
            "id": str(uuid4()),
            "org_id": str(org_id),
            "parcela_id": str(parcela_id),
            "permuta_ativo_id": ativo_id,
            "created_at": _now(),
            "created_por": str(usuario_id) if usuario_id else None,
        }
        for ativo_id in ativo_ids
    ]).execute()


def _apagar_links(client: Any, org_id: UUID, parcela_id: Any) -> None:
    _t(client, TABLE_PARCELA_PERMUTA_ATIVOS).delete().eq("org_id", str(org_id)).eq(
        "parcela_id", str(parcela_id)
    ).execute()


# ─── parcelas ─────────────────────────────────────────────────────────────


def _parcela_out(row: dict, links: dict[str, list[str]]) -> dict:
    return {
        "id": row["id"],
        "tipo": row["tipo"],
        "valor": str(_dec(row.get("valor")) or Decimal("0")),
        "vencimento": row.get("vencimento"),
        "evento": row.get("evento"),
        "forma_pagamento": row.get("forma_pagamento"),
        "favorecido_id": row.get("favorecido_id"),
        "confissao_divida": bool(row.get("confissao_divida", False)),
        "dispara_corretagem": bool(row.get("dispara_corretagem", False)),
        "permuta_ativo_ids": list(links.get(str(row["id"]), [])),
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


_MSG_ATIVOS_SO_EM_PERMUTA = (
    "imóveis de permuta só podem ser vinculados a uma parcela do tipo permuta"
)


def criar_parcela(
    client: Any, org_id: UUID, cliente_id: UUID, *, valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    if valores.get("favorecido_id"):
        _exigir_favorecido(client, org_id, atendimento_id, UUID(str(valores["favorecido_id"])))

    tipo = valores["tipo"]
    ativos_pedidos = valores.get("permuta_ativo_ids") or []
    if ativos_pedidos and tipo != "permuta":
        raise ValidationError_(_MSG_ATIVOS_SO_EM_PERMUTA, field="permuta_ativo_ids")
    ativos = _validar_ativos_permuta(client, org_id, atendimento_id, ativos_pedidos)

    # 🔴 `ordem` is ALWAYS server-computed on create — same "next slot after
    # the current max" rule `dividir_saldo_em_parcelas` already uses for its
    # batch insert (`ordem_base = max(existing) + 1`). Every parcela created
    # through THIS path used to land at the schema default `ordem=0`
    # (`ParcelaCreateBody` never accepted the field, so every single-create
    # parcela tied at 0) — see migration 108's header for why the printed
    # "Parcela 01/02/03" numbering, the `VENCIMENTOS_FORA_DE_ORDEM` derivação
    # blocker, and `posse_marco_parcela_id` all rest on this column actually
    # being distinct per parcela (see migration 144's backfill for existing rows).
    parcelas_atuais = _listar_parcelas_rows(client, org_id, atendimento_id)
    ordem = max((p.get("ordem", 0) for p in parcelas_atuais), default=-1) + 1

    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "atendimento_id": str(atendimento_id),
        "tipo": tipo,
        "valor": str(_dec(valores["valor"])),
        "vencimento": valores.get("vencimento"),
        "evento": valores.get("evento"),
        "forma_pagamento": valores.get("forma_pagamento"),
        "favorecido_id": (
            str(valores["favorecido_id"]) if valores.get("favorecido_id") else None
        ),
        "confissao_divida": bool(valores.get("confissao_divida", False)),
        "dispara_corretagem": bool(valores.get("dispara_corretagem", False)),
        "ordem": ordem,
        "created_at": _now(),
        "created_por": str(usuario_id) if usuario_id else None,
    }
    _t(client, TABLE_PARCELAS).insert(row).execute()
    # After the parcela exists: migration 114's link trigger reads its tipo.
    _gravar_links(client, org_id, row["id"], ativos, usuario_id=usuario_id)
    return obter_estruturada(client, org_id, cliente_id)


def atualizar_parcela(
    client: Any, org_id: UUID, cliente_id: UUID, parcela_id: UUID, *,
    valores: dict, usuario_id: Optional[UUID],
) -> dict:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    atual = _exigir_parcela(client, org_id, atendimento_id, parcela_id)

    for campo in _PARCELA_CAMPOS_NAO_NULOS:
        if campo in valores and valores[campo] is None:
            raise ValidationError_(f"{campo} não pode ser nulo", field=campo)

    tipo_final = valores.get("tipo", atual["tipo"])
    substituir_links = "permuta_ativo_ids" in valores
    if substituir_links:
        pedidos = valores["permuta_ativo_ids"] or []
        if pedidos and tipo_final != "permuta":
            raise ValidationError_(_MSG_ATIVOS_SO_EM_PERMUTA, field="permuta_ativo_ids")
        links_finais = _validar_ativos_permuta(
            client, org_id, atendimento_id, pedidos, parcela_id=parcela_id
        )
    else:
        links_finais = _links_por_parcela(client, org_id, [str(parcela_id)])[str(parcela_id)]
        if links_finais and tipo_final != "permuta":
            raise ValidationError_(
                "remova os imóveis de permuta desta parcela antes de mudar o tipo",
                field="tipo",
            )

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

    # Write order matters against migration 114's triggers: old links go
    # BEFORE a tipo change away from 'permuta'; new links go AFTER a tipo
    # change to 'permuta'.
    if substituir_links:
        _apagar_links(client, org_id, parcela_id)
    _t(client, TABLE_PARCELAS).update(patch).eq("org_id", str(org_id)).eq(
        "id", str(parcela_id)
    ).execute()
    if substituir_links:
        _gravar_links(client, org_id, str(parcela_id), links_finais, usuario_id=usuario_id)
    return obter_estruturada(client, org_id, cliente_id)


def remover_parcela(
    client: Any, org_id: UUID, cliente_id: UUID, parcela_id: UUID,
) -> None:
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    _exigir_parcela(client, org_id, atendimento_id, parcela_id)

    # A parcela named as a posse marco cannot vanish from under the clause
    # that cites it — migration 114's FK is NO ACTION on purpose; this is the
    # named message instead of that FK's 500.
    termos = _termos_linha(client, org_id, atendimento_id) or {}
    for campo, rotulo in (
        ("posse_marco_parcela_id", "da posse"),
        ("permuta_posse_marco_parcela_id", "da posse do imóvel da permuta"),
    ):
        if termos.get(campo) and str(termos[campo]) == str(parcela_id):
            raise ConflictError(
                f"esta parcela é o marco {rotulo} nos termos do negócio — "
                "altere o marco antes de removê-la",
                resource=TABLE_PARCELAS,
            )

    # The DB CASCADEs these; deleting them explicitly first keeps the service
    # correct on its own terms rather than on a side effect.
    _apagar_links(client, org_id, parcela_id)
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
            "dispara_corretagem": False,
            "ordem": ordem_base + i,
            "created_at": _now(),
            "created_por": str(usuario_id) if usuario_id else None,
        })
    _t(client, TABLE_PARCELAS).insert(rows).execute()
    return obter_estruturada(client, org_id, cliente_id)


# ─── termos do negócio (114) ──────────────────────────────────────────────


def _termos_linha(client: Any, org_id: UUID, atendimento_id: UUID) -> Optional[dict]:
    rows = (
        _t(client, TABLE_TERMOS)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _termos_out(row: Optional[dict]) -> dict:
    row = row or {}
    out = {campo: row.get(campo) for campo in TERMOS_CAMPOS}
    juros = _dec(row.get("confissao_juros_am"))
    out["confissao_juros_am"] = None if juros is None else str(juros)
    for campo in ("posse_marco_parcela_id", "permuta_posse_marco_parcela_id"):
        out[campo] = None if row.get(campo) is None else str(row[campo])
    return out


def _inteiro_ou_none(valor: Any, campo: str) -> Optional[int]:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValidationError_(f"{campo} deve ser um número inteiro", field=campo)
    return valor


def atualizar_termos(
    client: Any, org_id: UUID, cliente_id: UUID, *, valores: dict,
    usuario_id: Optional[UUID],
) -> dict:
    """PUT — replace this atendimento's clauses as a whole (an absent key is
    stored as null). Returns the aggregate, like every other write here.

    Refuses what is WRONG (a negative prazo, juros outside 0–100% a.m., a
    marco 'parcela' without its parcela or pointing at another deal's), never
    what is merely MISSING — see this module's header.
    """
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))

    recusados = sorted(set(valores) - set(TERMOS_CAMPOS))
    if recusados:
        raise ValidationError_(
            f"Campos não editáveis: {', '.join(recusados)}", field=recusados[0]
        )

    termos: dict = {campo: valores.get(campo) for campo in TERMOS_CAMPOS}

    for campo in _TERMOS_TEXTO:
        termos[campo] = _texto(termos[campo])

    for campo, rotulo in _TERMOS_PRAZOS.items():
        termos[campo] = _inteiro_ou_none(termos[campo], campo)
        if termos[campo] is not None and termos[campo] < 0:
            raise ValidationError_(f"{rotulo} não pode ser negativo", field=campo)

    termos["corretagem_num_parcelas"] = _inteiro_ou_none(
        termos["corretagem_num_parcelas"], "corretagem_num_parcelas"
    )
    if termos["corretagem_num_parcelas"] is not None and termos["corretagem_num_parcelas"] < 1:
        raise ValidationError_(
            "o número de parcelas da corretagem deve ser maior que zero",
            field="corretagem_num_parcelas",
        )

    if termos["confissao_juros_am"] is not None:
        try:
            juros = _dec(termos["confissao_juros_am"])
        except InvalidOperation:
            juros = None
        if juros is None or not (Decimal("0") <= juros <= Decimal("100")):
            raise ValidationError_(
                "os juros da confissão de dívida devem estar entre 0 e 100% ao mês",
                field="confissao_juros_am",
            )
        termos["confissao_juros_am"] = str(juros)

    if termos["ad_corpus"] is not None and not isinstance(termos["ad_corpus"], bool):
        raise ValidationError_("ad_corpus deve ser verdadeiro ou falso", field="ad_corpus")

    # Belt-and-suspenders with the router's `Literal` fields — mirrors
    # `contratos_service.atualizar`.
    for campo, permitidos in (
        ("posse_marco", POSSE_MARCOS),
        ("permuta_posse_marco", POSSE_MARCOS),
        ("onus_quitacao", ONUS_QUITACOES),
        ("corretagem_contratantes", CORRETAGEM_CONTRATANTES),
    ):
        if termos[campo] is not None and termos[campo] not in permitidos:
            raise ValidationError_(
                f"{campo} inválido: {termos[campo]!r}. "
                f"Permitidos: {', '.join(permitidos)}",
                field=campo,
            )

    for prefixo, rotulo in (
        ("posse", "a entrega da posse"),
        ("permuta_posse", "a entrega do imóvel da permuta"),
    ):
        campo_marco = f"{prefixo}_marco"
        campo_parcela = f"{prefixo}_marco_parcela_id"
        parcela_id = termos[campo_parcela]
        if termos[campo_marco] == "parcela":
            if not parcela_id:
                raise ValidationError_(
                    f"informe a parcela que marca {rotulo}", field=campo_parcela
                )
            _exigir_parcela(client, org_id, atendimento_id, UUID(str(parcela_id)))
            termos[campo_parcela] = str(parcela_id)
        elif parcela_id:
            raise ValidationError_(
                f"{campo_parcela} só se aplica quando {campo_marco} é 'parcela'",
                field=campo_parcela,
            )
        else:
            termos[campo_parcela] = None

    atual = _termos_linha(client, org_id, atendimento_id)
    if atual is None:
        _t(client, TABLE_TERMOS).insert({
            "atendimento_id": str(atendimento_id),
            "org_id": str(org_id),
            **termos,
            "created_at": _now(),
            "created_por": str(usuario_id) if usuario_id else None,
        }).execute()
    else:
        _t(client, TABLE_TERMOS).update({
            **termos,
            "updated_at": _now(),
            "updated_por": str(usuario_id) if usuario_id else None,
        }).eq("org_id", str(org_id)).eq("atendimento_id", str(atendimento_id)).execute()
    return obter_estruturada(client, org_id, cliente_id)


# ─── the aggregate view ───────────────────────────────────────────────────


def _completude(
    negociacao: dict, parcelas: list[dict], termos: dict,
    links: dict[str, list[str]],
) -> dict:
    """What this contract's terms still lack. NEVER used to refuse a save —
    see this module's header. An interpretation call: scoped to the fields
    THIS module manages (valor/parcelas/posse/permuta), not the full
    instrument.

    `posse` is satisfied by the 114 clause (marco + prazo) OR the legacy
    108 `posse_data` — a deal drafted before 114 is not suddenly incomplete.
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
    posse_por_termos = bool(termos.get("posse_marco")) and termos.get("posse_prazo_dias") is not None
    if not (posse_por_termos or negociacao.get("posse_data")):
        faltando.append("posse")
    if any(
        p.get("tipo") == "permuta" and not links.get(str(p["id"]))
        for p in parcelas
    ):
        faltando.append("parcela_permuta_sem_imoveis")
    return {"completo": not faltando, "faltando": faltando}


def obter_estruturada(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Parcelas + favorecidos + intermediários + termos + the computed saldo
    and completeness block, for one atendimento."""
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    negociacao = negociacao_service.obter(client, org_id, cliente_id)

    parcelas_rows = _listar_parcelas_rows(client, org_id, atendimento_id)
    favorecidos_rows = _listar_favorecidos_rows(client, org_id, atendimento_id)
    intermediarios_rows = _listar_intermediarios_rows(client, org_id, atendimento_id)
    termos = _termos_out(_termos_linha(client, org_id, atendimento_id))
    links = _links_por_parcela(client, org_id, [str(p["id"]) for p in parcelas_rows])

    valor_negociado = _dec(negociacao.get("valor_negociado"))
    saldo_nao_alocado: Optional[str] = None
    if valor_negociado is not None:
        alocado = sum((_dec(p.get("valor")) or Decimal("0")) for p in parcelas_rows)
        saldo_nao_alocado = str(valor_negociado - alocado)

    return {
        "atendimento_id": str(atendimento_id),
        "valor_negociado": negociacao.get("valor_negociado"),
        "saldo_nao_alocado": saldo_nao_alocado,
        # LEGACY (114): superseded by `termos.posse_*` / permuta parcelas —
        # still returned for the existing panel.
        "posse_data": negociacao.get("posse_data"),
        "posse_condicoes": negociacao.get("posse_condicoes"),
        "permuta_ativo_id": negociacao.get("permuta_ativo_id"),
        "parcelas": [_parcela_out(r, links) for r in parcelas_rows],
        "favorecidos": [_favorecido_out(r) for r in favorecidos_rows],
        "intermediarios": [_intermediario_out(r) for r in intermediarios_rows],
        "termos": termos,
        "completude": _completude(negociacao, parcelas_rows, termos, links),
    }


__all__ = [
    "CORRETAGEM_CONTRATANTES",
    "ENDERECO_CAMPOS",
    "FORMAS_PAGAMENTO_SUGERIDAS",
    "ONUS_QUITACOES",
    "PESSOA_TIPOS",
    "POSSE_MARCOS",
    "TABLE_FAVORECIDOS",
    "TABLE_INTERMEDIARIOS",
    "TABLE_PARCELAS",
    "TABLE_PARCELA_PERMUTA_ATIVOS",
    "TABLE_TERMOS",
    "TERMOS_CAMPOS",
    "TIPOS_INTERMEDIARIO",
    "TIPOS_PARCELA",
    "atualizar_favorecido",
    "atualizar_intermediario",
    "atualizar_parcela",
    "atualizar_termos",
    "criar_favorecido",
    "criar_intermediario",
    "criar_parcela",
    "dividir_saldo_em_parcelas",
    "obter_estruturada",
    "remover_favorecido",
    "remover_intermediario",
    "remover_parcela",
]
