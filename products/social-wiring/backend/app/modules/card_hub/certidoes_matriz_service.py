"""`GET /api/clientes/{cliente_id}/certidoes/matriz` — the "Certidões" card
tab's MATRIX: every certidão TYPE (rows — `registry.MATRIZ_LINHAS`'s fixed
13 PLUS this card's own active custom rows, migration 170) crossed with
every party the tech-lead's binding matrix rules name (columns), aggregated
server-side into one response — no N-call client pivot (Levantamento de
Certidões.xlsx, first tab).

WHO COUNTS ("columns") — tech-lead binding rules, 2026-09-24
--------------------------------------------------------------
Every vendedor party AND their permuta-comprador counterpart (+ cônjuges)
count the SAME way: `empresas_service.pessoas_do_card`'s own
`certificando` flag ALREADY encodes exactly this (True for every
vendedor-lado pessoa unconditionally; True for a comprador-lado pessoa —
the titular included — only when `tem_permuta_ativa`, per that function's
own "WHO COUNTS" docblock). Filtering on `certificando` here, rather than
hand-rolling a second permuta check, is the SAME reuse-not-restate
reasoning `empresas_service.listar` already applies to E1 — and is why a
permuta-comprador's own empresas show up "for free" below: `listar`'s
`exige_certidoes` verdict already demotes a comprador-only-owned empresa to
`sem_socio_certificando` when `tem_permuta` is false, and promotes it when
true (`empresas_service.py::test_permuta_comprador_is_certificando`). This
module makes ZERO derivação/permuta decisions of its own — read-only
consumer of `pessoas_do_card`/`listar`'s verdicts, never a restatement
(owner rule 2026-09-24 §7: a peer session is validating E1-E6 live).

`resolver_colunas` is the shared column-resolution step — `montar_matriz`
below AND `certidoes_matriz_linhas_service.criar` (the "+ Adicionar
certidão" fan-out) both call it, so "which parties/empresas does THIS card
show" is answered in exactly one place.

Empresa columns: `empresas_service.listar`'s own `items`, filtered to
`exige_certidoes=True` alone — that flag already folds in the permuta
verdict AND dedupes by empresa (one `cliente_empresa_participacoes` row
group per `empresas.id`/CNPJ, owners merged — `test_owners_merge_across_a_
shared_empresa`), so a couple-shared empresa surfaces as exactly one EMP
column, never twice.

CELLS — the FIXED PF-12 / PJ-11 sets (owner rule, 2026-09-24 §1-3)
--------------------------------------------------------------------
`registry.MATRIZ_LINHAS` rows 5.1-5.12 are the fixed checklist: all twelve
apply to a PESSOA (PF) column; PJ drops row 5.9 (SERASA — a personal credit
report, CENPROT already covers a company) to eleven, grey N/A on every
EMPRESA column. Row 5.13 (`fgts_regularidade`) is grey N/A on every PESSOA
column (a CNPJ-only obligation, `registry.aplicavel_a_tipo_documento`) and
recordable on an EMPRESA column. Rows 5.14, 5.15, ... are this CARD's own
active custom rows (`certidao_matriz_linhas_customizadas`, migration 170,
`nome`-labelled "Outras: <nome>") — applicable to BOTH PF and PJ columns,
never N/A. Every custom row, like FGTS, is DISPLAY/RECORD-ONLY: never
folded into the PF-12/PJ-11 fixed set nor into any readiness/required-
documents gate (owner rule §2). TJSP is ALWAYS the two split rows
(`tjsp_esaj`/`tjsp_eproc`, 5.7/5.8); the generic automated `tjsp` type from
`certidoes.registry.CERTIDOES_CONFIG` is deliberately absent from
`MATRIZ_LINHAS` and this module never reads it — a legacy `tipo='tjsp'`
resultado (if any exist from before this tab) surfaces in NEITHER split
row's cell/tooltip (owner rule §3: no invented mapping). `scoped-
improvement:` a fleet query for any live `tipo='tjsp'` resultado would
confirm whether that legacy-data case is purely hypothetical or needs its
own follow-up.

Every column resolves its certidão results through the SAME per-person/
per-empresa readers the rest of the certidões module already exposes —
`certidoes.service.certidoes_por_cliente`/`certidoes_por_empresa` — so a
consulta linked via `vincular_parte`/`vincular_cliente`/`vincular_empresa`
denormalizes onto this matrix for free, without a new linking mechanism. A
fixed-row cell is matched by `tipo`; a custom-row cell is matched by
`linha_customizada_id` (migration 170's FK — never an id encoded into
`tipo`, which stays the fixed sentinel `registry.CUSTOM_ROW_TIPO` for every
custom-row resultado). This module performs NO writes of its own
(`montar_matriz` is read-only, GET-only) — every write a caller can trigger
from this tab's dialog (`CertidoesPartePanel`, reused unmodified) goes
through the SAME audited paths (`process_manual_upload`,
`confirmar_resultado`, etc.) the rest of the certidões module already uses
(owner rule §6); the ONE new write path, adding/renaming/removing a custom
ROW DEFINITION, lives in `certidoes_matriz_linhas_service` instead.

A column may carry MULTIPLE consultas of the relevant `tipo_documento`
(a re-run, a corrected re-link); the most recently `created_at` resultado
per row wins — an older attempt's stale status must never shadow a newer
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
    resolve_atendimento_id_incluindo_partes,
)
from app.modules.certidoes import service as certidoes_svc
from app.modules.certidoes.registry import MATRIZ_LINHAS

from app.modules.certidoes.matriz_custom_rows import (
    LINHAS_CUSTOMIZADAS_TABLE,
    linhas_customizadas_ativas,
)
from app.services import table_reads

#: The three total buckets a non-N/A cell falls into — mirrors the Excel
#: source's "Totais" footer rows (Não constam / Constam / Pendente), one
#: count PER COLUMN across every row (never per row across columns).
_TOTAL_CHAVES = ("nao_constam", "constam", "pendente")

#: `resultado` values the matriz reads as GREEN "Não constam" — a negativa,
#: or a positiva whose own effect is a negativa (migration 116's caveat
#: values included: `negativa_com_homonimos` is still a clean read for a
#: due-diligence rollup, the homônimo caveat itself belongs to the detail
#: view, not this summary color). [Owner directive, 2026-09-25] Same read
#: `contrato_gerador.frases.RESULTADOS_COM_APONTAMENTO` now takes — the two
#: classifiers answer different questions (this one a checklist color, that
#: one "does the contract need an esclarecimentos paragraph") and are not
#: merged into one shared symbol, but they must never disagree on this
#: value again; a future change to either needs the same audit this one got.
_NAO_CONSTAM = frozenset({
    "negativa", "positiva_com_efeito_de_negativa", "negativa_com_homonimos",
})
#: `resultado` values the matriz reads as RED "Constam" — a real apontamento,
#: or a certidão the source refused to emit at all (`nao_emitida` is itself
#: the irregularity the checklist is chasing, never a "no news" gap).
_CONSTAM = frozenset({"positiva", "nao_emitida"})


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def resolver_colunas(client: Any, org_id: UUID, cliente_id: UUID) -> tuple[Optional[str], list[dict]]:
    """`(atendimento_id, colunas)` — the matriz's column set, per the tech-
    lead's binding rules (see module docstring). `atendimento_id` is `None`
    when there is no open/an ambiguous atendimento — `colunas` is always
    `[]` in that case. The ONE place this resolution happens; `montar_matriz`
    and `certidoes_matriz_linhas_service.criar`'s fan-out both call this
    rather than each re-deriving "who is on this card"."""
    ensure_cliente(client, org_id, cliente_id)
    try:
        atendimento_id = resolve_atendimento_id_incluindo_partes(client, org_id, cliente_id)
    except AmbiguousAtendimento:
        return None, []

    rows = (
        _t(client, ATENDIMENTOS_TABLE)
        .select("id, cliente_id")
        .eq("org_id", str(org_id))
        .eq("id", atendimento_id)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None, []
    atendimento = rows[0]

    pessoas = [p for p in pessoas_do_card(client, org_id, atendimento) if p["certificando"]]
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
    return atendimento_id, colunas


def _empty(atendimento_id: Optional[str] = None) -> dict:
    return {
        "atendimento_id": atendimento_id,
        "data_levantamento": date.today().isoformat(),
        "linhas": [_linha_fixa(linha) for linha in MATRIZ_LINHAS],
        "colunas": [],
        "celulas": {},
        "totais": {},
    }


def _linha_fixa(linha: dict) -> dict:
    return {**linha, "chave": linha["tipo"], "custom": False, "id": None}


def _linha_customizada(row: dict) -> dict:
    return {
        "tipo": None,
        "chave": str(row["id"]),
        "id": str(row["id"]),
        "linha": f"5.{row['ordem']}",
        "rotulo": f"Outras: {row['nome']}",
        "custom": True,
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


def _index_resultados(resultados: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    """`(por_tipo, por_linha_customizada_id)` — a fixed row is matched by
    `tipo`; a custom row's resultado always carries the SAME sentinel `tipo`
    (`registry.CUSTOM_ROW_TIPO`), so those are indexed separately by their
    real discriminator, `linha_customizada_id`. Most-recent-`created_at`
    wins within each index."""
    por_tipo: dict[str, dict] = {}
    por_linha: dict[str, dict] = {}
    for resultado in resultados:
        linha_customizada_id = resultado.get("linha_customizada_id")
        if linha_customizada_id:
            atual = por_linha.get(linha_customizada_id)
            if atual is None or (resultado.get("created_at") or "") > (atual.get("created_at") or ""):
                por_linha[linha_customizada_id] = resultado
            continue
        tipo = resultado.get("tipo")
        if not tipo:
            continue
        atual = por_tipo.get(tipo)
        if atual is None or (resultado.get("created_at") or "") > (atual.get("created_at") or ""):
            por_tipo[tipo] = resultado
    return por_tipo, por_linha


def montar_matriz(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """`GET`'s entire response — see the module docstring."""
    atendimento_id, colunas = resolver_colunas(client, org_id, cliente_id)
    if atendimento_id is None:
        return _empty()

    linhas_custom = linhas_customizadas_ativas(client, org_id, cliente_id)
    linhas = [_linha_fixa(linha) for linha in MATRIZ_LINHAS] + [
        _linha_customizada(row) for row in linhas_custom
    ]

    resultados_por_coluna: dict[str, tuple[dict, dict]] = {}
    for coluna in colunas:
        if coluna["kind"] == "pessoa":
            resultados = certidoes_svc.certidoes_por_cliente(client, org_id, coluna["id"])
        else:
            resultados = certidoes_svc.certidoes_por_empresa(client, org_id, coluna["id"])
        resultados_por_coluna[coluna["id"]] = _index_resultados(resultados)

    celulas: dict[str, dict[str, dict]] = {}
    totais = {coluna["id"]: {chave: 0 for chave in _TOTAL_CHAVES} for coluna in colunas}
    for linha in linhas:
        chave = linha["chave"]
        celulas[chave] = {}
        for coluna in colunas:
            # Owner rule 2026-09-24 §1: PJ = PF-12 minus SERASA (a personal
            # credit report; CENPROT already covers a company) — grey N/A on
            # every EMPRESA column. §2: FGTS (5.13) is a CNPJ-only
            # obligation — grey N/A on every PESSOA column. Custom rows are
            # NEVER N/A (applicable to both PF and PJ, owner rule §1 follow-up).
            if linha["tipo"] == "fgts_regularidade" and coluna["kind"] == "pessoa":
                celulas[chave][coluna["id"]] = _celula("na", "N/A", None)
                continue
            if linha["tipo"] == "serasa" and coluna["kind"] == "empresa":
                celulas[chave][coluna["id"]] = _celula("na", "N/A", None)
                continue
            por_tipo, por_linha = resultados_por_coluna[coluna["id"]]
            resultado_row = por_linha.get(chave) if linha["custom"] else por_tipo.get(chave)
            status, texto = _status_da_celula(resultado_row)
            totais[coluna["id"]][status] += 1
            celulas[chave][coluna["id"]] = _celula(status, texto, resultado_row)

    return {
        "atendimento_id": atendimento_id,
        "data_levantamento": date.today().isoformat(),
        "linhas": linhas,
        "colunas": colunas,
        "celulas": celulas,
        "totais": totais,
    }


__all__ = ["linhas_customizadas_ativas", "montar_matriz", "resolver_colunas"]
