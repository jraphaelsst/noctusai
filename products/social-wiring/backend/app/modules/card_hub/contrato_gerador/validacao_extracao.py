"""The human validation gate over machine-extracted contract data (owner
decision D2, roadmap `sw-extraction-contract-gate-2026-09`, migration 156).

WHAT IS "PENDING"
-----------------
A contract-feeding value is **machine-pending** iff, on its own provenance
columns, `origem` is set, is NOT a human's (`'manual'`), and nobody has
confirmed it (`confirmado_em IS NULL`) — and it actually holds a value (an
empty reading has nothing to vouch for). That is the roadmap's "Shared
field-state contract", applied through ONE table-driven `REGISTRO` rather than
a branch per source.

WHICH VALUES
------------
Exactly the rows `carregador.carregar` reads for THIS contract, identified
off the `DadosContrato` it returns — never a second, hand-kept list of who
signs:

| DadosContrato                | Rows checked                                          |
|------------------------------|-------------------------------------------------------|
| compradores + vendedores     | `clientes` (every parte, incl. cônjuges + antigos     |
| (titular, partes, cônjuges,  | proprietários) — the columns `_pessoa` reads          |
| antigos proprietários)       | `certidao_resultados` via the SAME `certidoes_por_*`  |
| imovel                       | `imovel_dados` (the columns `_imovel` reads)          |
|                              | `imovel_documentos` via `documentos_service.certidoes`|
|                              | `matricula_ato_detalhes` — the última transferência   |
|                              | act `titulo_service.antigos_proprietarios` resolves   |
| permuta_imoveis              | `imovel_dados` of each ativo's catalog imóvel (the    |
|                              | three columns `_permuta_imoveis` reads)               |

A value `carregador` does not read (e.g. `clientes.data_nascimento`) is not
contract-feeding and is deliberately absent.

🔴 A PROVENANCE COLUMN THAT DOES NOT EXIST YET IS NOT A CRASH. Rows are read
with `select("*")`, and a registry entry only applies when its `origem` and
`confirmado_em` columns are PRESENT on the row. Several entries name columns
parallel slices add (migration 153 identity, 154 imóvel); until they land, the
entry is inert — exactly the "not pending" answer those columns would give
while still empty. Writes likewise only touch columns present on the row.

OPEN CONFLICTS BLOCK TOO
------------------------
D1 never overwrites a set value with a disagreeing reading — it opens a
conflict (`cliente_campo_conflitos` 138, `imovel_campo_conflitos` 154) for an
admin. While one is open on a contract field, the value the contract would
print is contested, so `listar_conflitos` reports it beside the pending list
and `gerar` refuses on either. Conflicts are READ-ONLY here: the modal links
to the screen that decides them.

ACCEPT / REJECT
---------------
Accept → stamp `confirmado_por/_em` (value untouched). Reject → the value AND
its provenance go NULL: the field becomes `faltando` in the existing gate and
a human types it through the existing manual PATCH (a later extraction may
refill it). Both append one `extracao_validacoes` row (migration 156) carrying
what was decided about which reading — the extractor-refinement signal.

`matricula_ato_detalhes` is the one source whose `origem` is NOT NULL
(`'sugestao' | 'confirmado'`, CHECKed against `confirmado_em`): accept flips
it to `'confirmado'`; reject empties the reading (`data_registro` NULL,
`transmitentes` `[]`) and leaves it a `'sugestao'` with nothing in it — not
pending (nothing to vouch for), and `antigos_proprietarios` then reports the
date unknown, which the gate already handles.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable, Literal, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException, ValidationError_

from app.modules.card_hub.contrato_gerador.dados import DadosContrato, Pessoa
from app.modules.card_hub.contrato_gerador.derivacao import ROTULO_QUALIFICACAO
from app.modules.card_hub.identidade_extracao_service import CAMPOS as CAMPOS_IDENTIDADE
from app.modules.certidoes import service as certidoes_svc
from app.modules.imovel_hub import dados_service
from app.modules.imovel_hub import documentos_service as imovel_docs_svc
from app.modules.matriculas import titulo_service
from app.services import table_reads

LEDGER = "extracao_validacoes"

Decisao = Literal["aceito", "rejeitado"]

ENTIDADE_CLIENTE = "cliente"
ENTIDADE_IMOVEL = "imovel"
ENTIDADE_IMOVEL_DOCUMENTO = "imovel_documento"
ENTIDADE_CERTIDAO = "certidao"
ENTIDADE_ATO_DETALHE = "ato_detalhe"

#: Entity → the table its row lives in. `imovel_dados` has no id of its own —
#: it is keyed `(org_id, codigo)`, see `_filtro_linha`.
TABELAS: dict[str, str] = {
    ENTIDADE_CLIENTE: "clientes",
    ENTIDADE_IMOVEL: "imovel_dados",
    ENTIDADE_IMOVEL_DOCUMENTO: "imovel_documentos",
    ENTIDADE_CERTIDAO: "certidao_resultados",
    ENTIDADE_ATO_DETALHE: "matricula_ato_detalhes",
}

_ESTADOS_COM_CONJUGE = frozenset({"casado", "uniao_estavel"})


# ─── The registry ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Edicao:
    """How the modal's inline input writes a REJECTED value back by hand —
    through the EXISTING manual route, which stamps `origem='manual'` itself
    (`clientes_service.update_cliente` / `dados_service.atualizar`). `None`
    on an entry = no single-input route (a multi-column group, an enumerated
    field); the modal then points at the card tab instead."""

    rota: str  # template: `{id}` is the entity id
    campo: str  # the body key
    tipo: Literal["texto", "data"] = "texto"


@dataclass(frozen=True)
class CampoValidavel:
    """One contract-feeding value (or ONE reading spread over several
    columns, e.g. the endereço or a certidão) and where its provenance lives.
    """

    entidade: str
    campo: str
    rotulo: str
    #: The value column(s). Read to render/log the value; emptied on reject.
    valores: tuple[str, ...]
    origem: str
    confirmado_por: str
    confirmado_em: str
    documento_id: Optional[str] = None
    em: Optional[str] = None
    #: A confidence column on the SAME row (the ato detalhe carries its own).
    confianca_coluna: Optional[str] = None
    #: `None` = anything but `'manual'` is a machine; otherwise the explicit set.
    origens_maquina: Optional[frozenset[str]] = None
    #: `origem` is NOT NULL on this table (the ato detalhe) — reject keeps it.
    origem_obrigatoria: bool = False
    #: Extra columns an accept must set (the ato detalhe's `origem`).
    ao_aceitar: tuple[tuple[str, Any], ...] = ()
    #: The empty value each `valores` column takes on reject (default NULL).
    vazio: tuple[tuple[str, Any], ...] = ()
    obrigatorio: bool = True
    edicao: Optional[Edicao] = None

    def ativo(self, row: dict) -> bool:
        return self.origem in row and self.confirmado_em in row

    def pendente(self, row: dict) -> bool:
        if not self.ativo(row):
            return False
        origem = row.get(self.origem)
        if origem is None or origem == "manual":
            return False
        if self.origens_maquina is not None and origem not in self.origens_maquina:
            return False
        if row.get(self.confirmado_em) is not None:
            return False
        return any(preenchido(row.get(c)) for c in self.valores)


def _quinteto(
    entidade: str,
    campo: str,
    rotulo: str,
    *,
    valores: Optional[tuple[str, ...]] = None,
    prefixo: Optional[str] = None,
    obrigatorio: bool = True,
    edicao: Optional[Edicao] = None,
    documento: bool = True,
) -> CampoValidavel:
    """The house provenance quintet: `<p>_origem/_documento_id/_em/
    _confirmado_por/_confirmado_em` (068 → 153)."""
    p = prefixo or campo
    return CampoValidavel(
        entidade=entidade,
        campo=campo,
        rotulo=rotulo,
        valores=valores or (campo,),
        origem=f"{p}_origem",
        confirmado_por=f"{p}_confirmado_por",
        confirmado_em=f"{p}_confirmado_em",
        documento_id=f"{p}_documento_id" if documento else None,
        em=f"{p}_em",
        obrigatorio=obrigatorio,
        edicao=edicao,
    )


def _ed_cliente(campo: str, tipo: Literal["texto", "data"] = "texto") -> Edicao:
    return Edicao(rota="/api/clientes/{id}", campo=campo, tipo=tipo)


def _ed_imovel(campo: str) -> Edicao:
    return Edicao(rota="/api/imoveis/{id}/dados", campo=campo)


_ENDERECO_COLUNAS = (
    "endereco_cep", "endereco_logradouro", "endereco_numero", "endereco_complemento",
    "endereco_bairro", "endereco_cidade", "endereco_uf",
)

#: `clientes` — every column `carregador._pessoa` reads that has provenance.
CAMPOS_CLIENTE: tuple[CampoValidavel, ...] = (
    _quinteto(ENTIDADE_CLIENTE, "nome_oficial", ROTULO_QUALIFICACAO["nome_oficial"],
              edicao=_ed_cliente("nome_oficial")),
    _quinteto(ENTIDADE_CLIENTE, "cpf", ROTULO_QUALIFICACAO["cpf"], edicao=_ed_cliente("cpf")),
    _quinteto(ENTIDADE_CLIENTE, "rg", ROTULO_QUALIFICACAO["rg"], edicao=_ed_cliente("rg")),
    # Migration 153 (identity slice) — inert until it lands.
    _quinteto(ENTIDADE_CLIENTE, "rg_orgao_expedidor", ROTULO_QUALIFICACAO["rg_orgao_expedidor"],
              edicao=_ed_cliente("rg_orgao_expedidor")),
    # Enumerated: no free-text inline input — corrected on the card.
    _quinteto(ENTIDADE_CLIENTE, "genero", ROTULO_QUALIFICACAO["genero"]),
    _quinteto(ENTIDADE_CLIENTE, "estado_civil", ROTULO_QUALIFICACAO["estado_civil"]),
    _quinteto(ENTIDADE_CLIENTE, "regime_bens", ROTULO_QUALIFICACAO["regime_bens"]),
    _quinteto(ENTIDADE_CLIENTE, "data_casamento", ROTULO_QUALIFICACAO["data_casamento"],
              edicao=_ed_cliente("data_casamento", "data")),
    _quinteto(ENTIDADE_CLIENTE, "nacionalidade", ROTULO_QUALIFICACAO["nacionalidade"],
              edicao=_ed_cliente("nacionalidade")),
    _quinteto(ENTIDADE_CLIENTE, "profissao", ROTULO_QUALIFICACAO["profissao"],
              edicao=_ed_cliente("profissao")),
    # Migration 153 — ONE reading of the comprovante, ONE provenance group.
    _quinteto(ENTIDADE_CLIENTE, "endereco", ROTULO_QUALIFICACAO["endereco"],
              valores=_ENDERECO_COLUNAS, prefixo="endereco"),
    # Migration 153 — the link read off a certidão de casamento.
    _quinteto(ENTIDADE_CLIENTE, "conjuge", ROTULO_QUALIFICACAO["conjuge"],
              valores=("conjuge_cliente_id",), prefixo="conjuge"),
    # 148 has `_origem`/`_em` only; 153 adds `_confirmado_por/_em`.
    _quinteto(ENTIDADE_CLIENTE, "certidao_estado_civil_emitida_em",
              "Emissão da certidão de estado civil", documento=False, obrigatorio=False,
              edicao=_ed_cliente("certidao_estado_civil_emitida_em", "data")),
)

#: `imovel_dados` — the columns `carregador._imovel` reads that have provenance.
CAMPOS_IMOVEL: tuple[CampoValidavel, ...] = (
    _quinteto(ENTIDADE_IMOVEL, "numero_matricula", "Número da matrícula",
              edicao=_ed_imovel("numero_matricula")),
    # Migration 154 (imóvel slice) — inert until it lands.
    _quinteto(ENTIDADE_IMOVEL, "numero_registro_imoveis", "Cartório de registro de imóveis",
              edicao=_ed_imovel("numero_registro_imoveis")),
    _quinteto(ENTIDADE_IMOVEL, "prefeitura_cadastro_imobiliario",
              "Inscrição municipal (cadastro na prefeitura)",
              edicao=_ed_imovel("prefeitura_cadastro_imobiliario")),
    _quinteto(ENTIDADE_IMOVEL, "situacao_onus", "Situação de ônus"),
    CampoValidavel(
        entidade=ENTIDADE_IMOVEL, campo="titulo_aquisitivo_texto",
        rotulo="Título aquisitivo (texto do contrato)",
        valores=("titulo_aquisitivo_texto",), origem="titulo_aquisitivo_texto_origem",
        confirmado_por="titulo_aquisitivo_texto_confirmado_por",
        confirmado_em="titulo_aquisitivo_texto_confirmado_em",
    ),
    CampoValidavel(
        entidade=ENTIDADE_IMOVEL, campo="onus_credor", rotulo="Credor do ônus",
        valores=("onus_credor",), origem="onus_credor_origem",
        confirmado_por="onus_credor_confirmado_por", confirmado_em="onus_credor_confirmado_em",
        obrigatorio=False,
    ),
    # 109 — the título aquisitivo's source ACT (a pointer into a transcribed
    # matrícula). Machine-filled with `origem='sugerido'` by migration 154's
    # preenchimento; `carregador` gates on its `confirmado_em`
    # (`Imovel.titulo_aquisitivo_confirmado`), so accepting it here IS that
    # confirmation. 109's CHECKs tie the pointer columns to the origem —
    # reject empties them all together.
    CampoValidavel(
        entidade=ENTIDADE_IMOVEL, campo="titulo_aquisitivo",
        rotulo="Título aquisitivo (ato da matrícula)",
        valores=(
            "titulo_aquisitivo_ato_id", "titulo_aquisitivo_extracao_id",
            "titulo_aquisitivo_char_inicio", "titulo_aquisitivo_char_fim",
        ),
        origem="titulo_aquisitivo_origem",
        confirmado_por="titulo_aquisitivo_confirmado_por",
        confirmado_em="titulo_aquisitivo_confirmado_em",
    ),
    # 109 — `'sugerido' | 'manual'`; a CHECK ties `onus_fonte_extracao_id` to
    # the origem, so reject empties both.
    CampoValidavel(
        entidade=ENTIDADE_IMOVEL, campo="onus_fonte", rotulo="Atos de ônus citados no contrato",
        valores=("onus_fonte_atos", "onus_fonte_extracao_id"), origem="onus_fonte_origem",
        confirmado_por="onus_fonte_confirmado_por", confirmado_em="onus_fonte_confirmado_em",
        obrigatorio=False,
    ),
)

#: The three `imovel_dados` columns `carregador._permuta_imoveis` reads.
CAMPOS_IMOVEL_PERMUTA: tuple[CampoValidavel, ...] = tuple(
    c for c in CAMPOS_IMOVEL
    if c.campo in ("numero_matricula", "numero_registro_imoveis", "prefeitura_cadastro_imobiliario")
)

#: One imóvel certidão (118) — the structured read is ONE group.
CAMPO_IMOVEL_DOCUMENTO = CampoValidavel(
    entidade=ENTIDADE_IMOVEL_DOCUMENTO, campo="certidao", rotulo="Certidão do imóvel",
    valores=("numero", "emitida_em", "validade_ate", "resultado", "inscricao_imobiliaria"),
    origem="origem", confirmado_por="confirmado_por", confirmado_em="confirmado_em",
    origens_maquina=frozenset({"ia"}),
)

#: One party certidão (107) — `resultado_origem` `'api' | 'ia' | 'manual'`.
CAMPO_CERTIDAO = CampoValidavel(
    entidade=ENTIDADE_CERTIDAO, campo="certidao", rotulo="Certidão",
    valores=("numero", "emitida_em", "validade_ate", "resultado"),
    origem="resultado_origem", confirmado_por="confirmado_por", confirmado_em="confirmado_em",
    origens_maquina=frozenset({"api", "ia"}),
)

#: The última transferência act's typed reading (115).
CAMPO_ATO_DETALHE = CampoValidavel(
    entidade=ENTIDADE_ATO_DETALHE, campo="ultima_transferencia",
    rotulo="Última transferência (data de registro e transmitentes)",
    valores=("data_registro", "transmitentes"),
    origem="origem", confirmado_por="confirmado_por", confirmado_em="confirmado_em",
    confianca_coluna="data_registro_confianca",
    origens_maquina=frozenset({"sugestao"}),
    origem_obrigatoria=True,
    ao_aceitar=(("origem", "confirmado"),),
    vazio=(("transmitentes", []),),
)

REGISTRO: tuple[CampoValidavel, ...] = (
    *CAMPOS_CLIENTE, *CAMPOS_IMOVEL, CAMPO_IMOVEL_DOCUMENTO, CAMPO_CERTIDAO, CAMPO_ATO_DETALHE,
)
_POR_ENTIDADE_CAMPO: dict[tuple[str, str], CampoValidavel] = {
    (c.entidade, c.campo): c for c in REGISTRO
}


# ─── Errors ─────────────────────────────────────────────────────────────────


class ExtracaoPendenteValidacao(AppException):
    """`gerar` refused: machine-extracted values a human has not validated
    yet, or open extraction conflicts on contract data. `details.{pendentes,
    conflitos}` is the same answer the GET returns."""

    def __init__(self, pendentes: list[dict], conflitos: Optional[list[dict]] = None) -> None:
        super().__init__(
            code="EXTRACAO_PENDENTE_VALIDACAO",
            message=(
                "O contrato não pode ser gerado: há dados extraídos de documentos "
                "aguardando validação humana."
            ),
            status_code=409,
            details={"pendentes": pendentes, "conflitos": conflitos or []},
        )


class ValidacaoDesatualizada(AppException):
    """A decision named a `chave` that is not pending (any more) — decided
    in another tab, re-extracted, or never existed. Nothing was written."""

    def __init__(self, chaves: list[str]) -> None:
        super().__init__(
            code="EXTRACAO_VALIDACAO_DESATUALIZADA",
            message="Alguns itens já não estão pendentes de validação. Recarregue a lista.",
            status_code=409,
            details={"chaves": chaves},
        )


# ─── Helpers ────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def preenchido(valor: Any) -> bool:
    if valor is None:
        return False
    if isinstance(valor, str):
        return bool(valor.strip())
    if isinstance(valor, (list, tuple, dict)):
        return bool(valor)
    return True


def _texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, (list, dict)):
        return json.dumps(valor, ensure_ascii=False, default=str)
    return str(valor)


def chave(entidade: str, entidade_id: str, campo: str) -> str:
    return f"{entidade}:{entidade_id}:{campo}"


def valor_exibicao(campo: CampoValidavel, row: dict, nomes: dict[str, str]) -> Optional[str]:
    if campo.entidade == ENTIDADE_CLIENTE and campo.campo == "conjuge":
        alvo = row.get("conjuge_cliente_id")
        return nomes.get(str(alvo), str(alvo)) if alvo else None
    if campo.entidade == ENTIDADE_ATO_DETALHE:
        partes = []
        if row.get("data_registro"):
            partes.append(f"registro em {row['data_registro']}")
        nomes_t = [t.get("nome") for t in row.get("transmitentes") or [] if t.get("nome")]
        if nomes_t:
            partes.append("transmitentes: " + ", ".join(nomes_t))
        return " · ".join(partes) or None
    if campo.campo == "titulo_aquisitivo":
        ato = row.get("titulo_aquisitivo_ato_id")
        return nomes.get(str(ato), "ato da matrícula") if ato else None
    if campo.campo == "onus_fonte":
        atos = row.get("onus_fonte_atos") or []
        rotulos = [nomes.get(str(a.get("ato_id")), "ato") for a in atos if isinstance(a, dict)]
        return ", ".join(rotulos) or None
    if len(campo.valores) == 1:
        return _texto(row.get(campo.valores[0]))
    return " · ".join(
        f"{c}: {_texto(row.get(c))}" for c in campo.valores if preenchido(row.get(c))
    ) or None


def _valor_ledger(campo: CampoValidavel, row: dict) -> Optional[str]:
    if len(campo.valores) == 1:
        return _texto(row.get(campo.valores[0]))
    return json.dumps({c: row.get(c) for c in campo.valores}, ensure_ascii=False, default=str)


def _obrigatorio(campo: CampoValidavel, row: dict) -> bool:
    """Static in the registry, except the three a married state switches on
    (CC art. 1.647 — `documento_checklist_service._ESTADOS_QUE_EXIGEM_CONJUGE`)."""
    if campo.entidade == ENTIDADE_CLIENTE and campo.campo in ("regime_bens", "conjuge"):
        return (row.get("estado_civil") or "") in _ESTADOS_COM_CONJUGE
    if campo.entidade == ENTIDADE_CLIENTE and campo.campo == "data_casamento":
        return row.get("estado_civil") == "casado"
    return campo.obrigatorio


# ─── The pending read ───────────────────────────────────────────────────────


@dataclass
class Alvo:
    """One entity row to check, with how the modal should label it."""

    campos: tuple[CampoValidavel, ...]
    entidade_id: str
    row: dict
    grupo: str
    rotulo_sufixo: Optional[str] = None
    fonte_nome_propria: Optional[str] = None  # the row IS the document
    fonte_id_propria: Optional[str] = None
    confianca_propria: Optional[str] = None


@dataclass
class Coleta:
    alvos: list[Alvo] = field(default_factory=list)
    nomes: dict[str, str] = field(default_factory=dict)


def _rows_por_id(client: Any, org_id: UUID, tabela: str, ids: Iterable[str], select: str = "*") -> dict[str, dict]:
    lista = sorted({str(i) for i in ids if i})
    if not lista:
        return {}
    return {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(client, tabela, org_id, "id", lista, select=select)
    }


def _rotulo_pessoa(p: Pessoa, row: dict) -> str:
    nome = row.get("nome_oficial") or row.get("nome") or p.nome or p.nome_cadastro or p.cliente_id
    papel = p.papel.replace("_", " ")
    return f"{nome} ({papel})"


def coletar(client: Any, org_id: UUID, dados: DadosContrato, usuario_id: Optional[Any]) -> Coleta:
    coleta = Coleta()
    pessoas: list[Pessoa] = []
    vistos: set[str] = set()
    for p in [*dados.compradores, *dados.vendedores]:
        if p.cliente_id not in vistos:
            vistos.add(p.cliente_id)
            pessoas.append(p)

    clientes = _rows_por_id(client, org_id, "clientes", [p.cliente_id for p in pessoas])
    conjuges_extra = {
        str(r["conjuge_cliente_id"]) for r in clientes.values() if r.get("conjuge_cliente_id")
    } - set(clientes)
    for cid, r in _rows_por_id(client, org_id, "clientes", conjuges_extra, select="id,nome,nome_oficial").items():
        coleta.nomes[cid] = r.get("nome_oficial") or r.get("nome") or cid
    for cid, r in clientes.items():
        coleta.nomes[cid] = r.get("nome_oficial") or r.get("nome") or cid

    for p in pessoas:
        row = clientes.get(p.cliente_id)
        if row is None:
            continue
        grupo = _rotulo_pessoa(p, row)
        coleta.alvos.append(Alvo(CAMPOS_CLIENTE, p.cliente_id, row, grupo))
        brutas = (
            certidoes_svc.certidoes_por_parte(client, org_id, p.parte_id)
            if p.parte_id
            else certidoes_svc.certidoes_por_cliente(client, org_id, p.cliente_id)
        )
        for r in brutas:
            coleta.alvos.append(
                Alvo(
                    (CAMPO_CERTIDAO,), str(r["id"]), r, f"Certidões — {grupo}",
                    rotulo_sufixo=r.get("nome_display") or r.get("tipo"),
                    # The resultado IS the document (its uploaded/fetched file).
                    fonte_nome_propria=r.get("arquivo_nome"),
                    fonte_id_propria=str(r["id"]),
                )
            )

    im = dados.imovel
    if im is not None:
        linha = dados_service.linha(client, org_id, im.codigo) or {}
        if linha:
            coleta.alvos.append(Alvo(CAMPOS_IMOVEL, im.codigo, linha, f"Imóvel {im.codigo}"))
        itens = imovel_docs_svc.certidoes(client, org_id, im.codigo)["items"]
        docs = _rows_por_id(
            client, org_id, "imovel_documentos", [i["documento_id"] for i in itens],
            select="id,nome_original,tipo_documento,numero,emitida_em,validade_ate,resultado,"
                   "inscricao_imobiliaria,origem,confirmado_por,confirmado_em",
        )
        for item in itens:
            doc = docs.get(str(item["documento_id"]))
            if doc is None:
                continue
            coleta.alvos.append(
                Alvo(
                    (CAMPO_IMOVEL_DOCUMENTO,), str(doc["id"]), doc,
                    f"Certidões do imóvel {im.codigo}", rotulo_sufixo=item["tipo"],
                    fonte_nome_propria=doc.get("nome_original"), fonte_id_propria=str(doc["id"]),
                )
            )
        antigos = titulo_service.antigos_proprietarios(client, org_id, im.codigo, usuario_id=usuario_id)
        ato_id = ((antigos.get("ultima_transferencia") or {}).get("ato_id"))
        if ato_id:
            det = (
                table_reads.table(client, TABELAS[ENTIDADE_ATO_DETALHE])
                .select("*")
                .eq("org_id", str(org_id))
                .eq("ato_id", str(ato_id))
                .limit(1)
                .execute()
            ).data or []
            if det:
                coleta.alvos.append(
                    Alvo((CAMPO_ATO_DETALHE,), str(det[0]["id"]), det[0], f"Imóvel {im.codigo}")
                )

    ativo_ids = [p.permuta_ativo_id for p in dados.permuta_imoveis]
    if ativo_ids:
        ativos = table_reads.in_batched_rows(client, "permuta_ativos", org_id, "id", ativo_ids)
        codigos = sorted({a["imovel_codigo"] for a in ativos if a.get("imovel_codigo")})
        for codigo in codigos:
            if im is not None and codigo == im.codigo:
                continue
            linha = dados_service.linha(client, org_id, codigo) or {}
            if linha:
                coleta.alvos.append(
                    Alvo(CAMPOS_IMOVEL_PERMUTA, codigo, linha, f"Imóvel da permuta {codigo}")
                )

    # The act labels ("R.1", "AV.3") the título/ônus pointers render as.
    ato_ids: set[str] = set()
    for alvo in coleta.alvos:
        if alvo.campos is CAMPOS_IMOVEL:
            if alvo.row.get("titulo_aquisitivo_ato_id"):
                ato_ids.add(str(alvo.row["titulo_aquisitivo_ato_id"]))
            for a in alvo.row.get("onus_fonte_atos") or []:
                if isinstance(a, dict) and a.get("ato_id"):
                    ato_ids.add(str(a["ato_id"]))
    for aid, ato in _rows_por_id(client, org_id, "matricula_atos", ato_ids,
                                 select="id,kind,numero").items():
        coleta.nomes[aid] = (
            f"{ato['kind']}.{ato['numero']}" if ato.get("numero") is not None else str(ato.get("kind"))
        )
    return coleta


def documentos_de_origem(client: Any, org_id: UUID, pares: list[tuple[Alvo, CampoValidavel]]) -> dict[str, dict]:
    """The source document of each value in `pares` (pending or not —
    `listar_pendentes`/`decidir` call this with only-pending pairs,
    `proveniencia.linhagem` with every active one): `cliente_documentos`
    for a cliente field, `imovel_documentos` or `matricula_extracoes` for
    an imóvel field (154's `_documento_id` may point at either). Each
    returned row is tagged `_tabela` with the table it was actually found
    in, so a caller can tell the three apart without re-deriving it —
    `proveniencia.linhagem` turns that into an `Entrada` (`fontes.
    TABELA_ENTRADA`); this module stays free of that vocabulary."""
    ids_cliente, ids_imovel = set(), set()
    for alvo, campo in pares:
        doc_id = alvo.row.get(campo.documento_id) if campo.documento_id else None
        if not doc_id:
            continue
        (ids_cliente if campo.entidade == ENTIDADE_CLIENTE else ids_imovel).add(str(doc_id))
    fontes: dict[str, dict] = {}
    for did, r in _rows_por_id(client, org_id, "cliente_documentos", ids_cliente).items():
        fontes[did] = r | {"_nome": r.get("nome_original"), "_tabela": "cliente_documentos"}
    for did, r in _rows_por_id(client, org_id, "imovel_documentos", ids_imovel,
                               select="id,nome_original,tipo_documento,extracao_confianca").items():
        fontes[did] = r | {"_nome": r.get("nome_original"), "_tabela": "imovel_documentos"}
    restantes = ids_imovel - set(fontes)
    for did, r in _rows_por_id(client, org_id, "matricula_extracoes", restantes,
                               select="id,nome_arquivo").items():
        fontes[did] = r | {"_nome": r.get("nome_arquivo"), "_tabela": "matricula_extracoes"}
    return fontes


_CONFIANCA_IDENTIDADE = {c.item_key: c.coluna_confianca for c in CAMPOS_IDENTIDADE}


def _confianca(campo: CampoValidavel, alvo: Alvo, fonte: Optional[dict]) -> Optional[str]:
    if campo.confianca_coluna:
        return alvo.row.get(campo.confianca_coluna)
    if fonte is None:
        return None
    if campo.entidade == ENTIDADE_CLIENTE:
        coluna = _CONFIANCA_IDENTIDADE.get(campo.campo, f"extracao_{campo.campo}_confianca")
        return fonte.get(coluna)
    return fonte.get("extracao_confianca") if campo.campo == "numero_matricula" else None


def _pendentes_brutos(coleta: Coleta) -> list[tuple[Alvo, CampoValidavel]]:
    return [(alvo, campo) for alvo in coleta.alvos for campo in alvo.campos if campo.pendente(alvo.row)]


def _item(alvo: Alvo, campo: CampoValidavel, fontes: dict[str, dict], nomes: dict[str, str]) -> dict:
    doc_id = alvo.row.get(campo.documento_id) if campo.documento_id else alvo.fonte_id_propria
    fonte = fontes.get(str(doc_id)) if doc_id else None
    rotulo = f"{campo.rotulo} — {alvo.rotulo_sufixo}" if alvo.rotulo_sufixo else campo.rotulo
    return {
        "chave": chave(campo.entidade, alvo.entidade_id, campo.campo),
        "entidade": campo.entidade,
        "entidade_id": alvo.entidade_id,
        "campo": campo.campo,
        "grupo": alvo.grupo,
        "rotulo": rotulo,
        "valor": valor_exibicao(campo, alvo.row, nomes),
        "origem": alvo.row.get(campo.origem),
        "fonte_documento_id": str(doc_id) if doc_id else None,
        "fonte_nome": (fonte or {}).get("_nome") or alvo.fonte_nome_propria,
        "confianca": _confianca(campo, alvo, fonte),
        "obrigatorio": _obrigatorio(campo, alvo.row),
        "edicao": (
            {
                "rota": campo.edicao.rota.replace("{id}", alvo.entidade_id),
                "campo": campo.edicao.campo,
                "tipo": campo.edicao.tipo,
            }
            if campo.edicao
            else None
        ),
    }


#: `cliente_campo_conflitos.campo` is the `CampoExtraido.item_key` — the same
#: name as a `CAMPOS_CLIENTE` entry, except the cônjuge link, which the
#: identity slice (153) files under its column name. Only these feed the
#: contract (e.g. `data_nascimento` does not).
_CONFLITO_CAMPO_CLIENTE: dict[str, str] = {
    **{c.campo: c.campo for c in CAMPOS_CLIENTE},
    "conjuge_cliente_id": "conjuge",
}


def listar_conflitos(client: Any, org_id: UUID, dados: DadosContrato) -> list[dict]:
    """Open extraction CONFLICTS on this contract's data — a later reading
    disagreed with a value already set (D1: never a silent overwrite), and an
    admin has not decided it. Read-only here (deciding is the conflict
    screens' job), but they block generation exactly like a pending value:
    the value the contract would print is contested.

    - `cliente_campo_conflitos` (138) on every parte, for a contract field;
    - `imovel_campo_conflitos` (154, imóvel slice) on the imóvel + permuta
      imóveis — every field that table carries is an `imovel_dados` field the
      contract reads.
    """
    pessoas = {p.cliente_id: p for p in [*dados.compradores, *dados.vendedores]}
    saida: list[dict] = []
    if pessoas:
        rows = table_reads.in_batched_rows(
            client, "cliente_campo_conflitos", org_id, "cliente_id", sorted(pessoas)
        )
        for r in rows:
            registro = _CONFLITO_CAMPO_CLIENTE.get(r.get("campo") or "")
            if r.get("status") != "pendente" or registro is None:
                continue
            p = pessoas[str(r["cliente_id"])]
            campo = _POR_ENTIDADE_CAMPO[(ENTIDADE_CLIENTE, registro)]
            saida.append({
                "id": str(r["id"]),
                "entidade": ENTIDADE_CLIENTE,
                "entidade_id": p.cliente_id,
                "campo": registro,
                "grupo": _rotulo_pessoa(p, {}),
                "rotulo": campo.rotulo,
                "valor_atual": _texto(r.get("valor_anterior")),
                "valor_proposto": _texto(r.get("valor_proposto")),
                "origem_proposto": r.get("origem_proposto"),
                "link": {"rota": "/configuracoes", "rotulo": "Configurações → Pendências"},
            })

    codigos: list[str] = []
    if dados.imovel is not None:
        codigos.append(dados.imovel.codigo)
    ativo_ids = [p.permuta_ativo_id for p in dados.permuta_imoveis]
    if ativo_ids:
        for a in table_reads.in_batched_rows(client, "permuta_ativos", org_id, "id", ativo_ids):
            if a.get("imovel_codigo") and a["imovel_codigo"] not in codigos:
                codigos.append(a["imovel_codigo"])
    if codigos:
        rotulos_imovel = {c.campo: c.rotulo for c in CAMPOS_IMOVEL}
        rows = (
            table_reads.table(client, "imovel_campo_conflitos")
            .select("*")
            .eq("org_id", str(org_id))
            .in_("codigo", codigos)
            .eq("status", "pendente")
            .execute()
        ).data or []
        for r in rows:
            codigo = r["codigo"]
            saida.append({
                "id": str(r["id"]),
                "entidade": ENTIDADE_IMOVEL,
                "entidade_id": codigo,
                "campo": r["campo"],
                "grupo": f"Imóvel {codigo}",
                "rotulo": rotulos_imovel.get(r["campo"], r["campo"]),
                "valor_atual": _texto(r.get("valor_anterior")),
                "valor_proposto": _texto(r.get("valor_proposto")),
                "origem_proposto": r.get("origem_proposto"),
                "link": {
                    "rota": f"/imoveis/{codigo}?conflito={r['id']}",
                    "rotulo": f"Imóvel {codigo}",
                },
            })
    return saida


def listar_pendentes(
    client: Any, org_id: UUID, dados: DadosContrato, *, usuario_id: Optional[Any]
) -> list[dict]:
    """Every machine-pending contract-feeding value of the contract `dados`
    was loaded for — the GET answer and `gerar`'s precondition."""
    coleta = coletar(client, org_id, dados, usuario_id)
    brutos = _pendentes_brutos(coleta)
    fontes = documentos_de_origem(client, org_id, brutos)
    return [_item(alvo, campo, fontes, coleta.nomes) for alvo, campo in brutos]


def situacao(
    client: Any, org_id: UUID, dados: DadosContrato, *, usuario_id: Optional[Any]
) -> dict:
    """The GET answer: `{pendentes, conflitos}` — generation may proceed iff
    both are empty."""
    return {
        "pendentes": listar_pendentes(client, org_id, dados, usuario_id=usuario_id),
        "conflitos": listar_conflitos(client, org_id, dados),
    }


def exigir_sem_pendentes(
    client: Any, org_id: UUID, dados: DadosContrato, *, usuario_id: Optional[Any]
) -> None:
    estado = situacao(client, org_id, dados, usuario_id=usuario_id)
    if estado["pendentes"] or estado["conflitos"]:
        raise ExtracaoPendenteValidacao(estado["pendentes"], estado["conflitos"])


# ─── Decisions ──────────────────────────────────────────────────────────────


def _filtro_linha(query: Any, org_id: UUID, entidade: str, entidade_id: str) -> Any:
    query = query.eq("org_id", str(org_id))
    if entidade == ENTIDADE_IMOVEL:
        return query.eq("codigo", entidade_id)
    return query.eq("id", entidade_id)


def _patch_aceite(campo: CampoValidavel, row: dict, usuario_id: Optional[Any], agora: str) -> dict:
    patch = {
        campo.confirmado_por: str(usuario_id) if usuario_id else None,
        campo.confirmado_em: agora,
    }
    patch.update(dict(campo.ao_aceitar))
    return {k: v for k, v in patch.items() if k in row}


def _patch_rejeite(campo: CampoValidavel, row: dict) -> dict:
    vazios = dict(campo.vazio)
    patch: dict[str, Any] = {c: vazios.get(c) for c in campo.valores}
    if not campo.origem_obrigatoria:
        patch[campo.origem] = None
    for coluna in (campo.documento_id, campo.em, campo.confirmado_por, campo.confirmado_em):
        if coluna:
            patch[coluna] = None
    return {k: v for k, v in patch.items() if k in row}


def _gravar(client: Any, org_id: UUID, entidade: str, entidade_id: str, row: dict, patch: dict, agora: str) -> None:
    if not patch:
        return
    if "updated_at" in row:
        patch = {**patch, "updated_at": agora}
    _filtro_linha(
        table_reads.table(client, TABELAS[entidade]).update(patch), org_id, entidade, entidade_id
    ).execute()


def _rejeitar_conjuge_reverso(
    client: Any, org_id: UUID, cliente_id: str, conjuge_id: Optional[str], agora: str
) -> None:
    """The cônjuge link is symmetric by construction (`compradores_service.
    _casar` writes both sides); rejecting one side of a MACHINE link must not
    leave the other side pointing back — that is the half-link `derivacao`
    blocks on. A human-set reverse link (`conjuge_origem='manual'`) is kept."""
    if not conjuge_id:
        return
    rows = (
        _filtro_linha(table_reads.table(client, "clientes").select("*"), org_id,
                      ENTIDADE_CLIENTE, str(conjuge_id)).limit(1).execute()
    ).data or []
    if not rows:
        return
    reverso = rows[0]
    if str(reverso.get("conjuge_cliente_id") or "") != cliente_id:
        return
    if reverso.get("conjuge_origem") == "manual":
        return
    campo = _POR_ENTIDADE_CAMPO[(ENTIDADE_CLIENTE, "conjuge")]
    _gravar(client, org_id, ENTIDADE_CLIENTE, str(conjuge_id), reverso,
            _patch_rejeite(campo, reverso), agora)


def decidir(
    client: Any,
    org_id: UUID,
    dados: DadosContrato,
    contrato_id: UUID,
    decisoes: list[tuple[str, str]],
    *,
    usuario_id: Optional[Any],
) -> dict:
    """Apply `[(chave, 'aceito'|'rejeitado'), ...]` and log each to the
    ledger. Every `chave` must be CURRENTLY pending, or nothing is written
    (`ValidacaoDesatualizada`). Returns the remaining pending list."""
    chaves = [c for c, _ in decisoes]
    repetidas = sorted({c for c in chaves if chaves.count(c) > 1})
    if repetidas:
        raise ValidationError_(f"Chave repetida na mesma requisição: {', '.join(repetidas)}", field="decisoes")

    coleta = coletar(client, org_id, dados, usuario_id)
    brutos = _pendentes_brutos(coleta)
    por_chave = {chave(c.entidade, a.entidade_id, c.campo): (a, c) for a, c in brutos}
    desconhecidas = [c for c in chaves if c not in por_chave]
    if desconhecidas:
        raise ValidacaoDesatualizada(desconhecidas)

    fontes = documentos_de_origem(client, org_id, [por_chave[c] for c in chaves])
    agora = _now()
    for ch, decisao in decisoes:
        alvo, campo = por_chave[ch]
        # Both read BEFORE the write: the reject below empties the very row
        # these describe, and the ledger must keep what was thrown away.
        item = _item(alvo, campo, fontes, coleta.nomes)
        valor_extraido = _valor_ledger(campo, alvo.row)
        if decisao == "aceito":
            patch = _patch_aceite(campo, alvo.row, usuario_id, agora)
        else:
            patch = _patch_rejeite(campo, alvo.row)
        _gravar(client, org_id, campo.entidade, alvo.entidade_id, alvo.row, patch, agora)
        if decisao == "rejeitado" and campo.entidade == ENTIDADE_CLIENTE and campo.campo == "conjuge":
            _rejeitar_conjuge_reverso(
                client, org_id, alvo.entidade_id, alvo.row.get("conjuge_cliente_id"), agora
            )
        table_reads.table(client, LEDGER).insert(
            {
                "org_id": str(org_id),
                "contrato_id": str(contrato_id),
                "entidade": campo.entidade,
                "entidade_id": alvo.entidade_id,
                "campo": campo.campo,
                "valor_extraido": valor_extraido,
                "origem": item["origem"],
                "fonte_documento_id": item["fonte_documento_id"],
                "confianca": item["confianca"],
                "decisao": decisao,
                "decidido_por": str(usuario_id) if usuario_id else None,
                "decidido_em": agora,
            }
        ).execute()

    return {"aplicadas": len(decisoes), **situacao(client, org_id, dados, usuario_id=usuario_id)}


__all__ = [
    "Alvo",
    "CAMPOS_CLIENTE",
    "CAMPOS_IMOVEL",
    "CAMPOS_IMOVEL_PERMUTA",
    "CAMPO_ATO_DETALHE",
    "CAMPO_CERTIDAO",
    "CAMPO_IMOVEL_DOCUMENTO",
    "CampoValidavel",
    "Coleta",
    "Decisao",
    "ExtracaoPendenteValidacao",
    "LEDGER",
    "REGISTRO",
    "ValidacaoDesatualizada",
    "chave",
    "coletar",
    "decidir",
    "documentos_de_origem",
    "exigir_sem_pendentes",
    "listar_conflitos",
    "listar_pendentes",
    "preenchido",
    "situacao",
    "valor_exibicao",
]
