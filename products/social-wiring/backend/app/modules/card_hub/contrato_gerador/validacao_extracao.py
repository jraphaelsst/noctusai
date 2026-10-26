"""The human validation gate over machine-extracted contract data (owner
decision D2, roadmap `sw-extraction-contract-gate-2026-09`, migration 156).

🔴 TWO MODES, ONE SWITCH (`politica.Politica.revisao_final_unica`). Owner
decision 2026-09-30: "one final review of the finished contract by the legal
team" replaces the per-field confirmations — the DEFAULT. Then `gerar` calls
`pendentes_para_revisao` (only open conflicts refuse; the pending list is
recorded on the version) and the contract-level review confirms it via
`confirmar_por_revisao` (see `revisao_juridica`). With the flag False,
`exigir_sem_pendentes` + the per-field `decidir` below are the gate, exactly
as D2 shipped — kept for rollback. Everything else here (WHAT/WHICH, the
registry, conflicts) is shared by both modes.

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

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable, Literal, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException, ValidationError_

from app.modules.card_hub.contrato_gerador.dados import DadosContrato, Pessoa
from app.modules.card_hub.contrato_gerador.derivacao import ROTULO_QUALIFICACAO
from app.modules.card_hub.contrato_gerador.frases import REGIME_EXTENSO
from app.modules.card_hub.favorecidos_service import mascarar_conta, mascarar_documento
from app.modules.card_hub.identidade_extracao_service import CAMPO_POR_ITEM
from app.modules.card_hub.identidade_extracao_service import CAMPOS as CAMPOS_IDENTIDADE
from app.modules.card_hub.identidade_extracao_service import ORIGEM_CONJUGE_DOMICILIO
from app.modules.card_hub.identidade_extracao_service import endereco_comprovante_confirma_ficha
from app.modules.card_hub.identidade_extracao_service import _mesmo_valor
from app.modules.certidoes import service as certidoes_svc
from app.modules.imovel_hub import vinculo_legal
from app.modules.imovel_hub import documentos_service as imovel_docs_svc
from app.modules.matriculas import titulo_service
from app.services import divergencia_resolucao, table_reads

LEDGER = "extracao_validacoes"

Decisao = Literal["aceito", "rejeitado"]

ENTIDADE_CLIENTE = "cliente"
ENTIDADE_IMOVEL = "imovel"
ENTIDADE_IMOVEL_DOCUMENTO = "imovel_documento"
ENTIDADE_CERTIDAO = "certidao"
ENTIDADE_ATO_DETALHE = "ato_detalhe"
#: [E1/E2] An `empresas` row's group provenance (contract §A.1) — the
#: Cartão-CNPJ-sourced cadastral fields, same `<p>_origem/_documento_id/
#: _em/_confirmado_por/_confirmado_em` shape as a cliente/imóvel group.
ENTIDADE_EMPRESA = "empresa"
#: [S2b, negociação/financiamento extraction contract §E4/§C, migration
#: 171] `atendimento_negociacao.valor_negociado`'s house quintet — keyed by
#: `atendimento_id`, not `id` (see `_filtro_linha`).
ENTIDADE_NEGOCIACAO = "negociacao"
#: One `atendimento_negociacao_parcelas` row's `valor` — FLAT row
#: provenance (`origem, documento_id, extraido_em, confirmado_por,
#: confirmado_em`, §C item 4), keyed by the parcela's own `id`. The [H4]
#: derived intermediária suggestion is not a separate entry: it is the
#: same field with `origem='derivado'`.
ENTIDADE_PARCELA = "parcela"
#: [H5] One `atendimento_favorecidos` row's bank data, filled from the
#: Quadro Resumo's seller-credit account — same flat row-provenance shape
#: as the parcela, keyed by the favorecido's own `id`.
ENTIDADE_FAVORECIDO = "favorecido"
#: `atendimento_financiamento`'s house quintets (fgts, numero_proposta,
#: agente_financeiro, and [H6] situacao) — keyed by `atendimento_id`.
ENTIDADE_FINANCIAMENTO = "financiamento"

#: Entity → the table its row lives in. `imovel_dados` has no id of its own —
#: it is keyed `(org_id, codigo)`, see `_filtro_linha`. `negociacao` and
#: `financiamento` are keyed by `atendimento_id` the same way.
TABELAS: dict[str, str] = {
    ENTIDADE_CLIENTE: "clientes",
    ENTIDADE_IMOVEL: "imovel_dados",
    ENTIDADE_IMOVEL_DOCUMENTO: "imovel_documentos",
    ENTIDADE_CERTIDAO: "certidao_resultados",
    ENTIDADE_ATO_DETALHE: "matricula_ato_detalhes",
    ENTIDADE_EMPRESA: "empresas",
    ENTIDADE_NEGOCIACAO: "atendimento_negociacao",
    ENTIDADE_PARCELA: "atendimento_negociacao_parcelas",
    ENTIDADE_FAVORECIDO: "atendimento_favorecidos",
    ENTIDADE_FINANCIAMENTO: "atendimento_financiamento",
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

    def pendente(self, row: dict, *, corroborado: bool = False) -> bool:
        if not self.ativo(row):
            return False
        origem = row.get(self.origem)
        if origem is None or origem == "manual":
            return False
        if self.origens_maquina is not None and origem not in self.origens_maquina:
            return False
        if row.get(self.confirmado_em) is not None:
            return False
        if not any(preenchido(row.get(c)) for c in self.valores):
            return False
        # BUILD item 2 (owner directive, 2026-09-29) + its follow-up
        # (2026-09-29): a machine value from a source whose measured
        # precision for THIS field is >=95% with n>=10
        # (`divergencia_resolucao.PRECISAO`), OR one corroborated by >=2
        # independent documents (`corroborado`, computed by the caller —
        # `_pendentes_brutos`'s own batched `_corroboracao_cliente`, ONE
        # query per contract read, never per field), counts as validated --
        # `exigir_sem_pendentes` may proceed without a human click. Scoped
        # naturally by the evidence table itself: an (entidade, campo) it
        # does not cover (every non-`cliente` entity today — imóvel,
        # certidão, empresa, negociação, ...) always reads `False` here
        # (`corroborado` defaults `False` too for those callers), so every
        # OTHER `CampoValidavel` behaves exactly as before this directive.
        return not divergencia_resolucao.valido_para_contrato_sem_revisao(
            self.campo, origem, corroborado=corroborado
        )


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
    vazio: tuple[tuple[str, Any], ...] = (),
) -> CampoValidavel:
    """The house provenance quintet: `<p>_origem/_documento_id/_em/
    _confirmado_por/_confirmado_em` (068 → 153). `vazio` overrides the
    default NULL a reject writes to a `valores` column that is NOT NULL
    (e.g. `atendimento_financiamento.fgts` — [S2b §E4 item 4] resets to
    `False`, never NULL)."""
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
        vazio=vazio,
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
    # Migration 238 — the e-mail a ficha cadastral prints (signature block);
    # optional: a missing e-mail is the PARTE_SEM_EMAIL warning, not a block.
    _quinteto(ENTIDADE_CLIENTE, "email", "E-mail", obrigatorio=False,
              edicao=_ed_cliente("email")),
    # Migration 193 — the pacto antenupcial citation the qualification
    # prints; optional (only couples whose regime needs a pacto have one).
    _quinteto(ENTIDADE_CLIENTE, "pacto_antenupcial_data", "Data do pacto antenupcial",
              obrigatorio=False, edicao=_ed_cliente("pacto_antenupcial_data", "data")),
    _quinteto(ENTIDADE_CLIENTE, "pacto_antenupcial_tabelionato", "Tabelionato do pacto antenupcial",
              obrigatorio=False, edicao=_ed_cliente("pacto_antenupcial_tabelionato")),
    _quinteto(ENTIDADE_CLIENTE, "pacto_antenupcial_livro", "Livro do pacto antenupcial",
              obrigatorio=False, edicao=_ed_cliente("pacto_antenupcial_livro")),
    _quinteto(ENTIDADE_CLIENTE, "pacto_antenupcial_folha", "Página do pacto antenupcial",
              obrigatorio=False, edicao=_ed_cliente("pacto_antenupcial_folha")),
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

#: One party certidão (107/249) — `resultado_origem` `'api' | 'texto' | 'ia' |
#: 'manual'`. 🔴 Only `'ia'` is a machine READING to review (owner,
#: 2026-10-13): `'api'` is the issuer's own answer and `'texto'` the number/
#: date printed in the issuer's own text — the issuer's verdict, which no
#: human click makes truer. They used to fill the review list with ~15
#: certidão rows nobody could act on.
CAMPO_CERTIDAO = CampoValidavel(
    entidade=ENTIDADE_CERTIDAO, campo="certidao", rotulo="Certidão",
    valores=("numero", "emitida_em", "validade_ate", "resultado"),
    origem="resultado_origem", confirmado_por="confirmado_por", confirmado_em="confirmado_em",
    origens_maquina=frozenset({"ia"}),
)

#: [E1/E2, migration 167] `empresas`' group provenance — one reading (a
#: Cartão CNPJ, or the Serasa Crednet that created the row) fills every
#: cadastral field together (§A.1), so a machine-pending group blocks
#: generation exactly like the imóvel document group does. The rotulo names
#: the FIELD GROUP, never a source — the source is `dados_origem` (a Crednet
#: reading used to be labelled "Cartão CNPJ").
CAMPO_EMPRESA_DADOS = _quinteto(
    ENTIDADE_EMPRESA,
    "dados",
    "Dados cadastrais da empresa",
    valores=(
        "razao_social", "nome_fantasia", "natureza_juridica", "data_abertura",
        "situacao_cadastral", "data_situacao_cadastral", "motivo_situacao", "uf",
    ),
    prefixo="dados",
)

#: `empresa_campo_conflitos.campo` (P0c contract §H6/§H12 — the group fills
#: together, a DISAGREEMENT still opens its own row per field, via
#: `app.modules.empresas.dados_service.CAMPOS_CADASTRAIS`/`aplicar_cartao`)
#: -> a display rotulo, for `listar_conflitos` below. Not the same registry
#: as `CAMPO_EMPRESA_DADOS.valores` (the group-pending check's own list,
#: which also carries `uf` — never written to `empresas.cnpj`, per the
#: module's own scope-cut, so never a conflict campo either).
ROTULOS_EMPRESA_CAMPO: dict[str, str] = {
    "razao_social": "Razão social",
    "nome_fantasia": "Nome fantasia",
    "natureza_juridica": "Natureza jurídica",
    "data_abertura": "Data de abertura",
    "situacao_cadastral": "Situação cadastral",
    "data_situacao_cadastral": "Data da situação cadastral",
    "motivo_situacao": "Motivo da situação",
}

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

#: [S2b, negociação/financiamento extraction contract §E4/§C, migration
#: 171] `atendimento_negociacao.valor_negociado` — house quintet (§H2: no
#: authoritative document; any disagreement is a conflict for a human).
CAMPO_NEGOCIACAO_VALOR = _quinteto(ENTIDADE_NEGOCIACAO, "valor_negociado", "Valor negociado")

#: One `atendimento_negociacao_parcelas` row's `valor` — flat row
#: provenance (`origem, documento_id, extraido_em, confirmado_por,
#: confirmado_em`), NOT the `<p>_origem` quintet shape: `valor` is the
#: table's pre-existing (now nullable, §C item 4) column, not a new
#: `<campo>_*` group. `entidade_id` is the parcela's own `id`.
CAMPO_PARCELA_VALOR = CampoValidavel(
    entidade=ENTIDADE_PARCELA, campo="valor", rotulo="Valor da parcela",
    valores=("valor",), origem="origem", confirmado_por="confirmado_por",
    confirmado_em="confirmado_em", documento_id="documento_id", em="extraido_em",
)

#: [H5] One `atendimento_favorecidos` row's bank data (banco/agência/
#: conta/pix), read off the Quadro Resumo's seller-credit account and
#: matched to a vendedor by CPF — same flat row-provenance shape as the
#: parcela above ("row provenance like parcelas", H5).
CAMPO_FAVORECIDO_DADOS = CampoValidavel(
    entidade=ENTIDADE_FAVORECIDO, campo="dados", rotulo="Dados bancários do favorecido",
    valores=("banco", "agencia", "conta", "pix"),
    origem="origem", confirmado_por="confirmado_por", confirmado_em="confirmado_em",
    documento_id="documento_id", em="extraido_em",
)

#: `atendimento_financiamento`'s house quintets — fgts/numero_proposta/
#: agente_financeiro (§C item 5) plus [H6, owner 2026-09-25] situacao: a
#: signed contrato de financiamento sets `situacao='aprovado'`, with
#: provenance like every other machine value.
CAMPOS_FINANCIAMENTO: tuple[CampoValidavel, ...] = (
    # A NOT NULL boolean's `false` is indistinguishable from "unset" — fill-
    # empty is judged by `fgts_origem IS NULL` (§B), and reject must reset
    # to `False`, never leave a NULL the column disallows.
    _quinteto(ENTIDADE_FINANCIAMENTO, "fgts", "Uso de FGTS", vazio=(("fgts", False),)),
    _quinteto(ENTIDADE_FINANCIAMENTO, "numero_proposta", "Número da proposta"),
    _quinteto(ENTIDADE_FINANCIAMENTO, "agente_financeiro", "Agente financeiro",
              valores=("agente_financeiro_id",), prefixo="agente_financeiro"),
    _quinteto(ENTIDADE_FINANCIAMENTO, "situacao", "Situação do financiamento"),
)

REGISTRO: tuple[CampoValidavel, ...] = (
    *CAMPOS_CLIENTE, *CAMPOS_IMOVEL, CAMPO_IMOVEL_DOCUMENTO, CAMPO_CERTIDAO, CAMPO_ATO_DETALHE,
    CAMPO_EMPRESA_DADOS, CAMPO_NEGOCIACAO_VALOR, CAMPO_PARCELA_VALOR, CAMPO_FAVORECIDO_DADOS,
    *CAMPOS_FINANCIAMENTO,
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
        # The CURRENT certidão of each tipo only — an older consulta's copy
        # (or one Crednet reading fanned into every consulta) is history,
        # not something this contract relies on.
        brutas = certidoes_svc.mais_recente_por_tipo(
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
        linha = vinculo_legal.linha_efetiva(client, org_id, im.codigo) or {}
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

    # [E1/E2] Each empresa's Cartão-CNPJ group provenance — a machine-
    # pending reading blocks generation exactly like an imóvel document.
    empresas_rows = _rows_por_id(client, org_id, TABELAS[ENTIDADE_EMPRESA], [e.id for e in dados.empresas])
    for e in dados.empresas:
        row = empresas_rows.get(e.id)
        if row is None:
            continue
        nome_pj = e.razao_social or e.cnpj
        coleta.alvos.append(Alvo((CAMPO_EMPRESA_DADOS,), e.id, row, f"Empresa {nome_pj}"))

    # [S2b §E4] The deal's own provenance-tracked rows — negociação
    # (valor_negociado) and financiamento (fgts/numero_proposta/
    # agente_financeiro/situacao) are ONE row per atendimento; `None`
    # (never fetched) for a synthetic fixture with no `atendimento_id`
    # (`dados.py`'s own docstring on the field).
    if dados.atendimento_id:
        neg_rows = (
            table_reads.table(client, TABELAS[ENTIDADE_NEGOCIACAO])
            .select("*").eq("org_id", str(org_id)).eq("atendimento_id", dados.atendimento_id)
            .limit(1).execute()
        ).data or []
        if neg_rows:
            coleta.alvos.append(
                Alvo((CAMPO_NEGOCIACAO_VALOR,), dados.atendimento_id, neg_rows[0], "Negociação")
            )

        fin_rows = (
            table_reads.table(client, TABELAS[ENTIDADE_FINANCIAMENTO])
            .select("*").eq("org_id", str(org_id)).eq("atendimento_id", dados.atendimento_id)
            .limit(1).execute()
        ).data or []
        if fin_rows:
            coleta.alvos.append(
                Alvo(CAMPOS_FINANCIAMENTO, dados.atendimento_id, fin_rows[0], "Financiamento")
            )

    # Each parcela's own `valor` ([H4]'s derived intermediária suggestion is
    # just another `origem='derivado'` reading of this same field — no
    # special-casing here) and each favorecido's bank data ([H5]).
    parcelas_rows = _rows_por_id(client, org_id, TABELAS[ENTIDADE_PARCELA], [p.id for p in dados.parcelas])
    for p in dados.parcelas:
        row = parcelas_rows.get(p.id)
        if row is None:
            continue
        coleta.alvos.append(Alvo((CAMPO_PARCELA_VALOR,), p.id, row, "Parcelas", rotulo_sufixo=p.tipo))

    favorecidos_rows = _rows_por_id(
        client, org_id, TABELAS[ENTIDADE_FAVORECIDO], [f.id for f in dados.favorecidos]
    )
    for f in dados.favorecidos:
        row = favorecidos_rows.get(f.id)
        if row is None:
            continue
        coleta.alvos.append(
            Alvo((CAMPO_FAVORECIDO_DADOS,), f.id, row, "Favorecidos", rotulo_sufixo=f.nome)
        )

    ativo_ids = [p.permuta_ativo_id for p in dados.permuta_imoveis]
    if ativo_ids:
        ativos = table_reads.in_batched_rows(client, "permuta_ativos", org_id, "id", ativo_ids)
        codigos = sorted({a["imovel_codigo"] for a in ativos if a.get("imovel_codigo")})
        for codigo in codigos:
            if im is not None and codigo == im.codigo:
                continue
            linha = vinculo_legal.linha_efetiva(client, org_id, codigo) or {}
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
    an imóvel field (154's `_documento_id` may point at either),
    `empresa_documentos` (167, §A.3 — the Cartão CNPJ store, S2a) for an
    empresa field, or `atendimento_documentos` (171, S2b §E4) for a
    negociação/parcela/financiamento/favorecido field. Each returned row is
    tagged `_tabela` with the table it was actually found in, so a caller
    can tell them apart without re-deriving it — `proveniencia.linhagem`
    turns that into an `Entrada` (`fontes.TABELA_ENTRADA`); this module
    stays free of that vocabulary."""
    ids_cliente, ids_imovel, ids_empresa, ids_atendimento = set(), set(), set(), set()
    for alvo, campo in pares:
        doc_id = alvo.row.get(campo.documento_id) if campo.documento_id else None
        if not doc_id:
            continue
        if campo.entidade == ENTIDADE_CLIENTE:
            ids_cliente.add(str(doc_id))
        elif campo.entidade == ENTIDADE_EMPRESA:
            ids_empresa.add(str(doc_id))
        elif campo.entidade in (ENTIDADE_NEGOCIACAO, ENTIDADE_PARCELA, ENTIDADE_FINANCIAMENTO, ENTIDADE_FAVORECIDO):
            ids_atendimento.add(str(doc_id))
        else:
            ids_imovel.add(str(doc_id))
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
    for did, r in _rows_por_id(client, org_id, "empresa_documentos", ids_empresa,
                               select="id,nome_original,tipo_documento,extracao_dados").items():
        fontes[did] = r | {"_nome": r.get("nome_original"), "_tabela": "empresa_documentos"}
    # 🔴 [S2b] `extracao_dados` is a 171 column (S2's parallel migration, not
    # yet in this schema) — selecting it would fail the mock's real-schema
    # validation. Nothing downstream reads it for THIS table either (unlike
    # `empresa_documentos`' select list, kept for parity with its own
    # consumers), so the projection stays to what already exists.
    for did, r in _rows_por_id(client, org_id, "atendimento_documentos", ids_atendimento,
                               select="id,nome_original,tipo_documento").items():
        fontes[did] = r | {"_nome": r.get("nome_original"), "_tabela": "atendimento_documentos"}
    return fontes


_CONFIANCA_IDENTIDADE = {c.item_key: c.coluna_confianca for c in CAMPOS_IDENTIDADE}


def _confianca(campo: CampoValidavel, alvo: Alvo, fonte: Optional[dict]) -> Optional[str]:
    if campo.confianca_coluna:
        return alvo.row.get(campo.confianca_coluna)
    if fonte is None:
        return None
    if campo.entidade == ENTIDADE_CLIENTE:
        # A document of ANOTHER cliente (the couple's certidão filed under the
        # titular) carries the titular's per-field confidence in its flat
        # columns — never this person's. Unknown beats wrong.
        dono = fonte.get("cliente_id")
        if dono is not None and str(dono) != alvo.entidade_id:
            return None
        coluna =_CONFIANCA_IDENTIDADE.get(campo.campo, f"extracao_{campo.campo}_confianca")
        return fonte.get(coluna)
    return fonte.get("extracao_confianca") if campo.campo == "numero_matricula" else None


def _corroboracao_cliente(
    client: Any, org_id: UUID, cliente_ids: list[str], clientes_rows: dict[str, dict],
) -> dict[tuple[str, str], bool]:
    """ONE batched query (`cliente_campo_conflitos` IN `cliente_ids`, every
    status — corroboration counts a SETTLED disagreement too, not only an
    open one) computing whether the value ALREADY on each cliente's field
    is corroborated by >=2 independent sources — the follow-up to BUILD
    item 2 (owner directive, 2026-09-29): a corroborated value should not
    need a human click even when its own source falls under the tier bar
    alone. Same evidence shape `campo_conflitos.historico_valores` reads
    for the LIVE resolver, computed here for the contract gate's own
    question instead ("is what's on file corroborated?", not "which side
    of a fresh disagreement wins?"). Bounded: one query for the WHOLE
    contract read, never one per field."""
    if not cliente_ids:
        return {}
    rows = table_reads.in_batched_rows(
        client, "cliente_campo_conflitos", org_id, "cliente_id", cliente_ids,
        # `id` is the pager's dedupe key (`order_col` default) — omitting it
        # makes iter_paged_rows raise on ANY card that has conflict rows.
        select="id,cliente_id,campo,valor_proposto,origem_proposto",
    )
    por_chave: dict[tuple[str, str], list[tuple[Any, Optional[str]]]] = {}
    for r in rows:
        chave_local = (str(r.get("cliente_id")), r.get("campo") or "")
        por_chave.setdefault(chave_local, []).append(
            (r.get("valor_proposto"), r.get("origem_proposto"))
        )

    resultado: dict[tuple[str, str], bool] = {}
    for (cid, campo_nome), propostas in por_chave.items():
        row = clientes_rows.get(cid)
        if row is None or not campo_nome:
            continue
        valor_atual = row.get(campo_nome)
        origem_atual = row.get(f"{campo_nome}_origem")
        origens = {origem_atual} if origem_atual else set()
        for valor, origem in propostas:
            if origem and _mesmo_valor(campo_nome, valor, valor_atual):
                origens.add(origem)
        resultado[(cid, campo_nome)] = len(origens) >= divergencia_resolucao.CORROBORACAO_MINIMA
    return resultado


def _corroboracao_documentos(
    client: Any, org_id: UUID, clientes_rows: dict[str, dict],
) -> dict[tuple[str, str], int]:
    """How many INDEPENDENT documents of each cliente carry the value already
    on file — read off the per-document extraction columns
    (`cliente_documentos.<CampoExtraido.coluna_valor>`: every reading stays
    on its own document row), so two agreeing documents clear a value with
    no conflict row and no migration. Owner, 2026-10-13: the extractor skips
    the EQUAL case (`identidade_extracao_service._processar` only acts on a
    disagreement), so `_corroboracao_cliente`'s conflict history never saw
    an agreement and two agreeing documents never cleared anything.

    Independent = a different `tipo_documento`: the same certidão uploaded
    twice is one source, not two. A two-person document's flat per-person
    columns name nobody (`divergencia_resolucao.DOCUMENTOS_DUAS_PESSOAS`), so
    they never corroborate a per-person field. ONE batched query per
    contract read."""
    if not clientes_rows:
        return {}
    docs = table_reads.in_batched_rows(
        client, "cliente_documentos", org_id, "cliente_id", sorted(clientes_rows)
    )
    tipos: dict[tuple[str, str], set[str]] = {}
    for d in docs:
        if d.get("deleted_at") or d.get("extracao_descartada_em"):
            continue
        cid = str(d.get("cliente_id"))
        row = clientes_rows.get(cid)
        if row is None:
            continue
        tipo = d.get("tipo_documento") or str(d.get("id"))
        for campo_nome, coluna in CAMPO_POR_ITEM.items():
            if not coluna or (
                tipo in divergencia_resolucao.DOCUMENTOS_DUAS_PESSOAS
                and campo_nome in divergencia_resolucao.CAMPOS_POR_PESSOA
            ):
                continue
            if _mesmo_valor(campo_nome, d.get(coluna), row.get(campo_nome)):
                tipos.setdefault((cid, campo_nome), set()).add(tipo)
    return {k: len(v) for k, v in tipos.items()}


def _corroboracoes(client: Any, org_id: UUID, coleta: Coleta) -> dict[tuple[str, str], int]:
    """`(cliente_id, campo) -> how many independent sources agree` with the
    value on file: the document count (`_corroboracao_documentos`), raised to
    the bar when the conflict history already corroborates it
    (`_corroboracao_cliente`)."""
    clientes_rows = {a.entidade_id: a.row for a in coleta.alvos if a.campos is CAMPOS_CLIENTE}
    por_conflito = _corroboracao_cliente(client, org_id, sorted(clientes_rows), clientes_rows)
    saida = _corroboracao_documentos(client, org_id, clientes_rows)
    for chave_local, ok in por_conflito.items():
        if ok:
            saida[chave_local] = max(
                saida.get(chave_local, 0), divergencia_resolucao.CORROBORACAO_MINIMA
            )
    return saida


def _corroborado(n: int) -> bool:
    return n >= divergencia_resolucao.CORROBORACAO_MINIMA


def _pendentes_brutos(
    client: Any, org_id: UUID, coleta: Coleta
) -> list[tuple[Alvo, CampoValidavel]]:
    corroboracao = _corroboracoes(client, org_id, coleta)
    return [
        (alvo, campo)
        for alvo in coleta.alvos
        for campo in alvo.campos
        if campo.pendente(
            alvo.row,
            corroborado=_corroborado(corroboracao.get((alvo.entidade_id, campo.campo), 0)),
        )
    ]


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


#: [S2b §E4 item 4, migration 171] `atendimento_campo_conflitos.campo` (§C
#: item 6's DOTTED vocabulary — disambiguating negociação/financiamento on
#: the SAME atendimento-keyed table) -> `(REGISTRO entidade, REGISTRO
#: campo)`. `parcela.<id>.valor` is dynamic (the id names its own row) and
#: is parsed in `_conflito_atendimento` instead of listed here.
_CONFLITO_CAMPO_ATENDIMENTO: dict[str, tuple[str, str]] = {
    "valor_negociado": (ENTIDADE_NEGOCIACAO, "valor_negociado"),
    "financiamento.fgts": (ENTIDADE_FINANCIAMENTO, "fgts"),
    "financiamento.numero_proposta": (ENTIDADE_FINANCIAMENTO, "numero_proposta"),
    "financiamento.agente_financeiro_id": (ENTIDADE_FINANCIAMENTO, "agente_financeiro"),
    # [H6, owner 2026-09-25] Not in the contract's original §C item 6 list
    # (written before H6) — added the same way as the other three.
    "financiamento.situacao": (ENTIDADE_FINANCIAMENTO, "situacao"),
}


def _conflito_atendimento(campo_bruto: str, atendimento_id: str) -> Optional[tuple[str, str, str]]:
    """`(entidade, entidade_id, REGISTRO campo)` for one stored
    `atendimento_campo_conflitos.campo`, or `None` for an unrecognized one
    (the same honest-skip `listar_conflitos`'s cliente branch takes for a
    campo outside `_CONFLITO_CAMPO_CLIENTE`)."""
    if campo_bruto.startswith("parcela.") and campo_bruto.endswith(".valor"):
        partes = campo_bruto.split(".")
        if len(partes) == 3:
            return ENTIDADE_PARCELA, partes[1], "valor"
        return None
    par = _CONFLITO_CAMPO_ATENDIMENTO.get(campo_bruto)
    if par is None:
        return None
    entidade, registro_campo = par
    return entidade, atendimento_id, registro_campo


def _comprovante_confirma_ficha_registrada(conflito: dict, cliente_row: Optional[dict]) -> bool:
    """A pending `endereco` conflict that, by the ficha-prevalece rule
    (owner decision, 2026-10-13), is no divergence: the stored address is
    the ficha cadastral's and the proposal is a comprovante agreeing on CEP
    + cidade/UF (a gate/condominium bill). Opened before the rule existed,
    it is not pending — the panel does not list it (the backfill,
    `identidade_extracao_service.backfill_resolver_conflitos_pendentes`,
    settles the row itself)."""
    if cliente_row is None:
        return False
    try:
        proposto = json.loads(conflito.get("valor_proposto") or "null")
    except ValueError:
        return False
    if not isinstance(proposto, dict):
        return False
    return endereco_comprovante_confirma_ficha(
        cliente_row, proposto, conflito.get("origem_proposto")
    )


def listar_conflitos(client: Any, org_id: UUID, dados: DadosContrato) -> list[dict]:
    """Open extraction CONFLICTS on this contract's data — a later reading
    disagreed with a value already set (D1: never a silent overwrite), and an
    admin has not decided it. Read-only here (deciding is the conflict
    screens' job), but they block generation exactly like a pending value:
    the value the contract would print is contested.

    - `cliente_campo_conflitos` (138) on every parte, for a contract field;
    - `imovel_campo_conflitos` (154, imóvel slice) on the imóvel + permuta
      imóveis — every field that table carries is an `imovel_dados` field the
      contract reads;
    - `empresa_campo_conflitos` (167, P0c contract §H6/item 4) on every
      required empresa (`dados.empresas`) — the shared writer S2a opens
      (`app.services.campo_conflitos.EMPRESA`);
    - `atendimento_campo_conflitos` (171, S2b §E4 item 4) on the deal itself
      — negociação, financiamento, and every parcela.
    """
    pessoas = {p.cliente_id: p for p in [*dados.compradores, *dados.vendedores]}
    saida: list[dict] = []
    if pessoas:
        rows = table_reads.in_batched_rows(
            client, "cliente_campo_conflitos", org_id, "cliente_id", sorted(pessoas)
        )
        pendentes_cliente = [
            r for r in rows
            if r.get("status") == "pendente" and _CONFLITO_CAMPO_CLIENTE.get(r.get("campo") or "")
        ]
        clientes_endereco = _rows_por_id(
            client, org_id, "clientes",
            {str(r["cliente_id"]) for r in pendentes_cliente if r.get("campo") == "endereco"},
        )
        for r in pendentes_cliente:
            registro = _CONFLITO_CAMPO_CLIENTE[r["campo"]]
            if registro == "endereco" and _comprovante_confirma_ficha_registrada(
                r, clientes_endereco.get(str(r["cliente_id"]))
            ):
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
                # Migration 291 — the on-file value is an OWNER CORRECTION
                # this reading contests: a warning, not a block.
                "protege_correcao": bool(r.get("protege_correcao")),
                "link": {"rota": "/configuracoes/pendencias", "rotulo": "Configurações → Pendências"},
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

    if dados.empresas:
        empresa_por_id = {e.id: e for e in dados.empresas}
        rows = table_reads.in_batched_rows(
            client, "empresa_campo_conflitos", org_id, "empresa_id", sorted(empresa_por_id)
        )
        for r in rows:
            if r.get("status") != "pendente":
                continue
            e = empresa_por_id.get(str(r["empresa_id"]))
            if e is None:
                continue
            campo = r.get("campo") or ""
            nome_pj = e.razao_social or e.cnpj
            saida.append({
                "id": str(r["id"]),
                "entidade": ENTIDADE_EMPRESA,
                "entidade_id": e.id,
                "campo": campo,
                "grupo": f"Empresa {nome_pj}",
                "rotulo": ROTULOS_EMPRESA_CAMPO.get(campo, campo),
                "valor_atual": _texto(r.get("valor_anterior")),
                "valor_proposto": _texto(r.get("valor_proposto")),
                "origem_proposto": r.get("origem_proposto"),
                "link": {"rota": "/configuracoes/pendencias", "rotulo": "Configurações → Pendências"},
            })

    if dados.atendimento_id:
        rows = (
            table_reads.table(client, "atendimento_campo_conflitos")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("atendimento_id", dados.atendimento_id)
            .eq("status", "pendente")
            .execute()
        ).data or []
        for r in rows:
            resolvido = _conflito_atendimento(r.get("campo") or "", dados.atendimento_id)
            if resolvido is None:
                continue
            entidade, entidade_id, registro_campo = resolvido
            campo_obj = _POR_ENTIDADE_CAMPO.get((entidade, registro_campo))
            rotulo = campo_obj.rotulo if campo_obj else registro_campo
            grupo = f"Parcela {entidade_id}" if entidade == ENTIDADE_PARCELA else "Negociação"
            saida.append({
                "id": str(r["id"]),
                "entidade": entidade,
                "entidade_id": entidade_id,
                "campo": registro_campo,
                "grupo": grupo,
                "rotulo": rotulo,
                "valor_atual": _texto(r.get("valor_anterior")),
                "valor_proposto": _texto(r.get("valor_proposto")),
                "origem_proposto": r.get("origem_proposto"),
                "link": {"rota": "/configuracoes/pendencias", "rotulo": "Configurações → Pendências"},
            })
    return saida


#: pt-BR line every protection conflict carries (owner order 2026-10-20).
MENSAGEM_CORRECAO_CONTESTADA = (
    "A leitura do documento sugere outro valor para um campo que você corrigiu."
)


def bloqueantes(conflitos: list[dict]) -> list[dict]:
    """The conflicts that REFUSE generation: every open one except a
    protection conflict (`protege_correcao`, migration 291) — there the
    owner's own correction is the value on file and stands until they
    decide, so the contract prints it; the reading is a warning
    (`correcoes_contestadas`), never a block (owner order 2026-10-20)."""
    return [c for c in conflitos if not c.get("protege_correcao")]


def correcoes_contestadas(conflitos: list[dict]) -> list[dict]:
    """The protection conflicts of `listar_conflitos` — each with the pt-BR
    `mensagem` the readiness report shows beside approve/reject."""
    return [
        {**c, "mensagem": MENSAGEM_CORRECAO_CONTESTADA}
        for c in conflitos
        if c.get("protege_correcao")
    ]


def listar_pendentes(
    client: Any, org_id: UUID, dados: DadosContrato, *, usuario_id: Optional[Any]
) -> list[dict]:
    """Every machine-pending contract-feeding value of the contract `dados`
    was loaded for — the GET answer and `gerar`'s precondition."""
    coleta = coletar(client, org_id, dados, usuario_id)
    brutos = _pendentes_brutos(client, org_id, coleta)
    fontes = documentos_de_origem(client, org_id, brutos)
    return [_item(alvo, campo, fontes, coleta.nomes) for alvo, campo in brutos]


def situacao(
    client: Any, org_id: UUID, dados: DadosContrato, *, usuario_id: Optional[Any]
) -> dict:
    """The GET answer: `{pendentes, conflitos, correcoes_contestadas}` —
    generation may proceed iff the first two are empty; the third is the
    owner-correction warnings (migration 291), which never block."""
    todos = listar_conflitos(client, org_id, dados)
    return {
        "pendentes": listar_pendentes(client, org_id, dados, usuario_id=usuario_id),
        "conflitos": bloqueantes(todos),
        "correcoes_contestadas": correcoes_contestadas(todos),
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
    # [S2b §E4 item 1] `atendimento_negociacao`/`atendimento_financiamento`
    # have no `id` of their own — one row per atendimento (`_seed_completo`'s
    # own shape, migration 171).
    if entidade in (ENTIDADE_NEGOCIACAO, ENTIDADE_FINANCIAMENTO):
        return query.eq("atendimento_id", entidade_id)
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
    brutos = _pendentes_brutos(client, org_id, coleta)
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
        _registrar(
            client, org_id, contrato_id, campo, alvo, item, valor_extraido, decisao,
            usuario_id=usuario_id, agora=agora,
        )

    return {"aplicadas": len(decisoes), **situacao(client, org_id, dados, usuario_id=usuario_id)}


def _registrar(
    client: Any,
    org_id: UUID,
    contrato_id: UUID,
    campo: CampoValidavel,
    alvo: Alvo,
    item: dict,
    valor_extraido: Optional[str],
    decisao: Decisao,
    *,
    usuario_id: Optional[Any],
    agora: str,
    revisao_versao_id: Optional[str] = None,
) -> None:
    """One append-only ledger row (migration 156). `revisao_versao_id`
    (migration 177) is written ONLY by the legal review — a per-field
    decision's insert stays byte-identical to the pre-177 one."""
    linha = {
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
    if revisao_versao_id is not None:
        linha["revisao_versao_id"] = revisao_versao_id
    table_reads.table(client, LEDGER).insert(linha).execute()


# ─── One final legal review per contract (owner decision 2026-09-30) ────────


def valor_sha256(campo: CampoValidavel, row: dict) -> str:
    """Fingerprint of the value a rendering printed — what the legal review
    compares against, so it never confirms a value the reviewer did not see.
    The value itself is never stored on the version (the PDF carries it)."""
    return hashlib.sha256((_valor_ledger(campo, row) or "").encode("utf-8")).hexdigest()


# ─── The legal-review LIST: one row per fact, with its value ────────────────
#
# Owner, 2026-10-13, on a 43-row "Aguardando revisão jurídica" panel: "trash".
# Every row showed a field name + file + "Confiança baixa" and never the value;
# the same fact repeated per spouse; copied/derived values counted as
# extracted; ~15 certidão rows (one Serasa file 3x); an unrelated company via
# an unconfirmed Crednet participação. The list below is what a reviewer can
# actually act on: the VALUE (masked when it is an identity number), where it
# came from, why it is listed, and the MEASURED precision of that source.

#: `secao` of a review item. Only `extraido` is "a machine read this and
#: nobody vouched for it"; the other two are shown collapsed and never count.
SECAO_EXTRAIDO = "extraido"
#: Copied or inferred — not a reading of a document of THIS person.
SECAO_DERIVADO = "derivado"
#: >= `CORROBORACAO_MINIMA` independent documents agree — not pending.
SECAO_CORROBORADO = "corroborado"

#: A source (`tipo_documento`, or an `origem` when there is no document row)
#: -> how the reviewer reads it.
ROTULO_FONTE: dict[str, str] = {
    "cnh": "CNH",
    "rg": "RG",
    "cin": "CIN",
    "cpf": "CPF",
    "certidao_casamento": "Certidão de casamento",
    "certidao_nascimento": "Certidão de nascimento",
    "comprovante_endereco": "Comprovante de endereço",
    "ficha_cadastral": "Ficha cadastral",
    "serasa_crednet": "Serasa Crednet",
    "cartao_cnpj": "Cartão CNPJ",
    "certidao_consulta": "Consulta de certidão",
    "matricula": "Matrícula",
    "sugestao": "Sugestão da matrícula",
    "sugerido": "Sugestão da matrícula",
    "ia": "Arquivo da certidão (leitura por IA)",
    ORIGEM_CONJUGE_DOMICILIO: "Endereço do cônjuge",
}

#: Within one person: identity, then civil status, then address, then contact.
_ORDEM_CAMPO_CLIENTE: dict[str, int] = {
    c: i for i, c in enumerate((
        "nome_oficial", "cpf", "rg", "rg_orgao_expedidor", "genero", "nacionalidade",
        "profissao",
        "estado_civil", "regime_bens", "data_casamento", "pacto_antenupcial_data",
        "pacto_antenupcial_tabelionato", "pacto_antenupcial_livro", "pacto_antenupcial_folha",
        "conjuge", "certidao_estado_civil_emitida_em",
        "endereco",
        "email",
    ))
}

#: A fact about the COUPLE, not about one spouse: read once off the same
#: certidão, it is listed once, named for both.
CAMPOS_DO_CASAL = frozenset({
    "estado_civil", "regime_bens", "data_casamento", "pacto_antenupcial_data",
    "pacto_antenupcial_tabelionato", "pacto_antenupcial_livro", "pacto_antenupcial_folha",
    "conjuge",
})

_ORIGENS_CERTIDAO_CIVIL = frozenset({"certidao_casamento", "certidao_nascimento"})

_ESTADO_CIVIL_ROTULO = {
    "solteiro": "Solteiro(a)", "casado": "Casado(a)", "divorciado": "Divorciado(a)",
    "viuvo": "Viúvo(a)", "uniao_estavel": "União estável",
    "separado_judicialmente": "Separado(a) judicialmente",
}

_COLUNA_ROTULO = {
    "numero": "nº", "emitida_em": "emitida em", "validade_ate": "válida até",
    "resultado": "resultado", "inscricao_imobiliaria": "inscrição",
    "razao_social": "razão social", "nome_fantasia": "nome fantasia",
    "natureza_juridica": "natureza jurídica", "data_abertura": "abertura",
    "situacao_cadastral": "situação", "data_situacao_cadastral": "desde",
    "motivo_situacao": "motivo", "uf": "UF", "banco": "banco", "agencia": "agência",
    "conta": "conta", "pix": "PIX",
}

_DATA_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:$|T)")


def _formatar(valor: Any) -> Optional[str]:
    """A stored value as a reviewer reads it — an ISO date as dd/mm/aaaa."""
    if valor is None:
        return None
    if isinstance(valor, (date, datetime)):
        valor = valor.isoformat()
    texto = valor if isinstance(valor, str) else _texto(valor) or ""
    texto = texto.strip()
    m = _DATA_ISO.match(texto)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return texto or None


def _mascarar_rg(valor: Any) -> Optional[str]:
    """Every alphanumeric but the last three hidden, punctuation kept —
    `**.***.111-1` (the CPF/CNPJ masks are the favorecidos' own)."""
    texto = str(valor or "").strip()
    if not texto:
        return None
    total = sum(ch.isalnum() for ch in texto)
    vistos, saida = 0, []
    for ch in texto:
        if ch.isalnum():
            vistos += 1
            saida.append(ch if vistos > total - 3 else "*")
        else:
            saida.append(ch)
    return "".join(saida)


def _endereco_texto(row: dict) -> Optional[str]:
    rua = ", ".join(
        p for p in (row.get("endereco_logradouro"), row.get("endereco_numero"),
                    row.get("endereco_complemento")) if preenchido(p)
    )
    cidade = "/".join(p for p in (row.get("endereco_cidade"), row.get("endereco_uf")) if preenchido(p))
    cep = re.sub(r"\D", "", str(row.get("endereco_cep") or ""))
    partes = [rua, row.get("endereco_bairro") or "", cidade,
              f"CEP {cep[:5]}-{cep[5:]}" if len(cep) == 8 else (f"CEP {cep}" if cep else "")]
    return " — ".join(p for p in partes if p) or None


def valor_revisao(
    campo: CampoValidavel, row: dict, nomes: dict[str, str]
) -> tuple[Optional[str], Optional[str]]:
    """`(valor, valor_mascarado)` of one review item as the reviewer reads it.
    `valor_mascarado` is set only for an identity number / bank data — the FE
    shows it until the user explicitly reveals (`Revelar`, the favorecidos
    pattern); `None` = nothing to hide."""
    if campo.entidade == ENTIDADE_CLIENTE:
        bruto = row.get(campo.valores[0])
        if campo.campo == "cpf":
            texto = _formatar(bruto)
            return texto, mascarar_documento(bruto) or _mascarar_rg(bruto)
        if campo.campo == "rg":
            texto = _formatar(bruto)
            return texto, _mascarar_rg(bruto)
        if campo.campo == "endereco":
            return _endereco_texto(row), None
        if campo.campo == "conjuge":
            alvo = row.get("conjuge_cliente_id")
            if not alvo:
                return None, None
            proprio = row.get("nome_oficial") or row.get("nome")
            outro = nomes.get(str(alvo), str(alvo))
            return (f"{proprio} e {outro}" if proprio else outro), None
        if campo.campo == "estado_civil":
            return _ESTADO_CIVIL_ROTULO.get(str(bruto), _formatar(bruto)), None
        if campo.campo == "regime_bens":
            return REGIME_EXTENSO.get(str(bruto), _formatar(bruto)), None
        return _formatar(bruto), None
    if campo.entidade == ENTIDADE_FAVORECIDO:
        claro = " · ".join(
            f"{_COLUNA_ROTULO.get(c, c)} {_formatar(row.get(c))}"
            for c in campo.valores if preenchido(row.get(c))
        ) or None
        mascarado = " · ".join(
            f"{_COLUNA_ROTULO.get(c, c)} "
            + (mascarar_conta(row.get(c)) if c in ("conta", "pix") else _formatar(row.get(c)) or "")
            for c in campo.valores if preenchido(row.get(c)) and c != "agencia"
        ) or None
        return claro, mascarado
    if campo.entidade == ENTIDADE_ATO_DETALHE:
        partes = []
        if row.get("data_registro"):
            partes.append(f"registro em {_formatar(row['data_registro'])}")
        nomes_t = [t.get("nome") for t in row.get("transmitentes") or [] if t.get("nome")]
        if nomes_t:
            partes.append("transmitentes: " + ", ".join(nomes_t))
        return " · ".join(partes) or None, None
    if len(campo.valores) > 1 and campo.campo not in ("titulo_aquisitivo", "onus_fonte"):
        return " · ".join(
            f"{_COLUNA_ROTULO.get(c, c.replace('_', ' '))} {_formatar(row.get(c))}"
            for c in campo.valores if preenchido(row.get(c))
        ) or None, None
    return _formatar(valor_exibicao(campo, row, nomes)), None


def precisao_texto(campo: CampoValidavel, origem: Optional[str]) -> str:
    """The MEASURED precision of this source for this field
    (`divergencia_resolucao.PRECISAO`, with its sample size) — never a
    document's own confidence, which on a spouse's row was the titular's."""
    p = (
        divergencia_resolucao.precisao_de(campo.campo, origem)
        if campo.entidade == ENTIDADE_CLIENTE
        else None
    )
    if p is None:
        return "sem medição"
    return f"precisão medida {round(p.precisao * 100)}% ({p.n} {'contrato' if p.n == 1 else 'contratos'})"


def _derivado_marcado(campo: str, row: dict, fonte: Optional[dict]) -> bool:
    """The seed parsers' explicit `derivado=True` (a parallel slice), however
    it lands: on the cliente row (`<campo>_derivado`) or on the document's
    extraction columns (`extracao_<campo>_derivado`)."""
    fonte = fonte or {}
    return bool(
        row.get(f"{campo}_derivado")
        or fonte.get(f"extracao_{campo}_derivado")
        or fonte.get(f"{campo}_derivado")
    )


def _motivo_derivado(campo: CampoValidavel, row: dict, fonte: Optional[dict]) -> Optional[str]:
    """Why a machine value is NOT a reading of a document of this person
    (shown under "Derivados (conferir)", never counted as extracted), or
    `None` for a real extraction."""
    if campo.entidade != ENTIDADE_CLIENTE:
        return None
    origem = row.get(campo.origem)
    if campo.campo == "endereco" and origem == ORIGEM_CONJUGE_DOMICILIO:
        return "Copiado do endereço do cônjuge (mesmo domicílio) — não foi lido de um documento desta pessoa."
    if campo.campo == "conjuge":
        return "Vínculo entre os cônjuges, tirado da certidão — não é um dado extraído."
    if _derivado_marcado(campo.campo, row, fonte):
        return "Deduzido do texto do documento — não está escrito nele."
    if (
        campo.campo == "genero"
        and origem in _ORIGENS_CERTIDAO_CIVIL
        and divergencia_resolucao.confianca_baixa((fonte or {}).get("extracao_genero_confianca"))
    ):
        return "Inferido pela concordância gramatical da certidão — não está escrito nela."
    return None


def _motivo_extraido(campo: CampoValidavel) -> str:
    if campo.entidade == ENTIDADE_CERTIDAO:
        return "Número, data e resultado lidos por IA do arquivo — confira no documento."
    return "Lido automaticamente do documento e ainda não confirmado por ninguém."


def _rotulo_fonte(campo: CampoValidavel, alvo: Alvo, origem: Optional[str], fonte: Optional[dict]) -> Optional[str]:
    if campo.entidade == ENTIDADE_CERTIDAO:
        tipo = "serasa_crednet" if alvo.row.get("fonte_cliente_documento_id") else origem
    elif campo.entidade == ENTIDADE_EMPRESA or origem == ORIGEM_CONJUGE_DOMICILIO:
        # The empresa's `dados_documento_id` may point at a Crednet in
        # `cliente_documentos`; a copied address points at the OTHER
        # spouse's comprovante — the origem is the honest source name.
        tipo = origem
    else:
        tipo = (fonte or {}).get("tipo_documento") or origem
    if not tipo:
        return None
    return ROTULO_FONTE.get(tipo, tipo.replace("_", " "))


@dataclass
class _Candidato:
    alvo: Alvo
    campo: CampoValidavel
    posicao: int
    item: dict


def _item_revisao(
    alvo: Alvo, campo: CampoValidavel, n_corroboracao: int,
    fontes: dict[str, dict], nomes: dict[str, str],
) -> dict:
    base = _item(alvo, campo, fontes, nomes)
    fonte = fontes.get(base["fonte_documento_id"] or "")
    motivo_derivado = _motivo_derivado(campo, alvo.row, fonte)
    if _corroborado(n_corroboracao):
        secao, motivo = SECAO_CORROBORADO, f"Confirmado por {n_corroboracao} documentos independentes."
    elif motivo_derivado:
        secao, motivo = SECAO_DERIVADO, motivo_derivado
    else:
        secao, motivo = SECAO_EXTRAIDO, _motivo_extraido(campo)
    valor, mascarado = valor_revisao(campo, alvo.row, nomes)
    return {
        **base,
        "valor": valor,
        "valor_mascarado": mascarado,
        "valor_sha256": valor_sha256(campo, alvo.row),
        "secao": secao,
        "motivo": motivo,
        "precisao": precisao_texto(campo, base["origem"]),
        "fonte_tipo": _rotulo_fonte(campo, alvo, base["origem"], fonte),
        "n_documentos": n_corroboracao if _corroborado(n_corroboracao) else None,
        "agrupadas": [],
    }


def _nome_curto(alvo: Alvo) -> str:
    return alvo.row.get("nome_oficial") or alvo.row.get("nome") or alvo.grupo


def _absorver(dono: _Candidato, outro: _Candidato) -> None:
    dono.item["agrupadas"].append(
        {"chave": outro.item["chave"], "valor_sha256": outro.item["valor_sha256"]}
    )


def _agrupar(candidatos: list[_Candidato]) -> list[dict]:
    """One row per FACT, in reading order.

    1. A couple fact (`CAMPOS_DO_CASAL`) both spouses carry with the same
       value off the same certidão — or the mutual cônjuge link — is ONE row,
       labelled with both names; the spouse's `chave` rides in `agrupadas`
       (the approval confirms both rows).
    2. Any other `(campo, valor_sha256, fonte_documento_id, secao)` repeat across
       entities folds into its first occurrence.
    3. Order: person/entity in the contract's own order, then identity →
       civil status → address → contact within a person."""
    por_cliente: dict[tuple[str, str], _Candidato] = {
        (c.alvo.entidade_id, c.campo.campo): c
        for c in candidatos if c.campo.entidade == ENTIDADE_CLIENTE
    }
    absorvidos: set[int] = set()
    for c in candidatos:
        if id(c) in absorvidos or c.campo.entidade != ENTIDADE_CLIENTE:
            continue
        if c.campo.campo not in CAMPOS_DO_CASAL:
            continue
        conjuge_id = c.alvo.row.get("conjuge_cliente_id")
        par = por_cliente.get((str(conjuge_id), c.campo.campo)) if conjuge_id else None
        if par is None or par is c or id(par) in absorvidos:
            continue
        if c.campo.campo == "conjuge":
            mesmo_fato = str(par.alvo.row.get("conjuge_cliente_id")) == c.alvo.entidade_id
        else:
            mesmo_fato = c.item["valor_sha256"] == par.item["valor_sha256"] and (
                c.item["fonte_documento_id"] == par.item["fonte_documento_id"]
                or c.item["origem"] == par.item["origem"] == "certidao_casamento"
            )
        if not mesmo_fato:
            continue
        _absorver(c, par)
        absorvidos.add(id(par))
        c.item["grupo"] = f"Casal — {_nome_curto(c.alvo)} e {_nome_curto(par.alvo)}"

    vistos: dict[tuple[str, str, str, str], _Candidato] = {}
    for c in candidatos:
        if id(c) in absorvidos or not c.item["fonte_documento_id"]:
            continue
        # Same `secao` too: the spouse's COPY of an address (derivado) is
        # not folded into the reading it was copied from (extraído).
        chave_fato = (
            c.campo.campo, c.item["valor_sha256"], c.item["fonte_documento_id"], c.item["secao"]
        )
        primeiro = vistos.get(chave_fato)
        if primeiro is None:
            vistos[chave_fato] = c
            continue
        _absorver(primeiro, c)
        absorvidos.add(id(c))
        if c.item["grupo"] not in primeiro.item["grupo"]:
            primeiro.item["grupo"] = f"{primeiro.item['grupo']} e {c.item['grupo']}"

    restantes = [c for c in candidatos if id(c) not in absorvidos]
    restantes.sort(key=lambda c: (c.posicao, _ORDEM_CAMPO_CLIENTE.get(c.campo.campo, 99)))
    return [c.item for c in restantes]


def pendentes_para_revisao(
    client: Any, org_id: UUID, dados: DadosContrato, *, usuario_id: Optional[Any]
) -> list[dict]:
    """`Politica.revisao_final_unica`'s replacement for `exigir_sem_pendentes`.

    OPEN CONFLICTS STILL REFUSE (409 `EXTRACAO_PENDENTE_VALIDACAO`, with an
    empty `pendentes`): two readings disagree and the system cannot tell
    which one to print — the exception a human exists for. Machine values
    nobody vouched for do NOT refuse: they are returned for `gerar` to
    record on the version it renders, where the one contract-level review
    confirms them (`confirmar_por_revisao`).

    Each item carries its display `valor` (+ `valor_mascarado`), `secao`
    (`extraido` | `derivado` | `corroborado`), a `motivo` line, the measured
    `precisao`, `fonte_tipo`, and `agrupadas` (the other rows the same fact
    lives on) — one row per fact, see `_agrupar`. A `corroborado` value is
    listed for transparency but is NOT pending (`_pendentes_brutos` skips
    it), so the approval leaves it as it is."""
    conflitos = bloqueantes(listar_conflitos(client, org_id, dados))
    if conflitos:
        raise ExtracaoPendenteValidacao([], conflitos)
    coleta = coletar(client, org_id, dados, usuario_id)
    corroboracao = _corroboracoes(client, org_id, coleta)
    pares = [
        (posicao, alvo, campo)
        for posicao, alvo in enumerate(coleta.alvos)
        for campo in alvo.campos
        # Machine, unconfirmed, filled, below the tier bar — corroboration
        # is judged below, so a corroborated value is still SHOWN.
        if campo.pendente(alvo.row)
    ]
    fontes = documentos_de_origem(client, org_id, [(a, c) for _, a, c in pares])
    candidatos = [
        _Candidato(
            alvo, campo, posicao,
            _item_revisao(
                alvo, campo, corroboracao.get((alvo.entidade_id, campo.campo), 0)
                if campo.entidade == ENTIDADE_CLIENTE else 0,
                fontes, coleta.nomes,
            ),
        )
        for posicao, alvo, campo in pares
    ]
    return _agrupar(candidatos)


def _nomes_auxiliares(client: Any, org_id: UUID, linhas: list[tuple[str, dict]]) -> dict[str, str]:
    """The names `valor_exibicao` renders pointers with — a cônjuge's name
    and a matrícula act's label ("R.1") — for rows read outside `coletar`."""
    nomes: dict[str, str] = {}
    conjuges = {str(r["conjuge_cliente_id"]) for e, r in linhas
                if e == ENTIDADE_CLIENTE and r.get("conjuge_cliente_id")}
    for cid, r in _rows_por_id(client, org_id, "clientes", conjuges, select="id,nome,nome_oficial").items():
        nomes[cid] = r.get("nome_oficial") or r.get("nome") or cid
    atos: set[str] = set()
    for e, r in linhas:
        if e != ENTIDADE_IMOVEL:
            continue
        if r.get("titulo_aquisitivo_ato_id"):
            atos.add(str(r["titulo_aquisitivo_ato_id"]))
        for a in r.get("onus_fonte_atos") or []:
            if isinstance(a, dict) and a.get("ato_id"):
                atos.add(str(a["ato_id"]))
    for aid, ato in _rows_por_id(client, org_id, "matricula_atos", atos, select="id,kind,numero").items():
        nomes[aid] = (
            f"{ato['kind']}.{ato['numero']}" if ato.get("numero") is not None else str(ato.get("kind"))
        )
    return nomes


def valores_ao_vivo(client: Any, org_id: UUID, campos: list[dict]) -> dict[str, dict]:
    """`chave -> {valor, valor_mascarado, valor_confere}` for the recorded
    review items of a version (`revisao_juridica_campos`), read off the live
    rows at listing time.

    🔴 The version never stores the value (`contratos_service.
    CAMPOS_REVISAO_CHAVES`: a JSON copy of a CPF on every version row is a
    second place LGPD has to find it) — so the value is read where it lives,
    and `valor_confere` says whether it is still the value the version
    printed (`valor_sha256`). A recorded item whose entity is not a
    registry table (an aditivo's wording) is simply absent from the answer.
    Bounded: one batched read per entity table."""
    ids: dict[str, set[str]] = {}
    for c in campos:
        entidade, entidade_id = c.get("entidade"), c.get("entidade_id")
        if entidade in TABELAS and entidade_id and (entidade, c.get("campo")) in _POR_ENTIDADE_CAMPO:
            ids.setdefault(entidade, set()).add(str(entidade_id))
    linhas: dict[tuple[str, str], dict] = {}
    for entidade, chaves_ent in ids.items():
        if entidade == ENTIDADE_IMOVEL:
            # The SAME effective row `coletar` fingerprinted.
            for codigo in sorted(chaves_ent):
                linha = vinculo_legal.linha_efetiva(client, org_id, codigo)
                if linha:
                    linhas[(entidade, codigo)] = linha
            continue
        coluna = "atendimento_id" if entidade in (ENTIDADE_NEGOCIACAO, ENTIDADE_FINANCIAMENTO) else "id"
        select = certidoes_svc.RESULTADO_COLUNAS_SEM_TEXTO if entidade == ENTIDADE_CERTIDAO else "*"
        for r in table_reads.in_batched_rows(
            client, TABELAS[entidade], org_id, coluna, sorted(chaves_ent),
            select=select, order_col=coluna,
        ):
            linhas[(entidade, str(r[coluna]))] = r
    nomes = _nomes_auxiliares(client, org_id, [(e, r) for (e, _), r in linhas.items()])
    saida: dict[str, dict] = {}
    for c in campos:
        campo = _POR_ENTIDADE_CAMPO.get((c.get("entidade"), c.get("campo")))
        row = linhas.get((c.get("entidade"), str(c.get("entidade_id"))))
        if campo is None or row is None:
            continue
        valor, mascarado = valor_revisao(campo, row, nomes)
        saida[c["chave"]] = {
            "valor": valor,
            "valor_mascarado": mascarado,
            "valor_confere": valor_sha256(campo, row) == c.get("valor_sha256"),
        }
    return saida


def _registrados_expandidos(registrados: list[dict]) -> list[dict]:
    """Every row a recorded item vouches for — the item itself plus the rows
    the same fact was folded from (`agrupadas`: the spouse's copy of a couple
    fact). The approval confirms all of them."""
    saida: list[dict] = []
    for r in registrados:
        saida.append(r)
        saida.extend(a for a in r.get("agrupadas") or [] if a.get("chave"))
    return saida


class RevisaoJuridicaDesatualizada(AppException):
    """A value the version recorded changed (or stopped feeding the
    contract) after it was rendered — the PDF the reviewer read no longer
    matches the data. Nothing was written; generate a new version."""

    def __init__(self, chaves: list[str]) -> None:
        super().__init__(
            code="REVISAO_JURIDICA_VERSAO_DESATUALIZADA",
            message=(
                "Os dados do contrato mudaram depois que esta versão foi gerada. "
                "Gere uma nova versão e revise-a."
            ),
            status_code=409,
            details={"chaves": chaves},
        )


def confirmar_por_revisao(
    client: Any,
    org_id: UUID,
    dados: DadosContrato,
    contrato_id: UUID,
    versao_id: str,
    registrados: list[dict],
    *,
    usuario_id: Optional[Any],
) -> int:
    """Confirm, on its own row, every value `registrados` (the version's
    `revisao_juridica_campos`) names that is STILL machine-pending — the
    same `_patch_aceite` a per-field accept writes, plus one ledger row
    tagged with the version. Returns how many were confirmed.

    Refuses FIRST, writing nothing, when any recorded value no longer holds
    the value the version printed (`valor_sha256`) or no longer feeds this
    contract (`RevisaoJuridicaDesatualizada`). A recorded value that is no
    longer pending but unchanged (confirmed meanwhile, or auto-validated) is
    simply skipped — nothing left to vouch for. An item's `agrupadas` (the
    spouse's copy of a couple fact) are confirmed — and checked — the same
    way as the item itself."""
    registrados = _registrados_expandidos(registrados)
    coleta = coletar(client, org_id, dados, usuario_id)
    todos = {
        chave(c.entidade, a.entidade_id, c.campo): (a, c)
        for a in coleta.alvos
        for c in a.campos
    }
    desatualizadas = [
        r["chave"]
        for r in registrados
        if r.get("chave") not in todos
        or valor_sha256(todos[r["chave"]][1], todos[r["chave"]][0].row) != r.get("valor_sha256")
    ]
    if desatualizadas:
        raise RevisaoJuridicaDesatualizada(desatualizadas)

    pendentes = {
        chave(c.entidade, a.entidade_id, c.campo)
        for a, c in _pendentes_brutos(client, org_id, coleta)
    }
    alvos = [todos[r["chave"]] for r in registrados if r["chave"] in pendentes]
    fontes = documentos_de_origem(client, org_id, alvos)
    agora = _now()
    for alvo, campo in alvos:
        item = _item(alvo, campo, fontes, coleta.nomes)
        valor = _valor_ledger(campo, alvo.row)
        _gravar(client, org_id, campo.entidade, alvo.entidade_id, alvo.row,
                _patch_aceite(campo, alvo.row, usuario_id, agora), agora)
        _registrar(
            client, org_id, contrato_id, campo, alvo, item, valor, "aceito",
            usuario_id=usuario_id, agora=agora, revisao_versao_id=str(versao_id),
        )
    return len(alvos)


__all__ = [
    "Alvo",
    "MENSAGEM_CORRECAO_CONTESTADA",
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
    "RevisaoJuridicaDesatualizada",
    "SECAO_CORROBORADO",
    "SECAO_DERIVADO",
    "SECAO_EXTRAIDO",
    "ValidacaoDesatualizada",
    "bloqueantes",
    "chave",
    "coletar",
    "confirmar_por_revisao",
    "correcoes_contestadas",
    "decidir",
    "documentos_de_origem",
    "exigir_sem_pendentes",
    "listar_conflitos",
    "listar_pendentes",
    "pendentes_para_revisao",
    "preenchido",
    "situacao",
    "valor_exibicao",
    "valor_revisao",
    "valor_sha256",
    "valores_ao_vivo",
]
