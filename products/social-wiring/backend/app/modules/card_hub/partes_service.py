"""ALL the parties of an atendimento — both lados, PF and PJ, titular
included — and the registration lookup by documento (CONTRACT §2.1/§2.5,
project `atendimento-partes-imoveis`).

WHY THIS IS NOT `compradores_service.listar`
--------------------------------------------
`compradores_service.listar` is frozen (CONTRACT §2.2): PF-only, titular
excluded, one lado per call — every existing consumer (carregador, the card's
Compradores panel) assumes a non-null `cliente_id`. A PJ party
(`atendimento_partes.empresa_id`, migration 179) would break them, so PJ and
the titular are visible ONLY here. This module READS; every write stays in
`compradores_service` (one creation path per party).

`listar_partes` is also the service BE-certidoes imports to build the
certidões column set, so its `(atendimento_id, items)` return shape is part of
the contract.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.integrations.documents import cnpj as cnpj_docs
from noctusai_lib.integrations.documents import cpf as cpf_docs
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.card_hub import compradores_service as comp_svc
from app.modules.card_hub.contrato_gerador import politica
from app.modules.card_hub.services import (
    AmbiguousAtendimento,
    _atendimentos_ids_via_partes_e_conjuge,
    _atendimentos_do_cliente,
    _t,
    ensure_cliente,
    resolve_atendimento_id_incluindo_partes,
)
from app.services import table_reads

PARTES_TABLE = comp_svc.TABLE
EMPRESAS_TABLE = "empresas"
ATENDIMENTOS_TABLE = comp_svc.ATENDIMENTOS_TABLE
CLIENTES_TABLE = comp_svc.CLIENTES_TABLE

_EMPRESA_RESUMO = ("id", "razao_social", "nome_fantasia", "cnpj", "situacao_cadastral")
_CLIENTE_LOOKUP = ("id", "nome", "nome_oficial", "cpf", "celular", "email", "created_at")

_PREFIXO_ROTULO = {"comprador": "COMP", "vendedor": "VEND"}


def _digitos(valor: Optional[str]) -> Optional[str]:
    digitos = re.sub(r"\D", "", valor or "")
    return digitos or None


# ─── resolution ─────────────────────────────────────────────────────────────


def _resolver_atendimento(
    client: Any, org_id: UUID, cliente_id: UUID, explicit: Optional[UUID]
) -> Optional[str]:
    """The atendimento this card read is about, party-aware (CONTRACT §0).

    An explicit id must be one this cliente is ON (titular, party, or a
    vendedor's registered spouse) — unknown/foreign ⇒ `NotFoundError`, never a
    silent empty read (an authorisation-shaped refusal must not look empty).
    No explicit id: the single open one, else `None` (a read never 409s).
    """
    if explicit is not None:
        permitidos = {
            str(r["id"]) for r in _atendimentos_do_cliente(client, org_id, cliente_id)
        } | _atendimentos_ids_via_partes_e_conjuge(client, org_id, cliente_id)
        if str(explicit) not in permitidos:
            raise NotFoundError("atendimentos", str(explicit))
        return str(explicit)
    try:
        return resolve_atendimento_id_incluindo_partes(client, org_id, cliente_id)
    except AmbiguousAtendimento:
        return None


# ─── ParteItem assembly ─────────────────────────────────────────────────────


def _nome_cliente(c: Optional[dict]) -> str:
    if not c:
        return ""
    return c.get("nome_oficial") or c.get("nome_completo") or c.get("nome") or ""


def _nome_empresa(e: Optional[dict]) -> str:
    if not e:
        return ""
    return e.get("razao_social") or e.get("nome_fantasia") or ""


def _item(
    *,
    parte: Optional[dict],
    titular: bool,
    lado: str,
    papel: str,
    ordem: int,
    cliente: Optional[dict],
    empresa: Optional[dict],
    cliente_id: Optional[str],
    empresa_id: Optional[str],
) -> dict:
    e_pj = empresa_id is not None
    return {
        "parte_id": str(parte["id"]) if parte else None,
        "titular": titular,
        "rotulo": "",  # numbered per lado after ordering (`_numerar`)
        "lado": lado,
        "papel": papel,
        "ordem": ordem,
        "tipo_pessoa": "PJ" if e_pj else "PF",
        "cliente_id": cliente_id,
        "empresa_id": empresa_id,
        "nome": _nome_empresa(empresa) if e_pj else _nome_cliente(cliente),
        "documento": (
            _digitos((empresa or {}).get("cnpj")) if e_pj
            else _digitos((cliente or {}).get("cpf"))
        ),
        "observacao": (parte or {}).get("observacao"),
        "cliente": (
            {k: cliente.get(k) for k in comp_svc._CLIENTE_RESUMO} if cliente else None
        ),
        "empresa": (
            {k: empresa.get(k) for k in _EMPRESA_RESUMO} if empresa else None
        ),
    }


def _numerar(itens: list[dict]) -> list[dict]:
    """COMP n / VEND n, per lado, in list order (the list is already sorted)."""
    contadores = {"comprador": 0, "vendedor": 0}
    for it in itens:
        contadores[it["lado"]] += 1
        it["rotulo"] = f"{_PREFIXO_ROTULO[it['lado']]} {contadores[it['lado']]}"
    return itens


def _montar_itens(
    client: Any, org_id: UUID, atendimento: dict, partes: list[dict]
) -> list[dict]:
    titular_id = atendimento.get("cliente_id")
    cliente_ids = [str(p["cliente_id"]) for p in partes if p.get("cliente_id")]
    if titular_id:
        cliente_ids.append(str(titular_id))
    empresa_ids = [str(p["empresa_id"]) for p in partes if p.get("empresa_id")]
    clientes = {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(
            client, CLIENTES_TABLE, org_id, "id", cliente_ids,
            select=",".join(comp_svc._CLIENTE_RESUMO),
        )
    }
    empresas = {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(
            client, EMPRESAS_TABLE, org_id, "id", empresa_ids,
            select=",".join(_EMPRESA_RESUMO),
        )
    }

    itens: list[dict] = []
    if titular_id:
        # The titular IS the first comprador and has no `atendimento_partes`
        # row (migration 073) — hence `parte_id: null`.
        itens.append(
            _item(
                parte=None, titular=True, lado="comprador", papel="comprador",
                ordem=0, cliente=clientes.get(str(titular_id)), empresa=None,
                cliente_id=str(titular_id), empresa_id=None,
            )
        )
    ordenadas = sorted(
        partes,
        key=lambda r: (
            0 if (r.get("lado") or "comprador") == "comprador" else 1,
            r.get("ordem") or 0,
            str(r.get("created_at") or ""),
        ),
    )
    for p in ordenadas:
        cid = str(p["cliente_id"]) if p.get("cliente_id") else None
        eid = str(p["empresa_id"]) if p.get("empresa_id") else None
        itens.append(
            _item(
                parte=p, titular=False, lado=p.get("lado") or "comprador",
                papel=p.get("papel") or "", ordem=int(p.get("ordem") or 0),
                cliente=clientes.get(cid) if cid else None,
                empresa=empresas.get(eid) if eid else None,
                cliente_id=cid, empresa_id=eid,
            )
        )
    # Comprador lado first, then vendedor (the titular is already first).
    itens.sort(key=lambda it: 0 if it["lado"] == "comprador" else 1)
    return _numerar(itens)


def _atendimento_row(client: Any, org_id: UUID, atendimento_id: str) -> Optional[dict]:
    rows = (
        _t(client, ATENDIMENTOS_TABLE)
        .select("id, cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", atendimento_id)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _partes_do_atendimento(client: Any, org_id: UUID, atendimento_id: str) -> list[dict]:
    return table_reads.paged_rows(
        client, PARTES_TABLE, org_id, eq_filters={"atendimento_id": atendimento_id}
    )


def listar_partes(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    atendimento_id: Optional[UUID] = None,
) -> tuple[Optional[str], list[dict]]:
    """`(atendimento_id, ParteItem[])` — ambiguous / no open deal ⇒ `(None, [])`.

    CONTRACT §2.1. `ensure_cliente` first (404 for an unknown cliente).
    """
    ensure_cliente(client, org_id, cliente_id)
    alvo = _resolver_atendimento(client, org_id, cliente_id, atendimento_id)
    if alvo is None:
        return None, []
    atendimento = _atendimento_row(client, org_id, alvo)
    if atendimento is None:
        return None, []
    partes = _partes_do_atendimento(client, org_id, alvo)
    return alvo, _montar_itens(client, org_id, atendimento, partes)


def item_da_parte(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: str, parte_id: str
) -> dict:
    """The `ParteItem` of ONE just-written party row (the 201 body of
    `POST .../compradores`)."""
    _alvo, itens = listar_partes(
        client, org_id, cliente_id, atendimento_id=UUID(str(atendimento_id))
    )
    for it in itens:
        if it["parte_id"] == str(parte_id):
            return it
    raise NotFoundError(PARTES_TABLE, str(parte_id))


def partes_pj(
    client: Any, org_id: UUID, atendimento_id: str
) -> list[dict]:
    """The PJ parties of an atendimento (`parte_id, empresa_id, lado, papel,
    nome, cnpj`) — what the contract loader needs to surface a `faltando`
    for a company party instead of silently dropping it (the contract
    generator qualifies natural persons only)."""
    partes = [
        p for p in _partes_do_atendimento(client, org_id, atendimento_id)
        if p.get("empresa_id")
    ]
    if not partes:
        return []
    empresas = {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(
            client, EMPRESAS_TABLE, org_id, "id",
            [str(p["empresa_id"]) for p in partes],
            select=",".join(_EMPRESA_RESUMO),
        )
    }
    out = []
    for p in sorted(partes, key=lambda r: (r.get("ordem") or 0, str(r.get("created_at") or ""))):
        emp = empresas.get(str(p["empresa_id"]), {})
        out.append({
            "parte_id": str(p["id"]),
            "empresa_id": str(p["empresa_id"]),
            "lado": p.get("lado") or "comprador",
            "papel": p.get("papel") or "",
            "nome": _nome_empresa(emp),
            "cnpj": _digitos(emp.get("cnpj")),
        })
    return out


# ─── lookup by documento (§2.5) ─────────────────────────────────────────────


def _classificar_documento(documento: str) -> tuple[str, str]:
    """`(normalizado, 'cpf'|'cnpj')` or a 400 with the contract's copy."""
    norm = cnpj_docs.normalize(documento)
    if len(norm) == 11 and norm.isdigit():
        if not cpf_docs.is_valid(norm):
            raise ValidationError_("CPF inválido.")
        return norm, "cpf"
    if len(norm) == 14:
        if not cnpj_docs.is_valid(norm):
            raise ValidationError_("CNPJ inválido.")
        return norm, "cnpj"
    raise ValidationError_("Informe um CPF ou CNPJ válido.")


def _clientes_por_cpf(client: Any, org_id: UUID, cpf: str) -> list[dict]:
    """Every cliente of this org holding this CPF, oldest first.

    `clientes.cpf` keeps whatever punctuation it arrived with (097) and
    PostgREST cannot filter on `normalizar_documento(cpf)` (the expression
    behind `idx_sw_clientes_cpf_norm`), so the two shapes the app itself
    writes — bare digits and `ddd.ddd.ddd-dd` — are matched. A third spelling
    (spaces, stray text) would be missed.

    NOC-REMEDIATE[cpf-lookup-normalized-rpc]: a `social_wiring` RPC wrapping
    `normalizar_documento()` would make this exact on the existing index —
    batch with the CPF-dedupe consumers (`qualificacao_service._clientes_por_
    cpf` full-scans the org for the same reason). — 2026-10-01
    """
    formatado = cpf_docs.format_cpf(cpf)
    variantes = [cpf] + ([formatado] if formatado else [])
    rows = table_reads.in_batched_rows(
        client, CLIENTES_TABLE, org_id, "cpf", variantes,
        select=",".join(_CLIENTE_LOOKUP),
    )
    return sorted(rows, key=lambda r: str(r.get("created_at") or ""))


def _empresa_por_cnpj(client: Any, org_id: UUID, cnpj: str) -> Optional[dict]:
    rows = (
        _t(client, EMPRESAS_TABLE)
        .select(",".join(_EMPRESA_RESUMO))
        .eq("org_id", str(org_id))
        .eq("cnpj", cnpj)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def _atendimentos_da_pessoa(
    client: Any, org_id: UUID, *, cliente_ids: list[str], empresa_id: Optional[str]
) -> list[dict]:
    """Every atendimento the person/company is on — titular OR party — newest
    first. A titular row wins over a party row of the same atendimento."""
    entradas: dict[str, dict] = {}
    for r in table_reads.in_batched_rows(
        client, ATENDIMENTOS_TABLE, org_id, "cliente_id", cliente_ids, select="id"
    ):
        entradas[str(r["id"])] = {
            "lado": "comprador", "papel": "comprador", "titular": True, "parte_id": None,
        }
    partes: list[dict] = []
    if cliente_ids:
        partes += table_reads.in_batched_rows(
            client, PARTES_TABLE, org_id, "cliente_id", cliente_ids,
            select="id,atendimento_id,lado,papel",
        )
    if empresa_id:
        partes += table_reads.paged_rows(
            client, PARTES_TABLE, org_id, eq_filters={"empresa_id": empresa_id},
            select="id,atendimento_id,lado,papel",
        )
    for p in partes:
        entradas.setdefault(str(p["atendimento_id"]), {
            "lado": p.get("lado") or "comprador",
            "papel": p.get("papel") or "comprador",
            "titular": False,
            "parte_id": str(p["id"]),
        })
    if not entradas:
        return []

    atendimentos = {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(
            client, ATENDIMENTOS_TABLE, org_id, "id", list(entradas),
            select="id,titulo,status,arquivado,etapa_id,created_at",
        )
    }
    etapa_ids = sorted({a["etapa_id"] for a in atendimentos.values() if a.get("etapa_id")})
    etapas = {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(
            client, "pipeline_stages", org_id, "id", etapa_ids, select="id,label",
        )
    } if etapa_ids else {}

    out = []
    for aid, meta in entradas.items():
        a = atendimentos.get(aid)
        if a is None:
            continue
        etapa = etapas.get(str(a.get("etapa_id") or ""))
        out.append({
            "id": aid,
            "titulo": a.get("titulo"),
            "etapa": (
                {"id": str(etapa["id"]), "nome": etapa.get("label")} if etapa else None
            ),
            "status": a.get("status"),
            "arquivado": bool(a.get("arquivado")),
            **meta,
            "_created_at": str(a.get("created_at") or ""),
        })
    out.sort(key=lambda x: x["_created_at"], reverse=True)
    for x in out:
        x.pop("_created_at")
    return out


def _data(valor: Any) -> Optional[date]:
    texto = str(valor or "")[:10]
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def certidoes_mais_recentes(
    resultados: list[dict], *, hoje: date, max_dias: int
) -> dict:
    """The `certidoes` block of §2.5 — latest DATED resultado per `tipo`
    (greatest `emitida_em`; tie ⇒ greatest `created_at`, the §1.1 rule) with
    its age and the `stale_para_contrato` flag. Stale = `idade_dias >=
    max_dias` — the SAME predicate as `derivacao._certidoes` ((assinatura −
    emitida_em).days >= certidao_max_dias)."""
    from app.modules.certidoes.registry import CUSTOM_ROW_TIPO

    vencedor: dict[str, tuple[date, str, dict]] = {}
    for r in resultados:
        tipo = r.get("tipo")
        emitida = _data(r.get("emitida_em"))
        if not tipo or tipo == CUSTOM_ROW_TIPO or emitida is None:
            continue
        chave = (emitida, str(r.get("created_at") or ""))
        atual = vencedor.get(tipo)
        if atual is None or chave > (atual[0], atual[1]):
            vencedor[tipo] = (emitida, str(r.get("created_at") or ""), r)
    itens = []
    for tipo in sorted(vencedor):
        emitida, _created, r = vencedor[tipo]
        idade = (hoje - emitida).days
        itens.append({
            "tipo": tipo,
            "rotulo": r.get("nome_display") or tipo,
            "resultado_id": str(r["id"]),
            "emitida_em": emitida.isoformat(),
            "validade_ate": (_data(r.get("validade_ate")).isoformat()
                             if _data(r.get("validade_ate")) else None),
            "idade_dias": idade,
            "stale_para_contrato": idade >= max_dias,
            "resultado": r.get("resultado"),
        })
    vencidos = [i["tipo"] for i in itens if i["stale_para_contrato"]]
    return {
        "max_dias": max_dias,
        "data_referencia": hoje.isoformat(),
        "itens": itens,
        "tipos_vencidos": vencidos,
        "alerta_vencidas": bool(vencidos),
        "mensagem": (
            f"Há certidões com mais de {max_dias} dias. Re-emita e re-analise "
            "antes de usar no contrato."
            if vencidos else None
        ),
    }


def lookup_documento(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    documento: str,
    atendimento_id: Optional[UUID] = None,
    hoje: Optional[date] = None,
) -> dict:
    """CONTRACT §2.5 — what do we already know about this CPF/CNPJ? Read-only,
    org-scoped; a miss is a 200 with `encontrado: null`, never a 404."""
    from app.modules.certidoes import service as certidoes_svc

    ensure_cliente(client, org_id, cliente_id)
    norm, tipo_documento = _classificar_documento(documento)
    alvo = _resolver_atendimento(client, org_id, cliente_id, atendimento_id)
    hoje = hoje or date.today()

    cliente_resumo: Optional[dict] = None
    empresa_resumo: Optional[dict] = None
    cliente_ids: list[str] = []
    empresa_id: Optional[str] = None
    resultados: list[dict] = []
    if tipo_documento == "cpf":
        achados = _clientes_por_cpf(client, org_id, norm)
        cliente_ids = [str(c["id"]) for c in achados]
        if achados:
            # Several cards can share one CPF (same person, two deals): show
            # the one already on the resolved atendimento if any, else the
            # oldest — the canonical record the others were created after.
            escolhido = achados[0]
            if alvo is not None:
                no_alvo = {
                    str(p["cliente_id"])
                    for p in _partes_do_atendimento(client, org_id, alvo)
                    if p.get("cliente_id")
                }
                atd = _atendimento_row(client, org_id, alvo) or {}
                if atd.get("cliente_id"):
                    no_alvo.add(str(atd["cliente_id"]))
                escolhido = next(
                    (c for c in achados if str(c["id"]) in no_alvo), escolhido
                )
            cliente_resumo = {
                k: escolhido.get(k)
                for k in ("id", "nome", "nome_oficial", "cpf", "celular", "email")
            }
            cliente_resumo["id"] = str(cliente_resumo["id"])
        for cid in cliente_ids:
            resultados += certidoes_svc.certidoes_por_cliente(client, org_id, cid)
    else:
        empresa = _empresa_por_cnpj(client, org_id, norm)
        if empresa:
            empresa_resumo = {k: empresa.get(k) for k in _EMPRESA_RESUMO}
            empresa_resumo["id"] = str(empresa_resumo["id"])
            empresa_id = empresa_resumo["id"]
            resultados = certidoes_svc.certidoes_por_empresa(client, org_id, empresa_id)

    atendimentos = (
        _atendimentos_da_pessoa(
            client, org_id, cliente_ids=cliente_ids, empresa_id=empresa_id
        )
        if (cliente_ids or empresa_id) else []
    )
    return {
        "documento": norm,
        "tipo_documento": tipo_documento,
        "encontrado": (
            "cliente" if cliente_resumo else "empresa" if empresa_resumo else None
        ),
        "cliente": cliente_resumo,
        "empresa": empresa_resumo,
        "ja_no_atendimento": bool(alvo) and any(a["id"] == alvo for a in atendimentos),
        "atendimentos": atendimentos,
        "certidoes": certidoes_mais_recentes(
            resultados, hoje=hoje, max_dias=politica.POLITICA_PADRAO.certidao_max_dias
        ),
    }


__all__ = [
    "certidoes_mais_recentes",
    "item_da_parte",
    "listar_partes",
    "lookup_documento",
    "partes_pj",
]
