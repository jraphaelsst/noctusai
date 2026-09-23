"""The SW data -> file -> source catalog, slice S2: `linhagem_do_card` —
one contract's provenance ledger, machine-readable, for the card's
"Proveniência" tab. `fontes.py` (S1) catalogs WHICH `tipo_documento`
claims WHICH canonical field; this module walks the ACTUAL data
(`contrato_gerador.validacao_extracao.REGISTRO`, joined against
`cliente_documentos` / `imovel_documentos` / `matricula_extracoes`) and
answers, per contract-feeding value: what it holds, its state (empty /
machine-pending / confirmed / manual / conflicted), which document it came
from, and — from `fontes.FONTES` — which document type(s) COULD supply it
if it is not filled yet.

Scope (mirrors `fontes.FORA_DO_ESCOPO_S1`'s own honesty pattern): every
`REGISTRO` entry EXCEPT `CAMPO_CERTIDAO` (party certidões) and
`CAMPO_ATO_DETALHE` (última transferência) — those two are not resolved
through `cliente_documentos` / `imovel_documentos` / `matricula_extracoes`
at all (the row itself is a different table, `certidao_resultados` /
`matricula_ato_detalhes`), so the "table ⇒ entrada" join this module
performs does not apply to them; a later slice can add them.

- `linhagem_do_card` — `GET /api/clientes/{cliente_id}/contratos/
  {contrato_id}/proveniencia`'s answer (this module's `router.py`... no —
  see `contrato_gerador/router.py`, the sibling of `validacao-extracao`).
- `linhagem_do_registro` — `GET /api/proveniencia/registro`'s answer (this
  module's own `router.py`): a static reshaping of `fontes.FONTES` +
  `fontes.MANUAL_APENAS`, no DB reads, for the FE to build upload-channel
  hints without re-deriving the catalog client-side.
- `bloco_secao_0a` / `renderizar_secao_0a` — the generator for
  `CONTRACT-FIELD-PROVENANCE-MAP.md` § 0a's per-`tipo_documento` table +
  manual-only paragraph, so that section can never drift from `fontes.py`
  again (`test_proveniencia_kb_sync.py` pins the marker block to this
  function's OUTPUT byte-for-byte).
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.modules.card_hub.contrato_gerador import validacao_extracao as vx
from app.modules.card_hub.contrato_gerador.carregador import carregar
from app.modules.card_hub.proveniencia import fontes as fontes_mod
from app.services import table_reads

# ─── REGISTRO <-> fontes.py vocabulary translation ─────────────────────────

#: `REGISTRO` uses `clientes`' own column names (`nome_oficial`);
#: `fontes.FONTES`/`capacidades.py` use the seed's (`nome`) — see
#: `fontes.Fonte`'s own docstring for why they differ; the translation
#: itself (`fontes.RENOMEADOS_CAMPO`) is shared with `derivacao.falta()`'s
#: own suggestion lookup. Single source of truth for the (entidade, campo)
#: shape: `test_proveniencia_fontes.py` imports `CANONICOS_REGISTRO` from
#: here (it used to keep its own private copy of this same table).
def _canonicos_do_registro() -> dict[tuple[str, str], frozenset[str]]:
    out: dict[tuple[str, str], frozenset[str]] = {}
    for campo in vx.CAMPOS_CLIENTE:
        canonico = fontes_mod.RENOMEADOS_CAMPO.get(campo.campo, campo.campo)
        out[(campo.entidade, campo.campo)] = frozenset({canonico})
    # `numero_matricula` is spelled the same on both sides.
    for campo in vx.CAMPOS_IMOVEL:
        if campo.campo == "numero_matricula":
            out[(campo.entidade, campo.campo)] = frozenset({"numero_matricula"})
    return out


#: `(entidade, campo) -> canonical field name(s)` for every `REGISTRO`
#: field `fontes.FONTES` can claim via its `campos` set (CAMPOS_CLIENTE +
#: `imovel.numero_matricula`). Every other `REGISTRO` field is either
#: `CAMPO_IMOVEL_DOCUMENTO` (matched below via `estrutura_extraivel`,
#: not `campos`) or in `fontes.FORA_DO_ESCOPO_S1`.
CANONICOS_REGISTRO: dict[tuple[str, str], frozenset[str]] = _canonicos_do_registro()

#: `REGISTRO` fields this slice walks — every `CampoValidavel` EXCEPT the
#: two whose "document" is not one of the three joined tables. See the
#: module docstring's "Scope" paragraph.
_EXCLUIDOS_DA_LINHAGEM = (vx.CAMPO_CERTIDAO, vx.CAMPO_ATO_DETALHE)


# ─── linhagem_do_card ───────────────────────────────────────────────────────


def _todos_ativos(coleta: vx.Coleta) -> list[tuple[vx.Alvo, vx.CampoValidavel]]:
    """Every `(alvo, campo)` pair the migration has actually landed for —
    `listar_pendentes`'s `_pendentes_brutos` filters further, to only the
    ones awaiting a human; this keeps the VAZIO and CONFIRMADO/MANUAL ones
    too, so `linhagem_do_card` can report a full lineage, not just what
    blocks generation."""
    return [
        (alvo, campo)
        for alvo in coleta.alvos
        for campo in alvo.campos
        if campo not in _EXCLUIDOS_DA_LINHAGEM and campo.ativo(alvo.row)
    ]


def _decisoes_recentes(client: Any, org_id: UUID, contrato_id: UUID) -> dict[str, dict]:
    """Most recent `extracao_validacoes` ledger row per `chave`, for this
    contract. `decidir()` inserts one row per decision, so a `chave` that
    was extracted, rejected, and re-extracted can repeat — the latest
    `decidido_em` wins. Used only to enrich a now-empty (rejected) field's
    `origem` with what it USED to be — a lineage view should not go blank
    where the row itself went blank."""
    rows = (
        table_reads.table(client, vx.LEDGER)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("contrato_id", str(contrato_id))
        .execute()
    ).data or []
    latest: dict[str, dict] = {}
    for r in rows:
        k = vx.chave(r["entidade"], r["entidade_id"], r["campo"])
        atual = latest.get(k)
        if atual is None or (r.get("decidido_em") or "") > (atual.get("decidido_em") or ""):
            latest[k] = r
    return latest


def _estado(campo: vx.CampoValidavel, row: dict) -> str:
    if not any(vx.preenchido(row.get(c)) for c in campo.valores):
        return "vazio"
    if campo.pendente(row):
        return "maquina_pendente"
    if row.get(campo.origem) == "manual":
        return "manual"
    return "confirmado"


def _documento(
    campo: vx.CampoValidavel, alvo: vx.Alvo, fontes: dict[str, dict], decisao: Optional[dict],
) -> Optional[dict]:
    if campo.documento_id is None:
        # `CAMPO_IMOVEL_DOCUMENTO` — the alvo row IS an `imovel_documentos`
        # row (`_coletar` builds it that way); no second table lookup.
        if not alvo.fonte_id_propria:
            return None
        return {
            "id": alvo.fonte_id_propria,
            "tipo": alvo.row.get("tipo_documento"),
            "nome": alvo.fonte_nome_propria,
            "entrada": fontes_mod.TABELA_ENTRADA["imovel_documentos"].value,
        }
    doc_id = alvo.row.get(campo.documento_id) or (decisao or {}).get("fonte_documento_id")
    if not doc_id:
        return None
    fonte = fontes.get(str(doc_id))
    if fonte is None:
        return None
    tabela = fonte.get("_tabela")
    tipo = "matricula" if tabela == "matricula_extracoes" else fonte.get("tipo_documento")
    entrada = fontes_mod.TABELA_ENTRADA.get(tabela or "")
    return {
        "id": str(doc_id),
        "tipo": tipo,
        "nome": fonte.get("_nome"),
        "entrada": entrada.value if entrada else None,
    }


def _destino(
    campo: vx.CampoValidavel, alvo: vx.Alvo, cliente_id: UUID, imovel_codigo: Optional[str],
) -> Optional[str]:
    if campo.entidade == vx.ENTIDADE_CLIENTE:
        return f"/clientes/{cliente_id}"
    if campo.entidade == vx.ENTIDADE_IMOVEL:
        return f"/imoveis/{alvo.entidade_id}"
    if campo.entidade == vx.ENTIDADE_IMOVEL_DOCUMENTO:
        return f"/imoveis/{imovel_codigo}" if imovel_codigo else None
    return None


def _fontes_possiveis(entidade: str, campo: str, *, destino: Optional[str]) -> list[dict]:
    """Which `tipo_documento`(s) — per `fontes.FONTES` — could supply this
    `REGISTRO` field. `MANUAL_APENAS` ⇒ a single no-document entry pointing
    at the same `destino` (there is nowhere else to fill it in but the
    card itself); `FORA_DO_ESCOPO_S1` ⇒ `[]` (honest: this slice does not
    yet know)."""
    par = (entidade, campo)
    if par in fontes_mod.FORA_DO_ESCOPO_S1:
        return []
    if campo in fontes_mod.MANUAL_APENAS:
        return [{"tipo_documento": None, "rotulo": "Preenchimento manual", "entradas": [], "destino": destino}]
    if entidade == vx.ENTIDADE_IMOVEL_DOCUMENTO and campo == "certidao":
        # Migration 118's structured read — matched by `estrutura_extraivel`,
        # not by `campos` (those four `Fonte`s' `campos` is empty; see
        # `fontes.Fonte`'s own docstring).
        candidatos = [
            f for f in fontes_mod.FONTES.values() if f.dominio == "imovel" and f.estrutura_extraivel
        ]
    else:
        canonico = CANONICOS_REGISTRO.get(par)
        if not canonico:
            return []
        candidatos = [f for f in fontes_mod.FONTES.values() if canonico & f.campos]
    return [
        {
            "tipo_documento": f.tipo_documento,
            "rotulo": fontes_mod.ROTULOS_TIPO_DOCUMENTO.get(f.tipo_documento, f.tipo_documento),
            "entradas": sorted(e.value for e in f.entradas),
            "destino": destino,
        }
        for f in candidatos
    ]


def _linha(
    alvo: vx.Alvo,
    campo: vx.CampoValidavel,
    fontes: dict[str, dict],
    conflitos: dict[str, dict],
    decisoes: dict[str, dict],
    nomes: dict[str, str],
    cliente_id: UUID,
    imovel_codigo: Optional[str],
) -> dict:
    ch = vx.chave(campo.entidade, alvo.entidade_id, campo.campo)
    decisao = decisoes.get(ch)
    estado = "conflito" if ch in conflitos else _estado(campo, alvo.row)
    origem = alvo.row.get(campo.origem)
    if origem is None and decisao is not None:
        origem = decisao.get("origem")
    destino = _destino(campo, alvo, cliente_id, imovel_codigo)
    return {
        "entidade": campo.entidade,
        "campo": campo.campo,
        "rotulo": campo.rotulo,
        "valor": vx.valor_exibicao(campo, alvo.row, nomes),
        "estado": estado,
        "origem": origem,
        "documento": _documento(campo, alvo, fontes, decisao),
        "em": alvo.row.get(campo.em) if campo.em else None,
        "fontes_possiveis": _fontes_possiveis(campo.entidade, campo.campo, destino=destino),
    }


def linhagem_do_card(client: Any, org_id: UUID, cliente_id: UUID, contrato_id: UUID) -> dict:
    """`GET /api/clientes/{cliente_id}/contratos/{contrato_id}/proveniencia`'s
    answer: every contract-feeding value this contract loaded for (per
    `REGISTRO`, minus `CAMPO_CERTIDAO`/`CAMPO_ATO_DETALHE` — see the module
    docstring), its state, its source document, and which document
    type(s) could still supply it. `{"items": [...]}`."""
    dados, _ = carregar(client, org_id, cliente_id, contrato_id, usuario_id=None)
    coleta = vx.coletar(client, org_id, dados, None)
    pares = _todos_ativos(coleta)
    fontes = vx.documentos_de_origem(client, org_id, pares)
    conflitos = {
        vx.chave(c["entidade"], c["entidade_id"], c["campo"]): c
        for c in vx.listar_conflitos(client, org_id, dados)
    }
    decisoes = _decisoes_recentes(client, org_id, contrato_id)
    imovel_codigo = dados.imovel.codigo if dados.imovel is not None else None

    items = [
        _linha(alvo, campo, fontes, conflitos, decisoes, coleta.nomes, cliente_id, imovel_codigo)
        for alvo, campo in pares
    ]
    return {"items": items}


# ─── linhagem_do_registro ───────────────────────────────────────────────────


def _registro_fontes() -> list[dict]:
    saida: list[dict] = []
    for (entidade, campo), canonico in sorted(CANONICOS_REGISTRO.items()):
        candidatos = [f for f in fontes_mod.FONTES.values() if canonico & f.campos]
        if not candidatos:
            continue
        saida.append({
            "entidade": entidade,
            "campo": campo,
            "fontes": [
                {"tipo_documento": f.tipo_documento, "entradas": sorted(e.value for e in f.entradas)}
                for f in candidatos
            ],
        })
    estrutura = [
        f for f in fontes_mod.FONTES.values() if f.dominio == "imovel" and f.estrutura_extraivel
    ]
    if estrutura:
        saida.append({
            "entidade": vx.ENTIDADE_IMOVEL_DOCUMENTO,
            "campo": "certidao",
            "fontes": [
                {"tipo_documento": f.tipo_documento, "entradas": sorted(e.value for e in f.entradas)}
                for f in estrutura
            ],
        })
    return saida


def linhagem_do_registro() -> dict:
    """`GET /api/proveniencia/registro`'s answer: a static reshaping of
    `fontes.FONTES` + `fontes.MANUAL_APENAS` for the FE — no DB reads, same
    answer every call. `manual_apenas` entries are not entity-scoped in
    `fontes.py` (they are CONTRACT data categories, not `REGISTRO` fields —
    see `fontes.MANUAL_APENAS`'s own docstring), so `entidade` is the fixed
    label `"contrato"` rather than a fabricated per-item guess."""
    return {
        "fontes": _registro_fontes(),
        "manual_apenas": [
            {"entidade": "contrato", "campo": c, "destino": None}
            for c in sorted(fontes_mod.MANUAL_APENAS)
        ],
    }


# ─── § 0a generator (CONTRACT-FIELD-PROVENANCE-MAP.md) ─────────────────────

MARCADOR_SECAO_0A_INICIO = "<!-- AUTOGEN:fontes-secao-0a:begin -->"
MARCADOR_SECAO_0A_FIM = "<!-- AUTOGEN:fontes-secao-0a:end -->"


def renderizar_secao_0a() -> str:
    """§ 0a's per-`tipo_documento` table + manual-only paragraph, generated
    from `fontes.FONTES_REGISTRO`/`fontes.MANUAL_APENAS` — replaces the
    hand-written prose table that used to live there (drifted from the
    code with nothing to notice, exactly `fontes.py`'s own module
    docstring's complaint about the three-places-that-could-drift
    problem). `test_proveniencia_kb_sync.py` fails when the on-disk doc's
    marker block does not match this function's OUTPUT byte-for-byte."""
    linhas = [
        "| Tipo de documento | Domínio | Campos reivindicados | Extrator | Origens gravadas | Entradas |",
        "|---|---|---|---|---|---|",
    ]
    for fonte in fontes_mod.FONTES_REGISTRO:
        campos = ", ".join(f"`{c}`" for c in sorted(fonte.campos)) or "—"
        origens = ", ".join(f"`{o}`" for o in sorted(fonte.origens))
        entradas = ", ".join(f"`{e.value}`" for e in sorted(fonte.entradas))
        rotulo = fontes_mod.ROTULOS_TIPO_DOCUMENTO.get(fonte.tipo_documento, fonte.tipo_documento)
        linhas.append(
            f"| {rotulo} (`{fonte.tipo_documento}`) | {fonte.dominio} | {campos} | "
            f"`{fonte.extrator}` | {origens} | {entradas} |"
        )
    manual = ", ".join(f"`{c}`" for c in sorted(fontes_mod.MANUAL_APENAS))
    tabela = "\n".join(linhas)
    return f"{tabela}\n\n**Manual-only — no document carries it (by design, not a gap):** {manual}."


def bloco_secao_0a() -> str:
    """The full marker-delimited block — exactly what
    `CONTRACT-FIELD-PROVENANCE-MAP.md` § 0a carries between the two
    `AUTOGEN` comments."""
    return (
        f"{MARCADOR_SECAO_0A_INICIO}\n"
        "<!-- DO NOT EDIT BY HAND — regenerate via `app.modules.card_hub."
        "proveniencia.linhagem.bloco_secao_0a()` (pinned by "
        "`tests/modules/card_hub/test_proveniencia_kb_sync.py`). -->\n\n"
        f"{renderizar_secao_0a()}\n"
        f"{MARCADOR_SECAO_0A_FIM}"
    )


__all__ = [
    "CANONICOS_REGISTRO",
    "MARCADOR_SECAO_0A_FIM",
    "MARCADOR_SECAO_0A_INICIO",
    "bloco_secao_0a",
    "linhagem_do_card",
    "linhagem_do_registro",
    "renderizar_secao_0a",
]
