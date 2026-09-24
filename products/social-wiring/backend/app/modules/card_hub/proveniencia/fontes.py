"""The catalog: `tipo_documento -> Fonte`.

Source: `KNOWLEDGE-BASE/CONTEXT/PRODUCTS/social-wiring/
CONTRACT-FIELD-PROVENANCE-MAP.md` §0a's table, made executable. That table
stays the human-readable narrative (extra columns: "lands in", worked
example); this module is what code — and a test — can actually walk.

Two products call this catalog's `tipo_documento`s the same word for two
different tables (`social_wiring.cliente_documentos` vs.
`social_wiring.imovel_documentos`); `Fonte.dominio` says which.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from noctusai_lib.integrations.documents.capacidades import CAPACIDADES


class Entrada(str, Enum):
    """How a document that feeds a `Fonte` actually arrives.

    Distinct from `origem` (what gets WRITTEN to a provenance column once a
    reading lands) — this is the upload/entry CHANNEL, several of which may
    feed the same `tipo_documento`.
    """

    #: A Meta lead-gen form submission — structured fields, no file at all.
    LEAD_FORM = "lead_form"
    #: Uploaded by an operator on the card_hub `/clientes` card UI.
    CLIENTE_CARD_UPLOAD = "cliente_card_upload"
    #: Uploaded by the party itself through a self-serve panel/link.
    PARTE_PAINEL_UPLOAD = "parte_painel_upload"
    #: Uploaded by an operator on the imovel_hub `/imoveis` page.
    IMOVEL_PAGE_UPLOAD = "imovel_page_upload"
    #: Uploaded by an operator on an empresa's card (Cartão CNPJ).
    EMPRESA_CARD_UPLOAD = "empresa_card_upload"
    #: Uploaded through the dedicated `/matriculas` module.
    MATRICULAS = "matriculas"
    #: Mirrored from an external property-listing/"vista" source, not a
    #: card_hub or imovel_hub upload at all.
    VISTA_MIRROR = "vista_mirror"
    #: Pulled automatically by an API consulta bot (no human upload).
    CERTIDAO_ROBO = "certidao_robo"
    #: Typed directly by a human — no document at all.
    MANUAL = "manual"
    #: Computed from other already-stored data — no document, no human typing.
    DERIVADO = "derivado"


Dominio = Literal["cliente", "imovel", "empresa"]


@dataclass(frozen=True)
class Fonte:
    """One `tipo_documento`'s extraction contract.

    `campos` is the canonical (seed-vocabulary, see `capacidades.py`) field
    set this product ACTUALLY claims from this tipo — checked, not assumed,
    against `CAPACIDADES[tipo_documento]` (`test_fontes.py`). It may be
    narrower than what the same extractor produces for a RICHER document of
    the same family: `cpf` intentionally claims only `{"nome", "cpf"}`, even
    though `identidade_extracao_service._valores_lidos` does not (yet)
    type-gate its output per tipo — see that module's own scoped-improvement
    note. `campos` is empty for a tipo with no SEED-typed capability behind
    it (the imóvel CND/guia structured reads — an ad-hoc per-product LLM
    prompt, not a seed parser); `estrutura_extraivel` names that leg instead.
    """

    tipo_documento: str
    dominio: Dominio
    entradas: frozenset[Entrada]
    #: Dotted `module.attr` path to the function that reads this tipo.
    extrator: str
    #: `<campo>_origem` values this tipo's readings write. `{tipo_documento}`
    #: for the "quinteto" pattern (`validacao_extracao._quinteto`) — the
    #: house convention documented in `CONTRACT-FIELD-PROVENANCE-MAP.md`
    #: §0a's write-policy paragraph — or a product's own structured-read
    #: vocabulary (`imovel_hub.documentos_service.ORIGENS_ESTRUTURA`, mirrored
    #: here rather than imported to avoid a fontes.py <-> documentos_service
    #: import cycle: this module derives that module's `TIPOS_*`).
    origens: frozenset[str]
    #: Canonical fields this product claims from this tipo (⊆ `CAPACIDADES`).
    campos: frozenset[str] = field(default_factory=frozenset)
    #: The vision rung must read every page — the identity-document `TIPOS_
    #: LEITURA_INTEGRAL` concept. Meaningless (always `False`) off `dominio
    #: == "imovel"`.
    leitura_integral: bool = False
    #: Gets the imóvel structured read (migration 118, `imovel_hub.
    #: documentos_service.extrair_estrutura` / `CAMPOS_ESTRUTURA_POR_TIPO`).
    #: Meaningless (always `False`) off `dominio == "cliente"`.
    estrutura_extraivel: bool = False


#: `REGISTRO`/`Avaliacao.falta()` field-name suffix -> `capacidades.py`'s
#: canonical vocabulary, for the three spots where they differ (see this
#: module's `Fonte` docstring). Shared by `proveniencia.linhagem`
#: (`REGISTRO`'s own field names, unabridged) and `contrato_gerador.
#: derivacao` (`falta()`'s dotted `campo` strings, translated via their
#: LAST segment) so neither keeps its own copy — importing each other is
#: not an option: `derivacao` is imported BY `validacao_extracao`, which
#: `linhagem` also imports, so `derivacao -> linhagem` would cycle back.
RENOMEADOS_CAMPO: dict[str, str] = {
    "nome_oficial": "nome",
    "rg_orgao_expedidor": "rg_orgao",
    "certidao_estado_civil_emitida_em": "data_emissao",
}

#: `identidade_extracao_service.CAMPOS`' full canonical vocabulary, mapped
#: onto `capacidades.py`'s names (`nome_oficial -> nome`, `rg_orgao_
#: expedidor -> rg_orgao`) — every cliente-document `Fonte` below claims this
#: much UNLESS the document physically cannot carry it (`cpf`, narrower).
_CAMPOS_IDENTIDADE_BASE: frozenset[str] = frozenset(
    {
        "data_nascimento", "nome", "genero", "cpf", "rg", "rg_orgao",
        "estado_civil", "regime_bens", "data_casamento", "nacionalidade",
        "profissao",
    }
)

#: `imovel_hub.documentos_service.ORIGENS_ESTRUTURA`, mirrored — see
#: `Fonte.origens`' own docstring for why this is not an import.
_ORIGENS_ESTRUTURA: frozenset[str] = frozenset({"ia", "manual"})

_ENTRADAS_CLIENTE_UPLOAD = frozenset({Entrada.CLIENTE_CARD_UPLOAD, Entrada.PARTE_PAINEL_UPLOAD})

#: The registry — ordered. `imovel_hub.documentos_service.TIPOS_DOCUMENTO`
#: is re-derived from this tuple's own order (`(f.tipo_documento for f in
#: FONTES_REGISTRO if f.dominio == "imovel")`), so the imóvel entries below
#: are declared in the SAME order that constant has always shipped in:
#: `matricula, guia_iptu, cnd_iptu, cnd_condominio`.
FONTES_REGISTRO: tuple[Fonte, ...] = (
    # ─── cliente_documentos (card_hub/identidade_extracao_service) ────────
    Fonte(
        tipo_documento="rg",
        dominio="cliente",
        entradas=_ENTRADAS_CLIENTE_UPLOAD,
        extrator="noctusai_lib.integrations.documents.factory.make_identity_extractor",
        origens=frozenset({"rg"}),
        campos=_CAMPOS_IDENTIDADE_BASE,
    ),
    Fonte(
        tipo_documento="cpf",
        dominio="cliente",
        entradas=_ENTRADAS_CLIENTE_UPLOAD,
        extrator="noctusai_lib.integrations.documents.factory.make_identity_extractor",
        origens=frozenset({"cpf"}),
        # Narrower than `_CAMPOS_IDENTIDADE_BASE` on purpose — a CPF card
        # carries no birthdate/estado-civil/etc. See the class docstring.
        campos=frozenset({"nome", "cpf"}),
    ),
    Fonte(
        tipo_documento="cnh",
        dominio="cliente",
        entradas=_ENTRADAS_CLIENTE_UPLOAD,
        extrator="noctusai_lib.integrations.documents.factory.make_identity_extractor",
        origens=frozenset({"cnh"}),
        campos=_CAMPOS_IDENTIDADE_BASE,
    ),
    Fonte(
        tipo_documento="certidao_casamento",
        dominio="cliente",
        entradas=_ENTRADAS_CLIENTE_UPLOAD,
        extrator="noctusai_lib.integrations.documents.factory.make_identity_extractor",
        origens=frozenset({"certidao_casamento"}),
        # The averbação carries estado_civil/regime_bens/data_casamento
        # beside identity, PLUS the spouse link and the certidão's own
        # emission date — see `capacidades.CAPACIDADES["certidao_casamento"]`.
        campos=_CAMPOS_IDENTIDADE_BASE | {"conjuge", "data_emissao"},
        # Contract F6 / migration 110 — the estado-civil averbação is
        # further into the document than page 1; truncating it inverts the
        # answer (see `identidade_extracao_service.TIPOS_LEITURA_INTEGRAL`).
        leitura_integral=True,
    ),
    Fonte(
        tipo_documento="certidao_nascimento",
        dominio="cliente",
        entradas=_ENTRADAS_CLIENTE_UPLOAD,
        extrator="noctusai_lib.integrations.documents.factory.make_identity_extractor",
        origens=frozenset({"certidao_nascimento"}),
        campos=_CAMPOS_IDENTIDADE_BASE | {"data_emissao"},
        leitura_integral=True,
    ),
    Fonte(
        tipo_documento="comprovante_endereco",
        dominio="cliente",
        entradas=_ENTRADAS_CLIENTE_UPLOAD,
        extrator="noctusai_lib.integrations.documents.address.find_endereco",
        origens=frozenset({"comprovante_endereco"}),
        # Address-only by product policy AND by what the document is
        # evidence of — a utility bill's printed name/CPF belong to
        # whoever it was mailed to, not necessarily this titular.
        campos=frozenset({"endereco"}),
    ),
    # ─── imovel_documentos (imovel_hub/documentos_service) ─────────────────
    Fonte(
        tipo_documento="matricula",
        dominio="imovel",
        entradas=frozenset({Entrada.IMOVEL_PAGE_UPLOAD, Entrada.MATRICULAS}),
        extrator="noctusai_lib.integrations.documents.matricula.find_matricula",
        # Two independent write paths land on `matricula`: the número read
        # itself (`origem='matricula'`, the quinteto pattern) and the
        # migration-118 structured read (`origem` in `ia`/`manual`).
        origens=frozenset({"matricula"}) | _ORIGENS_ESTRUTURA,
        # `numero_matricula` — the imóvel-domain header field `extrator`
        # above reads. The other seven are a SEPARATE reader over the SAME
        # upload (`matriculas.qualificacao_service`'s consumer of
        # `noctusai_lib.integrations.documents.matricula_qualificacao
        # .extrair_qualificacoes`, per migration 137) that lands on
        # `clientes` (`ORIGEM_MATRICULA = "matricula"`, the same `origens`
        # value already claimed above) rather than on `imovel_dados` — one
        # `Fonte` because there is one physical document, not two. `Fonte.
        # dominio` stays `"imovel"` (this is the imóvel-upload channel's
        # entry, and every `dominio`-filtered reader —
        # `identidade_extracao_service.TIPOS_EXTRAIVEIS`/`TIPOS_ENDERECO` —
        # only reads `dominio == "cliente"` Fontes, so this stays invisible
        # to card_hub's own identity-upload gating either way): `linhagem
        # ._fontes_possiveis` matches candidates by `campos` alone, not by
        # `dominio`, which is what lets a cliente-domain gap (e.g.
        # `profissao`) legitimately resolve to an imóvel-domain document.
        campos=frozenset(
            {"numero_matricula", "profissao", "estado_civil", "nacionalidade",
             "rg", "rg_orgao", "endereco", "genero"}
        ),
        estrutura_extraivel=True,
    ),
    Fonte(
        tipo_documento="guia_iptu",
        dominio="imovel",
        entradas=frozenset({Entrada.IMOVEL_PAGE_UPLOAD}),
        extrator="app.modules.imovel_hub.documentos_service.extrair_estrutura",
        origens=_ORIGENS_ESTRUTURA,
        # No seed-typed capability backs this read (an ad-hoc per-product
        # LLM JSON prompt, `CAMPOS_ESTRUTURA_POR_TIPO["guia_iptu"]` — see
        # the class docstring's `campos` note) — left empty deliberately.
        estrutura_extraivel=True,
    ),
    Fonte(
        tipo_documento="cnd_iptu",
        dominio="imovel",
        entradas=frozenset({Entrada.IMOVEL_PAGE_UPLOAD}),
        extrator="app.modules.imovel_hub.documentos_service.extrair_estrutura",
        origens=_ORIGENS_ESTRUTURA,
        estrutura_extraivel=True,
    ),
    Fonte(
        tipo_documento="cnd_condominio",
        dominio="imovel",
        entradas=frozenset({Entrada.IMOVEL_PAGE_UPLOAD}),
        extrator="app.modules.imovel_hub.documentos_service.extrair_estrutura",
        origens=_ORIGENS_ESTRUTURA,
        estrutura_extraivel=True,
    ),
    # ─── P0c: Serasa Crednet (cliente_documentos) / Cartão CNPJ (empresa_
    # documentos) — contract `sw-drive-extraction-P0c-contract.md` §B/§C ────
    Fonte(
        tipo_documento="serasa_crednet",
        dominio="cliente",
        entradas=_ENTRADAS_CLIENTE_UPLOAD,
        extrator=(
            "noctusai_lib.integrations.documents.serasa_crednet"
            ".make_crednet_extractor"
        ),
        origens=frozenset({"serasa_crednet"}),
        # 🔴 Narrower than `_CAMPOS_IDENTIDADE_BASE` on purpose — a Crednet
        # consulta is not an identity document and never reads `genero`/
        # `rg`/`rg_orgao`/`estado_civil`/`regime_bens`/`data_casamento`/
        # `nacionalidade`/`profissao` (seed `CrednetFields`, contract §B).
        # It DOES read `nome_mae` — a field no OTHER cliente Fonte claims
        # (§A.6/§A.7). `participacoes`/`ocorrencias` are not `clientes`
        # columns at all (they land on `empresas` and on the certidão 9
        # resultado respectively, via `crednet_service.aplicar_leitura`) —
        # the field-provenance map only walks `clientes` columns, so they
        # are deliberately absent here. Guard 4
        # (`test_proveniencia_fontes.TestCapacidades`) is what caught this
        # Fonte over-claiming `_CAMPOS_IDENTIDADE_BASE` wholesale once the
        # `_PENDING_CROSS_SLICE_TIPOS` skip allowlist was removed.
        campos=frozenset({"nome", "cpf", "data_nascimento", "nome_mae"}),
        # The vision rung must read every page — participações routinely
        # sit on page 2 (§B: "max_pages=None reads every page").
        leitura_integral=True,
    ),
    Fonte(
        tipo_documento="cartao_cnpj",
        dominio="empresa",
        entradas=frozenset({Entrada.EMPRESA_CARD_UPLOAD}),
        extrator=(
            "noctusai_lib.integrations.documents.cartao_cnpj"
            ".make_cartao_cnpj_extractor"
        ),
        origens=frozenset({"cartao_cnpj"}),
        campos=frozenset(
            {"cnpj", "razao_social", "nome_fantasia", "natureza_juridica",
             "data_abertura", "situacao_cadastral", "data_situacao_cadastral",
             "motivo_situacao", "uf"}
        ),
    ),
)

#: Keyed like `contrato_gerador.validacao_extracao._POR_ENTIDADE_CAMPO` —
#: same construction (a comprehension over the canonical tuple above), same
#: reason: the tuple is what a human reads top-to-bottom, the dict is what
#: code looks a `tipo_documento` up in.
FONTES: dict[str, Fonte] = {f.tipo_documento: f for f in FONTES_REGISTRO}

#: Human label per `tipo_documento` — `proveniencia.linhagem`'s
#: `fontes_possiveis[].rotulo` and `GET /api/proveniencia/registro`'s FE
#: hints both read this rather than each inventing its own copy.
ROTULOS_TIPO_DOCUMENTO: dict[str, str] = {
    "rg": "RG",
    "cpf": "CPF",
    "cnh": "CNH",
    "certidao_casamento": "Certidão de casamento",
    "certidao_nascimento": "Certidão de nascimento",
    "comprovante_endereco": "Comprovante de endereço",
    "matricula": "Matrícula do imóvel",
    "guia_iptu": "Guia do IPTU",
    "cnd_iptu": "CND de IPTU",
    "cnd_condominio": "CND de condomínio",
    "serasa_crednet": "Serasa Crednet",
    "cartao_cnpj": "Cartão CNPJ",
}

#: The table a `<campo>_documento_id` resolved into, mapped onto the
#: `Entrada` it stands for — `validacao_extracao.documentos_de_origem`
#: tags each resolved row `_tabela`; this is the other half of that join,
#: kept here (not there) so that module stays free of `Entrada` vocabulary.
#: `cliente_documentos` covers both cliente-upload channels (`CLIENTE_CARD_
#: UPLOAD`/`PARTE_PAINEL_UPLOAD`) — the row itself does not say which, so
#: this picks the operator-facing one; `Fonte.entradas` is still the
#: authoritative "which channels can feed this tipo_documento" answer.
TABELA_ENTRADA: dict[str, Entrada] = {
    "cliente_documentos": Entrada.CLIENTE_CARD_UPLOAD,
    "imovel_documentos": Entrada.IMOVEL_PAGE_UPLOAD,
    "matricula_extracoes": Entrada.MATRICULAS,
    "empresa_documentos": Entrada.EMPRESA_CARD_UPLOAD,
}


def resolver_extrator(fonte: Fonte) -> Any:
    """Import `fonte.extrator` and return the callable it names.

    Fails loudly (`ImportError` / `AttributeError`) on a stale dotted path
    — the whole point of `test_fontes.py::test_every_extrator_path_imports`.
    """
    modulo, _, nome = fonte.extrator.rpartition(".")
    return getattr(importlib.import_module(modulo), nome)


#: §0a's "Manual-only — no document carries it (by design, not a gap)"
#: paragraph, moved from prose into a value a test can walk. These are
#: CONTRACT data categories, not `contrato_gerador.validacao_extracao.
#: REGISTRO` field names — none of them are machine-validatable (there is
#: no document to extract them from even in principle), so none of them
#: appear in `REGISTRO` at all. Kept here, next to `FONTES`, as the other
#: half of "where does this contract value come from" — and as the backstop
#: `test_fontes.py` checks every `REGISTRO` entry against: FONTES-covered,
#: here, or named in `FORA_DO_ESCOPO_S1` below — never silently neither.
MANUAL_APENAS: frozenset[str] = frozenset(
    {
        "negociacao_valor", "negociacao_parcelas", "negociacao_favorecidos",
        "negociacao_termos", "confissao", "permuta_termos", "posse",
        "financiamento", "intermediarios_qualificacao", "intermediarios_comissao",
        "org_dados_cadastrais", "testemunhas", "parte_email",
        "assinatura_data", "contrato_modelo", "matricula_atos_selecionados",
        "permuta_ativo_endereco",
        # 🔴 `certidao_pj_situacao_cadastral` DROPPED (P0c contract §C1): a
        # company's situação cadastral is now machine-sourced off the Cartão
        # CNPJ (`Fonte("cartao_cnpj", ...)` above), not manual-only.
        "parte_papel_no_card", "politica_constantes",
    }
)

#: `(entidade, campo)` pairs from `contrato_gerador.validacao_extracao.
#: REGISTRO` whose extractor lives OUTSIDE this slice's file scope
#: (`matriculas/preenchimento_service.py`, `matriculas/titulo_service.py`,
#: `certidoes/service.py`, `matricula_ato_detalhes.py` — none of which S1
#: touches). `("imovel_documento", "certidao")` is NOT here: it IS covered,
#: by the four `dominio == "imovel"` `Fonte`s' `estrutura_extraivel` leg
#: (`imovel_hub.documentos_service.extrair_estrutura`), which this slice
#: does touch. Each of the pairs below is REAL, machine-sourced data per
#: `CONTRACT-FIELD-PROVENANCE-MAP.md` §0a (not manual-only) — naming them
#: here, rather than leaving them uncovered, is what keeps `test_fontes.py`'s
#: REGISTRO sweep from reading a real gap as a silent pass. A future slice
#: (S2 imóvel / S3 certidões) shrinks this set by adding real `Fonte`
#: entries and moving the pair out.
FORA_DO_ESCOPO_S1: frozenset[tuple[str, str]] = frozenset(
    {
        ("imovel", "numero_registro_imoveis"),
        ("imovel", "prefeitura_cadastro_imobiliario"),
        ("imovel", "situacao_onus"),
        ("imovel", "titulo_aquisitivo_texto"),
        ("imovel", "onus_credor"),
        ("imovel", "titulo_aquisitivo"),
        ("imovel", "onus_fonte"),
        ("certidao", "certidao"),
        ("ato_detalhe", "ultima_transferencia"),
        # P0c contract §C1/§E — `("empresa", "dados")` is S2b's GROUP-level
        # `validacao_extracao.REGISTRO` entry for the whole `empresas` D1
        # provenance quintet (`dados_origem/_documento_id/_em/_confirmado_
        # por/_confirmado_em`). `linhagem.CANONICOS_REGISTRO`'s auto-derived
        # translation (`_canonicos_do_registro`) only walks `vx.CAMPOS_
        # CLIENTE` + `vx.CAMPOS_IMOVEL`'s `numero_matricula` special case —
        # extending it for a THIRD entity is a `linhagem.py`/`validacao_
        # extracao.py` change (S2b's files, not this slice's), so this is
        # named here rather than left silently uncovered. The `Fonte`
        # ("cartao_cnpj", dominio="empresa", ...) above DOES claim the real
        # per-field canonical names (`razao_social`, `situacao_cadastral`,
        # ...) — only the GROUP pseudo-field `"dados"` itself has no direct
        # translation entry.
        ("empresa", "dados"),
    }
)
