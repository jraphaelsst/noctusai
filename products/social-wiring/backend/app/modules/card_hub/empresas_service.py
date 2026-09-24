"""`GET/POST /api/clientes/{cliente_id}/empresas` (P0c contract §D1/§D2) —
the card's "which companies is this deal's people tied to, and do they need
PJ certidões" panel.

WHO COUNTS ("owners")
----------------------
The titular (`atendimentos.cliente_id`, always a comprador — migration 073's
header), every `atendimento_partes` row on BOTH sides, and — vendedor side
only — each vendedor's registered spouse via `clientes.conjuge_cliente_id`
(migration 153's D1 link), even when that spouse never got added as its own
`atendimento_partes` row. `certificando` (per owner): a vendedor or their
spouse always counts; a comprador (the titular included) or their spouse
counts ONLY when the deal `tem_permuta` — the permuta comprador stands in a
seller-like position for THAT parcela (contract §E1/§H11).

🔴 THIS MODULE DOES **NOT** IMPORT `contrato_gerador` (S2b's territory)
-------------------------------------------------------------------------
`exige_certidoes`/`motivo` below is a DELIBERATE, MINIMAL re-statement of
the SAME E1 classification `contrato_gerador.derivacao.classificar_empresa`
implements for the contract-GENERATION gate — not a shared import, because
that module is a sibling slice's (S2b) in-flight file. Both read the SAME
`politica.SITUACOES_PJ_EXIGIDAS` / `politica.PoliticaCertidoes.
pj_baixada_janela_anos` constants (a neutral, already-shipped file neither
slice owns), so a policy change moves both at once even though the
CLASSIFICATION CODE itself is duplicated. This is a KNOWN, ACCEPTED
recurrence (N=2, not yet the N=3 MUST-formalize threshold) — surfaced in
this dispatch's own `scoped-improvement:` footer as a follow-up: lift both
call sites onto one shared `classificar_empresa` once S2b's rewrite lands
and the two can be reconciled without editing each other's file mid-flight.
`exige_certidoes` here is DISPLAY-ONLY (an informational badge) and is
NEVER the gate that blocks contract generation — that gate stays entirely
in `contrato_gerador.validacao_extracao`/`derivacao`.

`tem_permuta` is resolved via a direct, lightweight read of `atendimento_
negociacao_parcelas` (owned by `card_hub.negociacao_estruturada_service`,
not `contrato_gerador`) rather than through `contrato_gerador.dados.
parcela_permuta`, which needs the WHOLE `DadosContrato` graph loaded — too
heavy (and too coupled to S2b's carregador) for a card listing read.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub.contrato_gerador import politica
from app.modules.card_hub.services import (
    AmbiguousAtendimento,
    ensure_cliente,
    resolve_atendimento_id,
)
from app.modules.empresas import dados_service
from app.services import table_reads

CLIENTES_TABLE = "clientes"
ATENDIMENTOS_TABLE = "atendimentos"
PARTES_TABLE = "atendimento_partes"
PARCELAS_TABLE = "atendimento_negociacao_parcelas"
PARTICIPACOES_TABLE = "cliente_empresa_participacoes"
EMPRESAS_TABLE = "empresas"

#: No `uf` — `empresas` models no address/UF at all (owner decision,
#: 2026-09-24, twice-confirmed; see `dados_service`'s module docstring).
_EMPRESA_CAMPOS = (
    "id", "cnpj", "razao_social", "nome_fantasia", "natureza_juridica",
    "data_abertura", "situacao_cadastral", "data_situacao_cadastral",
    "motivo_situacao", "dados_origem", "dados_confirmado_em",
)


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def _tem_permuta(client: Any, org_id: UUID, atendimento_id: str) -> bool:
    rows = (
        _t(client, PARCELAS_TABLE)
        .select("id")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", atendimento_id)
        .eq("tipo", "permuta")
        .limit(1)
        .execute()
    ).data or []
    return bool(rows)


def _pessoas_do_card(client: Any, org_id: UUID, atendimento: dict) -> list[dict]:
    """Every "who might own a PJ" person on this atendimento — see the
    module docstring's "WHO COUNTS" section. Returns
    `[{"cliente_id","lado","papel","certificando"}]`, deduped by
    `cliente_id` (first occurrence wins — the titular, listed first, is
    never shadowed by a `conjuge`-lado-comprador row that happens to name
    the same person)."""
    tem_permuta = _tem_permuta(client, org_id, str(atendimento["id"]))

    pessoas: list[dict] = [
        {
            "cliente_id": str(atendimento["cliente_id"]),
            "lado": "comprador",
            "papel": "comprador",
            "certificando": tem_permuta,
        }
    ]
    vistos = {pessoas[0]["cliente_id"]}

    partes = (
        _t(client, PARTES_TABLE)
        .select("cliente_id, lado, papel")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento["id"]))
        .execute()
    ).data or []
    for parte in partes:
        cid = str(parte["cliente_id"])
        if cid in vistos:
            continue
        vistos.add(cid)
        lado = parte.get("lado") or "comprador"
        pessoas.append(
            {
                "cliente_id": cid,
                "lado": lado,
                "papel": parte.get("papel") or "",
                "certificando": True if lado == "vendedor" else tem_permuta,
            }
        )

    # Every vendedor-side pessoa's registered spouse, even when that spouse
    # never got its own `atendimento_partes` row (a comprador's spouse
    # normally does, via `compradores_service.adicionar`; nothing forces a
    # vendedor's own registered spouse through the same path).
    vendedores = [p["cliente_id"] for p in pessoas if p["lado"] == "vendedor"]
    if vendedores:
        rows = (
            _t(client, CLIENTES_TABLE)
            .select("id, conjuge_cliente_id")
            .eq("org_id", str(org_id))
            .in_("id", vendedores)
            .execute()
        ).data or []
        for row in rows:
            conjuge_id = row.get("conjuge_cliente_id")
            if not conjuge_id or str(conjuge_id) in vistos:
                continue
            vistos.add(str(conjuge_id))
            pessoas.append(
                {
                    "cliente_id": str(conjuge_id),
                    "lado": "vendedor",
                    "papel": "conjuge",
                    "certificando": True,
                }
            )
    return pessoas


def _motivo_e_exigencia(empresa: dict, *, referencia: date) -> tuple[bool, str]:
    """E1's classification — see the module docstring for why this is a
    deliberate, minimal restatement rather than a `contrato_gerador` import.
    """
    situacao = empresa.get("situacao_cadastral")
    if situacao is None:
        return False, "sem_cartao_cnpj"
    if situacao in politica.SITUACOES_PJ_EXIGIDAS:
        return True, situacao
    if situacao == "baixada":
        data_situacao = empresa.get("data_situacao_cadastral")
        if not data_situacao:
            return False, "sem_cartao_cnpj"
        try:
            ano, mes, dia = (int(p) for p in str(data_situacao)[:10].split("-"))
            situacao_date = date(ano, mes, dia)
        except (ValueError, TypeError):
            return False, "sem_cartao_cnpj"
        janela = politica.PoliticaCertidoes().pj_baixada_janela_anos
        anos = referencia.year - situacao_date.year - (
            (referencia.month, referencia.day) < (situacao_date.month, situacao_date.day)
        )
        if anos < janela:
            return True, "baixada_menos_5_anos"
        return False, "baixada_5_anos_ou_mais"
    return False, "outra_situacao"


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """§D1's `GET`. Empty (`items: []`) — never a 409 — when the person has
    no open atendimento the resolver can name, or it is ambiguous: the card
    asks this on every open and has nothing to show either way, same
    posture `compradores_service.listar` takes."""
    ensure_cliente(client, org_id, cliente_id)
    try:
        atendimento_id = resolve_atendimento_id(client, org_id, cliente_id)
    except AmbiguousAtendimento:
        return {"atendimento_id": None, "referencia": date.today().isoformat(), "items": []}

    rows = (
        _t(client, ATENDIMENTOS_TABLE)
        .select("id, cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", atendimento_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return {"atendimento_id": None, "referencia": date.today().isoformat(), "items": []}
    atendimento = rows[0]

    pessoas = _pessoas_do_card(client, org_id, atendimento)
    pessoas_por_id = {p["cliente_id"]: p for p in pessoas}
    nomes = {
        str(r["id"]): (r.get("nome_oficial") or r.get("nome") or "")
        for r in (
            _t(client, CLIENTES_TABLE)
            .select("id, nome, nome_oficial")
            .eq("org_id", str(org_id))
            .in_("id", list(pessoas_por_id))
            .execute()
        ).data or []
    }

    participacoes = (
        _t(client, PARTICIPACOES_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .in_("cliente_id", list(pessoas_por_id))
        .execute()
    ).data or []
    if not participacoes:
        return {
            "atendimento_id": atendimento_id,
            "referencia": date.today().isoformat(), "items": [],
        }

    empresa_ids = sorted({p["empresa_id"] for p in participacoes})
    empresas = {
        str(r["id"]): r
        for r in (
            _t(client, EMPRESAS_TABLE)
            .select(",".join(_EMPRESA_CAMPOS))
            .eq("org_id", str(org_id))
            .in_("id", empresa_ids)
            .execute()
        ).data or []
    }

    referencia = date.today()
    items: list[dict] = []
    for empresa_id in empresa_ids:
        empresa = empresas.get(empresa_id)
        if empresa is None:
            continue
        owners = []
        for part in participacoes:
            if str(part["empresa_id"]) != empresa_id:
                continue
            pessoa = pessoas_por_id.get(str(part["cliente_id"]))
            if pessoa is None:
                continue
            owners.append(
                {
                    "cliente_id": pessoa["cliente_id"],
                    "nome": nomes.get(pessoa["cliente_id"], ""),
                    "lado": pessoa["lado"],
                    "papel": pessoa["papel"],
                    "participacao_pct": part.get("participacao_pct"),
                    "origem": part.get("origem"),
                    "certificando": pessoa["certificando"],
                }
            )
        if not owners:
            continue

        exige, motivo = _motivo_e_exigencia(empresa, referencia=referencia)
        if not any(o["certificando"] for o in owners):
            exige, motivo = False, "sem_socio_certificando"

        cartao_doc = (
            _t(client, "empresa_documentos")
            .select("id, extracao_status, extracao_descartada_em")
            .eq("org_id", str(org_id))
            .eq("empresa_id", empresa_id)
            .is_("deleted_at", "null")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        cartao_row = cartao_doc[0] if cartao_doc else None

        from app.modules.certidoes import service as certidoes_svc

        resultados = certidoes_svc.certidoes_por_empresa(client, org_id, empresa_id)
        por_resultado = {
            "negativa": 0, "positiva": 0, "positiva_com_efeito_de_negativa": 0,
            "negativa_com_homonimos": 0, "nao_emitida": 0, "pendente": 0,
        }
        for r in resultados:
            chave = r.get("resultado") or "pendente"
            por_resultado[chave] = por_resultado.get(chave, 0) + 1

        items.append(
            {
                "empresa": {k: empresa.get(k) for k in _EMPRESA_CAMPOS},
                "owners": owners,
                "cartao": {
                    "documento_id": (cartao_row or {}).get("id"),
                    "extracao_status": (cartao_row or {}).get("extracao_status"),
                    "extracao_descartada_em": (cartao_row or {}).get("extracao_descartada_em"),
                    "aviso": None,
                },
                "exige_certidoes": exige,
                "motivo": motivo,
                "certidoes": {
                    "consulta_ids": sorted({r["consulta_id"] for r in resultados}),
                    "total": len(resultados),
                    "por_resultado": por_resultado,
                },
            }
        )

    return {"atendimento_id": atendimento_id, "referencia": referencia.isoformat(), "items": items}


def adicionar_manual(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    cnpj: str,
    participante_cliente_id: UUID,
    razao_social: Optional[str] = None,
    participacao_pct: Optional[float] = None,
    confirmado_por: Optional[Any] = None,
) -> dict:
    """§D2's `POST` — a manual link. `participante_cliente_id` MUST be a
    participant on this card (the titular or an `atendimento_partes` row) —
    a caller cannot link an empresa to a stranger's participação."""
    from noctusai_lib.integrations.documents.cnpj import is_valid as cnpj_is_valid

    ensure_cliente(client, org_id, cliente_id)
    if not cnpj_is_valid(cnpj):
        raise ValidationError_(f"CNPJ inválido: {cnpj!r}", field="cnpj")

    try:
        atendimento_id = resolve_atendimento_id(client, org_id, cliente_id)
    except AmbiguousAtendimento:
        raise NotFoundError("atendimentos", str(cliente_id)) from None

    valido = str(participante_cliente_id) == str(cliente_id)
    if not valido:
        partes = (
            _t(client, PARTES_TABLE)
            .select("cliente_id")
            .eq("org_id", str(org_id))
            .eq("atendimento_id", atendimento_id)
            .eq("cliente_id", str(participante_cliente_id))
            .limit(1)
            .execute()
        ).data or []
        valido = bool(partes)
    if not valido:
        raise NotFoundError(PARTES_TABLE, str(participante_cliente_id))

    return dados_service.criar_ou_vincular_manual(
        client, org_id, participante_cliente_id,
        cnpj=cnpj, razao_social=razao_social,
        participacao_pct=participacao_pct, confirmado_por=confirmado_por,
    )


__all__ = ["adicionar_manual", "listar"]
