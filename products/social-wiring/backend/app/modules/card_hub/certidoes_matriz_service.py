"""`GET /api/clientes/{cliente_id}/certidoes/matriz` — the "Certidões" card
tab's MATRIX: every certidão TYPE (rows, `registry.MATRIZ_LINHAS`) crossed
with every VENDEDOR party + every one of their empresas that requires
certidões (columns), aggregated server-side into one response — no N-call
client pivot (Levantamento de Certidões.xlsx, first tab).

WHO COUNTS ("columns")
-----------------------
Vendedor parties: `empresas_service.pessoas_do_card` filtered to
`lado == "vendedor"` — the EXACT same resolution `empresas_service.listar`
uses for its own owners list (vendedor `atendimento_partes` rows PLUS every
vendedor's registered spouse via `clientes.conjuge_cliente_id`, even one
never added as its own `atendimento_partes` row — migration 153's D1 link).
Reused rather than restated: two independent "who is a vendedor on this
card" answers is exactly the N=2 recurrence `empresas_service`'s own
docstring already warns about for the E1 classification.

Empresa columns: `empresas_service.listar`'s own `items`, filtered to
`exige_certidoes=True` (E1's classification — an empresa the deal does NOT
need certidões for, e.g. baixada outside the window or every owner
non-certificando, is excluded from the matriz entirely) AND at least one
`owners` entry with `lado == "vendedor"` (a comprador-side-only empresa, the
permuta case, is out of THIS matrix's scope — it mirrors the Excel source's
own "VEND n / EMP n" column set).

CELLS
-----
Every column resolves its certidão results through the SAME per-person/
per-empresa readers the rest of the certidões module already exposes —
`certidoes.service.certidoes_por_cliente`/`certidoes_por_empresa` — so a
consulta linked via `vincular_parte`/`vincular_cliente`/`vincular_empresa`
denormalizes onto this matrix for free, without a new linking mechanism.
`registry.MATRIZ_LINHAS`'s `fgts_regularidade` row (5.13) is grey N/A on
every PESSOA (PF) column, by construction — it is a CNPJ-only obligation
(`registry.aplicavel_a_tipo_documento`), so no resultado can ever exist
there.

A column may carry MULTIPLE consultas of the relevant `tipo_documento`
(a re-run, a corrected re-link); the most recently `created_at` resultado
per `tipo` wins — an older attempt's stale status must never shadow a newer
one on this summary read.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from app.modules.card_hub.empresas_service import (
    ATENDIMENTOS_TABLE,
    CLIENTES_TABLE,
    listar as listar_empresas,
    pessoas_do_card,
)
from app.modules.card_hub.services import (
    AmbiguousAtendimento,
    ensure_cliente,
    resolve_atendimento_id,
)
from app.modules.certidoes import service as certidoes_svc
from app.modules.certidoes.registry import MATRIZ_LINHAS
from app.services import table_reads

#: The three total buckets a non-N/A cell falls into — mirrors the Excel
#: source's "Totais" footer rows (Não constam / Constam / Pendente), one
#: count PER COLUMN across all 15 rows (never per row across columns).
_TOTAL_CHAVES = ("nao_constam", "constam", "pendente")

#: `resultado` values the matriz reads as GREEN "Não constam" — a negativa,
#: or a positiva whose own effect is a negativa (migration 116's caveat
#: values included: `negativa_com_homonimos` is still a clean read for a
#: due-diligence rollup, the homônimo caveat itself belongs to the detail
#: view, not this summary color).
_NAO_CONSTAM = frozenset({
    "negativa", "positiva_com_efeito_de_negativa", "negativa_com_homonimos",
})
#: `resultado` values the matriz reads as RED "Constam" — a real apontamento,
#: or a certidão the source refused to emit at all (`nao_emitida` is itself
#: the irregularity the checklist is chasing, never a "no news" gap).
_CONSTAM = frozenset({"positiva", "nao_emitida"})


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def _empty(atendimento_id: Optional[str] = None) -> dict:
    return {
        "atendimento_id": atendimento_id,
        "data_levantamento": date.today().isoformat(),
        "linhas": [dict(linha) for linha in MATRIZ_LINHAS],
        "colunas": [],
        "celulas": {},
        "totais": {},
    }


def _status_da_celula(resultado_row: Optional[dict]) -> tuple[str, str]:
    """`(status, texto)` for one cell — the three colors plus the accessible
    label kept alongside them (never color alone)."""
    if resultado_row is None or resultado_row.get("status") != "sucesso":
        return "pendente", "Pendente"
    resultado = resultado_row.get("resultado")
    if resultado in _NAO_CONSTAM:
        return "nao_constam", "Não constam"
    if resultado in _CONSTAM:
        return "constam", "Constam"
    return "pendente", "Pendente"


def _celula(status: str, texto: str, resultado_row: Optional[dict]) -> dict:
    resultado_row = resultado_row or {}
    return {
        "status": status,
        "texto": texto,
        "resultado_id": resultado_row.get("id"),
        "consulta_id": resultado_row.get("consulta_id"),
        "numero": resultado_row.get("numero"),
        "emitida_em": resultado_row.get("emitida_em"),
        "validade_ate": resultado_row.get("validade_ate"),
        "analise_ia": resultado_row.get("analise_ia"),
        "erro_mensagem": resultado_row.get("erro_mensagem"),
    }


def _resultado_mais_recente_por_tipo(resultados: list[dict]) -> dict[str, dict]:
    por_tipo: dict[str, dict] = {}
    for resultado in resultados:
        tipo = resultado.get("tipo")
        if not tipo:
            continue
        atual = por_tipo.get(tipo)
        if atual is None or (resultado.get("created_at") or "") > (atual.get("created_at") or ""):
            por_tipo[tipo] = resultado
    return por_tipo


def montar_matriz(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """`GET`'s entire response — see the module docstring."""
    ensure_cliente(client, org_id, cliente_id)
    try:
        atendimento_id = resolve_atendimento_id(client, org_id, cliente_id)
    except AmbiguousAtendimento:
        return _empty()

    rows = (
        _t(client, ATENDIMENTOS_TABLE)
        .select("id, cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", atendimento_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return _empty()
    atendimento = rows[0]

    pessoas = [p for p in pessoas_do_card(client, org_id, atendimento) if p["lado"] == "vendedor"]
    nomes = {
        str(r["id"]): (r.get("nome_oficial") or r.get("nome") or "")
        for r in (
            _t(client, CLIENTES_TABLE)
            .select("id, nome, nome_oficial")
            .eq("org_id", str(org_id))
            .in_("id", [p["cliente_id"] for p in pessoas])
            .execute()
        ).data or []
    } if pessoas else {}

    empresas_resp = listar_empresas(client, org_id, cliente_id)
    empresas_colunas = [
        item["empresa"]
        for item in empresas_resp.get("items", [])
        if item.get("exige_certidoes")
        and any(o.get("lado") == "vendedor" for o in item.get("owners", []))
    ]

    colunas: list[dict] = []
    for idx, pessoa in enumerate(pessoas, start=1):
        colunas.append({
            "kind": "pessoa",
            "id": pessoa["cliente_id"],
            "rotulo": f"VEND {idx}",
            "nome": nomes.get(pessoa["cliente_id"], ""),
            "papel": pessoa.get("papel") or "",
        })
    for idx, empresa in enumerate(empresas_colunas, start=1):
        colunas.append({
            "kind": "empresa",
            "id": empresa["id"],
            "rotulo": f"EMP {idx}",
            "nome": empresa.get("nome_fantasia") or empresa.get("razao_social") or "",
            "cnpj": empresa.get("cnpj"),
        })

    resultados_por_coluna: dict[str, dict[str, dict]] = {}
    for coluna in colunas:
        if coluna["kind"] == "pessoa":
            resultados = certidoes_svc.certidoes_por_cliente(client, org_id, coluna["id"])
        else:
            resultados = certidoes_svc.certidoes_por_empresa(client, org_id, coluna["id"])
        resultados_por_coluna[coluna["id"]] = _resultado_mais_recente_por_tipo(resultados)

    celulas: dict[str, dict[str, dict]] = {}
    totais = {coluna["id"]: {chave: 0 for chave in _TOTAL_CHAVES} for coluna in colunas}
    for linha in MATRIZ_LINHAS:
        tipo = linha["tipo"]
        celulas[tipo] = {}
        for coluna in colunas:
            if tipo == "fgts_regularidade" and coluna["kind"] == "pessoa":
                celulas[tipo][coluna["id"]] = _celula("na", "N/A", None)
                continue
            resultado_row = resultados_por_coluna[coluna["id"]].get(tipo)
            status, texto = _status_da_celula(resultado_row)
            totais[coluna["id"]][status] += 1
            celulas[tipo][coluna["id"]] = _celula(status, texto, resultado_row)

    return {
        "atendimento_id": atendimento_id,
        "data_levantamento": date.today().isoformat(),
        "linhas": [dict(linha) for linha in MATRIZ_LINHAS],
        "colunas": colunas,
        "celulas": celulas,
        "totais": totais,
    }


__all__ = ["montar_matriz"]
