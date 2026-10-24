"""The contract SPECIFICATION catalogue — what kind of contract this deal is.

Owner direction (2026-10-24): the contract's specifications are SELECTABLE in
the UI and they scope which data the readiness asks for. Real deals have no
reference contract to copy from, so "what this contract is" must be a stated
choice, not only something inferred from whatever data happens to be typed.

Until now the shape was derived from the data (`derivacao.derivar_switches`
→ `derivacao.modelo_derivado`). That derivation stays — `sugerir` is its
successor: the same switches in, a richer answer out (the facets, not just
one `modelo` label). `derivacao.modelo_derivado` is computed from it, so the
label and the facets can never disagree.

House style: constant tables in code (like `numeracao.CLAUSULA_CONDICIONAL`
and `contratos_service.MODELOS`), pure functions, no IO. The stored
selection (`atendimento_contratos.especificacoes`, migration 308) carries
`CATALOGO_VERSAO`, so a later catalogue change can tell a selection made
against an older vocabulary from a current one.

AXES
----
- ``base``          — ``compra_venda``: every contract here is a compra e
                      venda; always selected.
- ``pagamento``     — ``a_vista`` · ``sinal_saldo`` · ``financiamento_bancario``
                      · ``fgts`` · ``parcelas_diretas`` · ``intermediarias``.
                      MULTI-select: a financed deal is sinal + financiamento
                      (+ fgts), possibly with intermediárias; the exclusive
                      pairs are declared (`exclusiva_com`).
- ``confissao``     — ``confissao_divida`` (requires ``parcelas_diretas``).
- ``permuta``       — ``permuta``.
- ``intermediacao`` — ``intermediacao``.

REQUISITOS
----------
`requisitos` are readiness ``falta`` keys (`derivacao.Avaliacao.falta`'s
`campo`) — the exact keys `derivacao` already emits, inventoried from it. A
``*`` stands for exactly ONE dotted segment (an id: a parcela, a favorecido,
an intermediário, a permuta ativo). How readiness uses them
(`derivacao.Avaliacao.pede`, the gate every falta passes): a falta key no
specification GOVERNS (`governa`) is always asked — parties, certidões, the
imóvel's registry data are about every contract; a governed key is asked
only when a selected specification requires it (`exige`). No stored
selection = legacy mode: no scope at all.

🔴 PENDING OWNER DECISION — G1. An à vista deal with NO sinal has no base for
the multa rescisória (in the signed corpus the sinal is that base). It is
represented as the explicit requisito `negociacao.multa_rescisoria_base` on
``a_vista`` (dispensed when ``sinal_saldo`` is also selected — the sinal is
the base then). No value, rule or default is invented here: the key exists
so the decision has a named destination (`PENDENTES_DECISAO`); `derivacao`
asks it as a falta labelled "aguardando decisão do escritório"
(`derivacao.ROTULO_PENDENTE_DECISAO`) whenever a selection requires it —
an à vista selection without sinal is never ready until the owner decides.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

#: Bumped whenever a key is added/removed/re-meant, so a stored selection
#: (`atendimento_contratos.especificacoes_versao`) states which vocabulary
#: it was made against.
CATALOGO_VERSAO = 1

#: The `modelo` labels (`atendimento_contratos.modelo`) — the single home of
#: these three strings; `derivacao.MODELO_*` re-export them.
MODELO_COMPRA_VENDA = "compra_venda"
MODELO_A_VISTA = "compra_venda_a_vista"
MODELO_PERMUTA = "compra_venda_permuta"

EIXOS: tuple[str, ...] = ("base", "pagamento", "confissao", "permuta", "intermediacao")

#: Requisito keys that name an OPEN owner question — no readiness rule may
#: invent their value; see the module docstring.
PENDENTES_DECISAO: Mapping[str, str] = {
    "negociacao.multa_rescisoria_base": (
        "G1 (owner, aberta): base da multa rescisória num contrato à vista sem sinal."
    ),
}


@dataclass(frozen=True)
class Especificacao:
    chave: str
    rotulo: str
    eixo: str
    #: `derivacao.derivar_switches` keys whose TRUE value suggests this
    #: specification (`sugerir`); empty = never inferred from data alone.
    switches_implicados: tuple[str, ...]
    #: Readiness `falta` keys this specification asks for (see module doc).
    requisitos: tuple[str, ...]
    #: `numeracao.ORDEM_CLAUSULAS` keys this specification brings in.
    clausulas: tuple[str, ...]
    #: Specifications that must ALSO be selected.
    requer: tuple[str, ...] = ()
    #: Specifications that may NOT be selected together with this one
    #: (declared on both sides; a test pins the symmetry).
    exclusiva_com: tuple[str, ...] = ()
    #: Requisitos of OTHER specifications this one makes unnecessary.
    dispensa: tuple[str, ...] = ()


_SEM_FINANCIAR = ("financiamento_bancario", "fgts", "parcelas_diretas", "confissao_divida")

#: Every switch that means "the deal has payment parcelas" — the legacy
#: readiness demands a sinal on EVERY such deal (`negociacao.parcela_sinal`),
#: so the legacy shape is always sinal + saldo.
_HA_PARCELAS = ("a_vista", "tem_financiamento", "tem_parcelas_diretas", "tem_intermediaria", "tem_permuta")

#: Suggested from the legacy shape but NOT witnessed by the switches, so never
#: reported as a data conflict (`conflitos`).
_SO_SUGESTAO = frozenset({"sinal_saldo"})

CATALOGO: tuple[Especificacao, ...] = (
    Especificacao(
        chave="compra_venda",
        rotulo="Compra e venda",
        eixo="base",
        switches_implicados=(),
        requisitos=(
            "negociacao.imovel",
            "negociacao.valor_negociado",
            "negociacao.parcelas",
            "negociacao.parcela.*.valor",
            "negociacao.parcela.*.momento",
            "negociacao.parcela.*.forma_pagamento",
            "negociacao.parcela.*.favorecido",
            "negociacao.favorecido.*.conta",
            "negociacao.favorecido.*.cpf_cnpj",
            "negociacao.favorecido.*.banco",
            "negociacao.posse_marco",
            "negociacao.posse_prazo_dias",
            "negociacao.posse_data",
            "negociacao.foro_comarca",
            "partes.vendedores",
            "partes.compradores",
        ),
        clausulas=(
            "objeto", "preco", "certidoes", "onus", "posse", "tributos", "irretratabilidade",
            "mora", "vistoria", "registro", "resolutiva", "foro",
        ),
    ),
    Especificacao(
        chave="a_vista",
        rotulo="À vista (recursos próprios)",
        eixo="pagamento",
        switches_implicados=("a_vista",),
        requisitos=("negociacao.multa_rescisoria_base",),
        clausulas=(),
        exclusiva_com=_SEM_FINANCIAR,
    ),
    Especificacao(
        chave="sinal_saldo",
        rotulo="Sinal + saldo",
        eixo="pagamento",
        switches_implicados=_HA_PARCELAS,
        requisitos=("negociacao.parcela_sinal",),
        clausulas=(),
        dispensa=("negociacao.multa_rescisoria_base",),
    ),
    Especificacao(
        chave="financiamento_bancario",
        rotulo="Financiamento bancário",
        eixo="pagamento",
        switches_implicados=("tem_financiamento",),
        requisitos=("financiamento", "financiamento.situacao"),
        clausulas=(),
        exclusiva_com=("a_vista",),
    ),
    Especificacao(
        chave="fgts",
        rotulo="Uso de FGTS",
        eixo="pagamento",
        switches_implicados=("tem_fgts",),
        requisitos=(),
        clausulas=(),
        requer=("financiamento_bancario",),
        exclusiva_com=("a_vista",),
    ),
    Especificacao(
        chave="parcelas_diretas",
        rotulo="Parcelas diretas ao vendedor",
        eixo="pagamento",
        switches_implicados=("tem_parcelas_diretas",),
        requisitos=(),
        clausulas=(),
        exclusiva_com=("a_vista",),
    ),
    Especificacao(
        chave="intermediarias",
        rotulo="Parcelas intermediárias",
        eixo="pagamento",
        switches_implicados=("tem_intermediaria",),
        requisitos=(),
        clausulas=(),
    ),
    Especificacao(
        chave="confissao_divida",
        rotulo="Confissão de dívida",
        eixo="confissao",
        switches_implicados=("tem_confissao",),
        requisitos=("negociacao.confissao_juros_am", "negociacao.parcela.*.vencimento"),
        clausulas=("confissao",),
        requer=("parcelas_diretas",),
        exclusiva_com=("a_vista",),
    ),
    Especificacao(
        chave="permuta",
        rotulo="Permuta",
        eixo="permuta",
        switches_implicados=("tem_permuta",),
        requisitos=(
            "negociacao.permuta_imoveis",
            "negociacao.parcela.*.permuta_imoveis",
            "matricula.permuta.*.atos",
            "negociacao.permuta.*.inscricao_municipal",
            "negociacao.permuta.*.matricula_numero",
            "negociacao.permuta.*.cartorio",
            "negociacao.permuta.*.logradouro",
            "negociacao.permuta.*.numero",
            "negociacao.permuta.*.cidade",
            "negociacao.permuta.*.endereco_registro_texto",
            "negociacao.permuta_posse_marco",
            "negociacao.permuta_posse_prazo_dias",
        ),
        clausulas=(),
    ),
    Especificacao(
        chave="intermediacao",
        rotulo="Intermediação (corretagem)",
        eixo="intermediacao",
        switches_implicados=("tem_intermediacao",),
        requisitos=(
            "negociacao.intermediario.*.creci",
            "negociacao.intermediario.*.tipo",
            "negociacao.intermediario.*.valor",
            "negociacao.intermediario.*.qualificacao",
            "negociacao.intermediario.*.favorecido",
            "negociacao.corretagem_contratantes",
            "negociacao.corretagem_parcelas_marco",
            "negociacao.pct_comissao",
        ),
        clausulas=("intermediacao",),
    ),
)

POR_CHAVE: Mapping[str, Especificacao] = {e.chave: e for e in CATALOGO}
CHAVES: tuple[str, ...] = tuple(POR_CHAVE)
BASE = "compra_venda"


def _ordenadas(chaves: Iterable[str]) -> tuple[str, ...]:
    conjunto = set(chaves)
    return tuple(c for c in CHAVES if c in conjunto)


def sugerir(switches: Mapping[str, bool]) -> list[str]:
    """The specifications the derived switches imply (catalogue order) — the
    successor of `derivacao.modelo_derivado`: same input, the facets instead
    of one label. A SUGGESTION: the operator's stored selection wins."""
    return [
        e.chave
        for e in CATALOGO
        if e.chave == BASE or any(switches.get(s) for s in e.switches_implicados)
    ]


def validar(especificacoes: Iterable[str]) -> tuple[str, ...]:
    """Refuse an incoherent selection with a ValueError naming the culprit
    (unknown key, repeated key, missing base, missing `requer`, an
    `exclusiva_com` pair). Returns the selection in catalogue order."""
    lista = list(especificacoes)
    desconhecidas = [c for c in lista if c not in POR_CHAVE]
    if desconhecidas:
        raise ValueError(f"especificação desconhecida: {desconhecidas[0]!r}")
    repetidas = sorted({c for c in lista if lista.count(c) > 1})
    if repetidas:
        raise ValueError(f"especificação repetida: {repetidas[0]!r}")
    if BASE not in lista:
        raise ValueError(f"especificação obrigatória ausente: {BASE!r}")
    selecao = set(lista)
    for chave in _ordenadas(selecao):
        e = POR_CHAVE[chave]
        for r in e.requer:
            if r not in selecao:
                raise ValueError(f"especificação {chave!r} requer {r!r}")
        for x in e.exclusiva_com:
            if x in selecao:
                raise ValueError(f"especificações exclusivas: {chave!r} e {x!r}")
    return _ordenadas(selecao)


def requisitos(especificacoes: Iterable[str]) -> frozenset[str]:
    """The readiness `falta` keys (patterns, see module doc) the selection
    asks for: the union of each specification's requisitos, minus what a
    selected specification dispenses."""
    selecao = validar(especificacoes)
    pedidos: set[str] = set()
    dispensados: set[str] = set()
    for chave in selecao:
        pedidos.update(POR_CHAVE[chave].requisitos)
        dispensados.update(POR_CHAVE[chave].dispensa)
    return frozenset(pedidos - dispensados)


def conflitos(especificacoes: Iterable[str], switches: Mapping[str, bool]) -> list[str]:
    """What the deal's DATA contradicts in a (valid) selection — messages,
    catalogue order. Absent data is never a conflict (that is a readiness
    `falta`); only data that is THERE and disagrees:

    - the data carries a facet the selection lacks (a financiamento parcela
      on a deal selected without ``financiamento_bancario``) — worded against
      the exclusive facet when that is the reason (``a_vista`` + financiamento);
    - the selection names a financing/direct facet but the data is a complete
      à vista shape (`switches['a_vista']`: parcelas exist and none is
      financiamento/direta) — e.g. ``fgts`` with no financiamento parcela.
    """
    selecao = set(validar(especificacoes))
    saida: list[str] = []
    for e in CATALOGO:
        # ``sinal_saldo``'s switches only witness "there are parcelas" (the
        # switches carry no sinal flag) — a G1 à vista deal with no sinal
        # must not read as contradicting an unselected ``sinal_saldo``.
        if e.chave in selecao or not e.switches_implicados or e.chave in _SO_SUGESTAO:
            continue
        if not any(switches.get(s) for s in e.switches_implicados):
            continue
        exclusoras = [x for x in e.exclusiva_com if x in selecao]
        if exclusoras:
            saida.append(
                f"Especificação '{POR_CHAVE[exclusoras[0]].rotulo}' selecionada, mas os dados "
                f"do negócio têm {e.rotulo.lower()}."
            )
        else:
            saida.append(
                f"Os dados do negócio têm {e.rotulo.lower()}, mas a especificação "
                f"'{e.rotulo}' não está selecionada."
            )
    if switches.get("a_vista"):
        for chave in _SEM_FINANCIAR:
            if chave in selecao:
                saida.append(
                    f"Especificação '{POR_CHAVE[chave].rotulo}' selecionada, mas as parcelas do "
                    "negócio não têm financiamento nem parcela direta."
                )
    return saida


def modelo_de(especificacoes: Iterable[str]) -> str:
    """The `modelo` label a selection implies — permuta wins, then à vista
    (paid with own resources: no financiamento, fgts or parcela direta, with
    or without a sinal), else plain compra e venda. Parity with
    `derivacao.modelo_derivado` is pinned per fixture variant."""
    selecao = set(validar(especificacoes))
    if "permuta" in selecao:
        return MODELO_PERMUTA
    if "a_vista" in selecao:
        return MODELO_A_VISTA
    return MODELO_COMPRA_VENDA


# ─── requisito-pattern matching (consumed by the readiness slice) ─────────

_TODOS_REQUISITOS: frozenset[str] = frozenset(r for e in CATALOGO for r in e.requisitos)


def _regex(padrao: str) -> re.Pattern[str]:
    return re.compile("^" + r"\.".join("[^.]+" if p == "*" else re.escape(p) for p in padrao.split(".")) + "$")


_REGEX: Mapping[str, re.Pattern[str]] = {p: _regex(p) for p in _TODOS_REQUISITOS}


def _casa(padrao: str, campo: str) -> bool:
    rx = _REGEX.get(padrao) or _regex(padrao)
    return bool(rx.match(campo))


def exige(requisitos_: Iterable[str], campo: str) -> bool:
    """Does a requisito set (from `requisitos`) ask for this falta key?"""
    return any(_casa(p, campo) for p in requisitos_)


def governa(campo: str) -> bool:
    """Is this falta key owned by SOME specification? An ungoverned key is
    about every contract and is always asked."""
    return exige(_TODOS_REQUISITOS, campo)


__all__ = [
    "BASE",
    "CATALOGO",
    "CATALOGO_VERSAO",
    "CHAVES",
    "EIXOS",
    "Especificacao",
    "MODELO_A_VISTA",
    "MODELO_COMPRA_VENDA",
    "MODELO_PERMUTA",
    "PENDENTES_DECISAO",
    "POR_CHAVE",
    "conflitos",
    "exige",
    "governa",
    "modelo_de",
    "requisitos",
    "sugerir",
    "validar",
]
