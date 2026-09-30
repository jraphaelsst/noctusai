"""Read a bank's own registration form ("ficha cadastral bancária") — the
buyer/seller/FGTS forms every financed deal folder carries
("FORMULÁRIO COMPRADOR ITAÚ" / "FORMULÁRIO VENDEDOR PESSOA FÍSICA ITAÚ" /
"FORMULÁRIO FGTS ITAÚ") — into one or more `PessoaFichaCadastral`.

WHY THIS DOCUMENT MATTERS (live prod test on 5 historical deals, 2026-09-30)
-----------------------------------------------------------------------
The contract's party ADDRESS (and sometimes profissão/estado civil) came
from these forms for every party that had one: the contract's CEP matched
the form's own CEP for 16/16 parties measured, the street for ~12/16. Today
the platform has no reader for them at all, so address stays empty for most
parties (a proof of address is routinely missing, or in someone else's
name) — this is the single biggest remaining extraction gap the live test
surfaced.

WHY THIS IS A DIFFERENT SHAPE FROM `types.IdentityFields`
----------------------------------------------------------
Every OTHER extractor in this package reads ONE document belonging to ONE
person (an RG, a CNH) or, at most, a certidão naming exactly two co-equal
spouses (`conjuges.py`). A ficha cadastral is structurally different: the
SAME PDF may carry a proponente AND their cônjuge on TWO consecutive pages
(the buyer form), or one OR two sellers (the seller form), or a single
person's own FGTS declaration — with no "titular" bias to pick one: a
consumer must attribute EVERY person it names, by their own printed CPF,
never guess which one the caller already knows. `IdentityFields.conjuges`
solves a narrower problem (bias toward the card's own titular); this module
returns every person flatly, in document order, and leaves attribution to
the caller (social-wiring's `ficha_cadastral_service`, which matches each
person's CPF against the atendimento's own parties).

🔴 THESE ARE FILLABLE PDF FORMS — THE TEXT LAYER'S READING ORDER LIES
----------------------------------------------------------------------
Measured directly (PyMuPDF `page.get_text()` vs `page.widgets()` on the
real corpus, 2026-09-30): a fillable AcroForm page's plain text extraction
prints EVERY LABEL FIRST (the form's static content), then EVERY FILLED
VALUE AFTER, in field order but nowhere near its own label — because the
widget appearance streams render (and therefore extract) separately from
the page's own content stream. A label-proximity reader (`address._rotulado`'s
own strategy) would pair the wrong label with the wrong value on a page
shaped this way, confidently. So the PRIMARY rung here is not text at all:
it is the PDF's own AcroForm FIELD NAMES and VALUES (`ficha_cadastral_
extractor.py` reads them via `fitz`; this module only classifies and
groups the resulting `(nome_campo, valor, pagina, tipo)` triples — kept
pure/fitz-free, like every sibling parser here).

A page's fields are grouped into ONE person (`_pessoa_da_pagina`) — measured
on the corpus: the buyer/seller templates place exactly one person's whole
block on one page (the SAME shape, copy-pasted per person, page 1 =
proponente/1º vendedor, page 2 = cônjuge/2º vendedor). A page whose only
matches are a bank-account row's "Nome/CPF do vendedor" (repeated for
payment purposes, no other person-shaped field beside it) or a cartório's
own name is REJECTED by `_pessoa_valida` before it ever becomes a
`PessoaFichaCadastral` — see that function's own note.

FIELD-NAME VOCABULARY IS TEMPLATE-SPECIFIC, DELIBERATELY CLOSED
------------------------------------------------------------------
`_CLASSIFICADORES` below is a closed, ordered table — the same shape
`address._ROTULOS` is — built against the Itaú comprador/vendedor/FGTS
templates measured on the P3 corpus (2026-09-30). A differently-shaped
bank form (a different vendor's own field-naming convention) extends this
table; it does not invent a NEW mechanism.

🔴 THE ESTADO CIVIL / REGIME DE BENS RADIO GROUPS ARE POSITION-DECODED,
NEVER `ALTA`
------------------------------------------------------------------------
The comprador/vendedor templates print these as an UNLABELLED radio group
— PyMuPDF returns only the CHECKED button's own export value (a bare
digit, `"1"`.."6"), never the option's text. The digit-to-option mapping
below (`_ESTADO_CIVIL_RADIO` / `_REGIME_BENS_RADIO`) is inferred from the
STATIC text printed beside the checkboxes, in the SAME order the buttons
themselves are drawn — correct for every form in the P3 corpus, but a
template-specific inference, not a labelled read. `BAIXA`, never `ALTA` —
this is the one field family in this module the seed cannot verify
mechanically. FGTS's own `ESTADO CIVIL` field is a `ComboBox` printing the
option's actual TEXT (`"Solteiro(a)"`) — read directly, `ALTA`, no
decode needed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from noctusai_lib.integrations.documents.address import EnderecoLido, find_endereco, normalizar_uf
from noctusai_lib.integrations.documents.birthdate import MAX_AGE, MIN_AGE
from noctusai_lib.integrations.documents.cpf import format_cpf, is_valid as cpf_is_valid, only_digits
from noctusai_lib.integrations.documents.nacionalidade import canonico as nacionalidade_canonica
from noctusai_lib.integrations.documents.text import strip_accents_upper
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource

#: Every field a widget-driven read can lift onto one person, PLUS
#: `rg_orgao` — same "travels with `rg`, not independently persistable"
#: reasoning `types.IdentityFields.rg_orgao` gives (this module mirrors
#: that decision rather than re-deriving it).
CAMPOS: tuple[str, ...] = (
    "nome", "cpf", "rg", "data_nascimento", "estado_civil",
    "regime_bens", "nacionalidade", "profissao",
)

ALTA = ExtractionConfidence.ALTA
BAIXA = ExtractionConfidence.BAIXA
NENHUMA = ExtractionConfidence.NENHUMA


@dataclass(frozen=True)
class PessoaFichaCadastral:
    """One person's own block off a ficha cadastral bancária.

    Every value Optional — a form legibly read may simply not carry a
    given field for this person (a seller form has no `data_casamento`
    box when the seller states `solteiro`, for instance).
    """

    #: The form's own section this block sat in — `"proponente"` /
    #: `"conjuge"` / `"vendedor"` / `"titular"` (FGTS, a single-person
    #: form) — whatever the caller can tell from which upload slot/page
    #: this was; `None` when the form itself gives no cue.
    papel: Optional[str] = None

    nome: Optional[str] = None
    nome_confianca: ExtractionConfidence = NENHUMA

    cpf: Optional[str] = None
    cpf_confianca: ExtractionConfidence = NENHUMA

    rg: Optional[str] = None
    rg_confianca: ExtractionConfidence = NENHUMA
    #: Travels with `rg`, never independently persisted — see the module
    #: docstring on `types.IdentityFields.rg_orgao`.
    rg_orgao: Optional[str] = None
    rg_orgao_confianca: ExtractionConfidence = NENHUMA

    data_nascimento: Optional[date] = None
    data_nascimento_confianca: ExtractionConfidence = NENHUMA

    #: Closed vocabulary — `civil_status.ESTADO_CIVIL_VALORES`.
    estado_civil: Optional[str] = None
    estado_civil_confianca: ExtractionConfidence = NENHUMA

    #: Closed vocabulary — `civil_status.REGIME_BENS_VALORES`. Only
    #: meaningful beside a married `estado_civil`, same as elsewhere in
    #: this package.
    regime_bens: Optional[str] = None
    regime_bens_confianca: ExtractionConfidence = NENHUMA

    #: Closed vocabulary — `nacionalidade.NACIONALIDADE_VALORES`.
    nacionalidade: Optional[str] = None
    nacionalidade_confianca: ExtractionConfidence = NENHUMA

    #: Label-anchored-equivalent (it sat in the form's own "Profissão" box)
    #: — lower-cased, with the document's own accents, matching `types.
    #: IdentityFields.profissao`'s own convention.
    profissao: Optional[str] = None
    profissao_confianca: ExtractionConfidence = NENHUMA

    #: A GROUP, like `IdentityFields.endereco` — written together or not at
    #: all. `None` when this person's block carried no usable address.
    endereco: Optional[EnderecoLido] = None

    telefone: Optional[str] = None
    email: Optional[str] = None

    def _valor(self, campo: str) -> object:
        return getattr(self, campo)

    def _confianca(self, campo: str) -> ExtractionConfidence:
        return getattr(self, f"{campo}_confianca")

    def presente(self, campo: str) -> bool:
        if campo not in CAMPOS:
            raise KeyError(campo)
        return bool(self._valor(campo))

    def persistable(self, campo: str) -> bool:
        """May this be written unattended? `ALTA` only — uniform bar,
        matching `IdentityFields.persistable`'s own reasoning."""
        return self.presente(campo) and self._confianca(campo) is ALTA

    def sugestao(self, campo: str) -> bool:
        return self.presente(campo) and self._confianca(campo) is BAIXA


@dataclass(frozen=True)
class FichaCadastralLida:
    """Every person a ficha cadastral bancária named, in document order."""

    pessoas: tuple[PessoaFichaCadastral, ...] = ()
    source: TextSource = TextSource.NENHUMA
    error: Optional[str] = None
    error_message: Optional[str] = None
    #: Set when a page carried person-shaped fields (nome+cpf) that failed
    #: `_pessoa_valida`'s minimum-richness bar — a notice, not a failure
    #: (`aviso`, never `error`, per the documents package's own rule): the
    #: read still succeeded, this page just was not a person's own block
    #: (a bank-account row repeating an already-captured name/CPF).
    aviso: Optional[str] = None


# ─── Radio-group decode: TEXT, never POSITION ──────────────────────────────
#
# 🔴 P3 CORPUS FINDING (2026-09-30) — A POSITION-BASED DECODE IS WRONG, AND
# MEASURABLY SO. This module's first pass assumed the checked button's own
# export value (`"1"`..`"6"`) followed the printed reading order of the
# options beside it — the same shape `_ESTADO_CIVIL_TEXTO` below replaces.
# Calibrated against the 5-deal P3 answer keys (matching each ficha's own
# CPF to the signed contract's `estado_civil`/`regime_bens`): the SAME
# export value (`"3"`) decoded to `casado` on one page and the position
# table said `viuvo`; a DIFFERENT page's `EstadoCivil1#V1` group used `"2"`
# for the SAME real-world `casado` — different button-creation order on
# different template revisions of the SAME PDF's own pages. A fixed
# `{"1": "solteiro", "2": "casado", ...}` table is not a measured signal at
# all, it is a coincidence that happened to be right on the FIRST form
# inspected and wrong on the next one — exactly the shape of bug this
# package's `misfile.py`/`labels.py` decoy tables exist to prevent
# elsewhere.
#
# What DOES hold, geometrically verified against the same 5-deal corpus:
# each checkbox's own PRINTED LABEL sits immediately beside its `rect` on
# the page — `ficha_cadastral_extractor.py`'s `_rotulo_geometrico` reads
# that text directly (fitz page text within a clip box around the widget),
# and this module only ever canonicalises the RESULTING LABEL STRING
# (`"CASADO"`, `"COMUNHAO PARCIAL"`) into the closed vocabulary below —
# never a bare digit. `estado_civil_de_texto`/`regime_bens_de_texto` are
# shared by BOTH that geometric read (BAIXA — an inferred nearest-label
# match, never `ALTA`) and FGTS's own `ComboBox` (which prints the SAME
# option text directly as its field VALUE, no geometry needed — `ALTA`).

_ESTADO_CIVIL_TEXTO: dict[str, str] = {
    "SOLTEIRO": "solteiro",
    "CASADO": "casado",
    "VIUVO": "viuvo",
    "DIVORCIADO": "divorciado",
    "SEPARADO": "separado_judicialmente",
    "SEPARADO JUDICIALMENTE": "separado_judicialmente",
    "UNIAO ESTAVEL": "uniao_estavel",
    # "Desquitado(a)" has no slot in `civil_status.ESTADO_CIVIL_VALORES` —
    # an archaic pre-1977 term distinct enough from `separado_judicialmente`
    # that guessing would misrepresent the party's actual regime; left
    # unmapped (falls through to `None`) rather than forced into a bucket.
}

_REGIME_BENS_TEXTO: dict[str, str] = {
    "COMUNHAO PARCIAL": "comunhao_parcial",
    "COMUNHAO DE PARCIAL": "comunhao_parcial",
    "SEPARACAO TOTAL": "separacao_total",
    "COMUNHAO UNIVERSAL": "comunhao_universal",
    "PARTICIPACAO FINAL": "participacao_final_aquestos",
    "SEPARACAO OBRIGATORIA": "separacao_obrigatoria",
}

#: The printed option phrases `ficha_cadastral_extractor._rotulo_geometrico`
#: searches for beside a checkbox's own `rect` — ORDER MATTERS for
#: `regime`: `"COMUNHAO PARCIAL"` must be tried before the form's own
#: `"Regime de Comunhão Parcial Bens"` heading could otherwise match a
#: broader/shorter alternative first (there is none today, kept explicit
#: for the next entry).
ESTADO_CIVIL_OPCOES: tuple[str, ...] = (
    "SOLTEIRO", "CASADO", "VIUVO", "DIVORCIADO", "SEPARADO", "DESQUITADO",
)
REGIME_BENS_OPCOES: tuple[str, ...] = (
    "COMUNHAO PARCIAL", "COMUNHAO DE PARCIAL", "SEPARACAO TOTAL",
    "COMUNHAO UNIVERSAL", "PARTICIPACAO FINAL", "SEPARACAO OBRIGATORIA",
)


def _normalizar_opcao(texto: str) -> str:
    """`"Solteiro(a)"` → `"SOLTEIRO"` — the `(a)`/`(o)` gender suffix is
    DROPPED WHOLE (not just its parentheses): stripping only punctuation
    would merge the bare letter onto the word (`"SOLTEIROA"`), which
    matches nothing in the vocabulary tables below."""
    s = strip_accents_upper(texto)
    s = re.sub(r"\([A-Z]+\)", "", s)
    return re.sub(r"[^A-Z ]", "", s).strip()


def estado_civil_de_texto(valor: str) -> Optional[str]:
    """A raw estado-civil LABEL (`"Solteiro(a)"`, or the geometric read's
    `"CASADO"`) → the closed vocabulary, or `None` when it names nothing
    this package tracks (`"Desquitado(a)"`)."""
    return _ESTADO_CIVIL_TEXTO.get(_normalizar_opcao(valor))


def regime_bens_de_texto(valor: str) -> Optional[str]:
    """Same shape as `estado_civil_de_texto`, for `regime_bens`."""
    return _REGIME_BENS_TEXTO.get(_normalizar_opcao(valor))


# ─── Field-name classification ──────────────────────────────────────────────


def _norm_campo(nome_campo: str) -> str:
    """Collapse a widget's field name to bare lowercase letters — accent,
    case, digit, punctuation and `#`-suffix insensitive. The SAME logical
    field prints as `"Data de Nascimento 1"` on one template revision and
    `"nascv2"` on another (measured, same PDF, adjacent pages) — matching
    is only tractable once both collapse to comparable substrings
    (`"datadenascimento"` / `"nascv"`, both containing `"nasc"`)."""
    s = strip_accents_upper(nome_campo or "").lower()
    return re.sub(r"[^a-z]", "", s)


#: Ordered (substring, campo) pairs — first match wins, same shape as
#: `address._ROTULOS`. Checked AFTER the exclusion gates in `classificar_
#: campo` below (procurador/bank-account/correspondence/parent sections,
#: and birth city/UF, which share substrings with wanted fields).
_CLASSIFICADORES: tuple[tuple[str, str], ...] = (
    ("cep", "endereco_cep"),
    ("bairro", "endereco_bairro"),
    ("nasc", "data_nascimento"),
    ("nacio", "nacionalidade"),
    ("profiss", "profissao"),
    ("ocupac", "profissao"),
    # RG number — BEFORE the generic "numero" (address) rule below, and
    # before "documento" alone (which also names the TYPE radio, excluded
    # separately in `classificar_campo`).
    ("numerodedocumento", "rg_numero"),
    ("numdoc", "rg_numero"),
    ("documentovendedor", "rg_numero"),
    ("orgaoexpedidor", "rg_orgao"),
    ("orgao", "rg_orgao"),
    ("estadocivil", "estado_civil"),
    ("regimedecasamento", "regime_bens"),
    ("regimecasamento", "regime_bens"),
    ("logradouro", "endereco_logradouro"),
    ("enderecoresidencial", "endereco_logradouro"),
    ("enderecocont", "endereco_bruto_cont"),
    ("endereco", "endereco_bruto"),
    ("cidade", "endereco_cidade"),
    ("municipio", "endereco_cidade"),
    ("estado", "endereco_uf"),
    ("telefonecelular", "telefone"),
    ("telcel", "telefone"),
    ("telefoneresidencial", "telefone"),
    ("telresid", "telefone"),
    ("telefonecomercial", "telefone"),
    ("telcom", "telefone"),
    ("email", "email"),
    ("cpf", "cpf"),
    ("nome", "nome"),
)

#: Short-abbreviation fallbacks (`"End#V1"`, `"Num#v1"`, `"complem#v1"` —
#: one template abbreviates every address label to its first syllable,
#: measured P3 corpus, beside the SAME page's full-word `Bairro`/`Cidade`/
#: `Estado`/`CEP`). Matched only as a PREFIX, never `in norm` — `"end"` is a
#: substring of `"vendedor"`/`"comprador"` (a page's OWN `"Nome Vendedor#V1"`
#: field would otherwise misclassify as an address before `_CLASSIFICADORES`'
#: `"nome"` entry ever got a turn), and `"num"` is a substring of any field
#: whose name happens to contain it. Checked only when `_CLASSIFICADORES`
#: found nothing — a full-word match anywhere else always wins first.
_CLASSIFICADORES_PREFIXO: tuple[tuple[str, str], ...] = (
    ("end", "endereco_logradouro"),
    ("num", "endereco_numero"),
    ("complem", "endereco_complemento"),
)

#: 🔴 `NOC-REMEDIATE[ficha-cadastral-corresp-numbered-suffix]` — one
#: template's correspondence-address override fields (`"Local de entrega de
#: Correspondência"` toggle) are named `"Endereço 1"` / `"Número_2"` /
#: `"CEP_2"` — no `"corresp"` substring at all, unlike every other template
#: measured. `montar_pessoas`' first-non-empty-wins per campo means the
#: PRIMARY (residential) fields, which the widget order always lists
#: first, win whenever both are filled; the gap is real only when the
#: primary group is empty and the override is filled, unmeasured on the P3
#: corpus (every sample had a primary address). Left named rather than
#: guessed at with a stickier state machine this corpus gives no evidence
#: to calibrate.
#:
#: Field names carrying one of these are NEVER this person's own fact —
#: matched before `_CLASSIFICADORES` runs at all.
_EXCLUSOES = (
    "procurador", "mae", "pai", "filiacao", "banco", "agencia", "corren",
    "poup", "receber", "inss", "corresp", "garagem", "anexo", "cartorio",
    "responsavel", "razaosocial", "tipodedocumento", "uniaoestavel", "cnpj",
    # A property/matrícula block riding on the SAME page as a person's own
    # registration fields (measured, P3 corpus: one vendedor template also
    # carries `"Numero matricula"` / `"numero IPU"` / `"Cidade do cartório"`
    # trailing the person's own block) — a registry/tax number is never this
    # person's own address/identity fact, whatever short substring ("num",
    # "cidade") it would otherwise share with one.
    "matricula", "iptu", "ipu",
)


def classificar_campo(nome_campo: str) -> Optional[str]:
    """One widget field name → the semantic slot it fills, or `None` when
    it names nothing this module reads (a procurador's own fields, a bank
    account row, a correspondence-address override, a parent's name, the
    document-TYPE radio, ...)."""
    norm = _norm_campo(nome_campo)
    if not norm:
        return None
    for decoy in _EXCLUSOES:
        if decoy in norm:
            return None
    for chave, campo in _CLASSIFICADORES:
        if chave in norm:
            if campo == "data_nascimento" and ("cid" in norm or "uf" in norm):
                # Birth city/UF — not this module's `data_nascimento`, and
                # not an address part either (it is the person's BIRTH
                # place, not their residence).
                return None
            return campo
    for chave, campo in _CLASSIFICADORES_PREFIXO:
        if norm.startswith(chave):
            return campo
    return None


# ─── Person assembly off classified widget values ───────────────────────────


def _parse_data_br(valor: str) -> Optional[date]:
    valor = (valor or "").strip()
    if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", valor):
        return None
    try:
        d = datetime.strptime(valor, "%d/%m/%Y").date()
    except ValueError:
        return None
    hoje = date.today()
    if d > hoje:
        return None
    idade = hoje.year - d.year - ((hoje.month, hoje.day) < (d.month, d.day))
    if not (MIN_AGE <= idade <= MAX_AGE):
        return None
    return d


def _limpar_texto(valor: str) -> Optional[str]:
    valor = " ".join((valor or "").split()).strip(" .,-")
    return valor or None


@dataclass
class CampoWidget:
    """One classified widget — the extractor's own read, handed in as data
    so this module stays fitz-free (`ficha_cadastral_extractor.py` is the
    only place that opens a PDF)."""

    campo: str
    valor: str
    tipo: str  # `fitz.Widget.field_type_string` — "Text" / "RadioButton" / "ComboBox"


def _pessoa_de_campos(campos: dict[str, str], *, papel: Optional[str]) -> Optional[PessoaFichaCadastral]:
    """One page's classified `{campo: valor}` → a person, or `None` when it
    does not clear `_pessoa_valida`'s bar."""
    nome = _limpar_texto(campos.get("nome", ""))
    cpf_bruto = campos.get("cpf", "")
    cpf_norm = format_cpf(cpf_bruto) if cpf_bruto else None
    if not nome or not cpf_norm:
        return None

    richness = any(
        campos.get(k)
        for k in (
            "data_nascimento", "profissao", "estado_civil", "endereco_cep",
            "endereco_bruto", "endereco_logradouro", "nacionalidade",
        )
    )
    if not richness:
        # A bank-account row repeating this person's own name/CPF for
        # payment purposes, or a cartório/banco's own name — see the module
        # docstring's `_pessoa_valida` note. Not a person's own block.
        return None

    cpf_confianca = ALTA if cpf_is_valid(cpf_bruto) else BAIXA

    data_nasc = _parse_data_br(campos.get("data_nascimento", ""))
    data_nasc_conf = ALTA if data_nasc else NENHUMA

    nacionalidade = nacionalidade_canonica(campos.get("nacionalidade", "") or "")
    nacionalidade_conf = ALTA if nacionalidade else NENHUMA

    profissao = _limpar_texto(campos.get("profissao", ""))
    profissao = profissao.lower() if profissao else None
    profissao_conf = ALTA if profissao else NENHUMA

    rg = _limpar_texto(campos.get("rg_numero", ""))
    # 🔴 F1 (live prod test, 2026-09-30): on some forms the widget classified
    # `rg_numero` ("Número de documento 1/2") actually holds this SAME
    # person's own CPF, digit for digit — a buyer whose identity document is
    # a CIN (which prints the CPF as its own number) filled it there, or the
    # template's own field mapping duplicated the CPF into this box. Unlike a
    # genuine CIN scan (`identidade_extracao_service._e_cin`'s own órgão
    # `IIGDR` corroboration), this bank form pairs it with an unrelated
    # órgão beside it — no corroborating signal this is a real RG at all.
    # 3 of 19 people measured got a wrong `rg == cpf` this way and it
    # outranked nothing better once written unattended. Withhold BOTH `rg`
    # and `rg_orgao` (NENHUMA) rather than vouch for a pair this form cannot
    # actually prove — a genuine CIN still reaches `clientes.rg` through an
    # actual identity-document read, never through this ambiguous field.
    if rg and only_digits(rg) == only_digits(cpf_norm):
        rg = None
    rg_conf = ALTA if rg else NENHUMA
    rg_orgao = _limpar_texto(campos.get("rg_orgao", "")) if rg else None
    rg_orgao_conf = ALTA if rg_orgao else NENHUMA

    # `estado_civil_texto` — a ComboBox/Text field printing the option's own
    # word directly (FGTS) — `ALTA`. `estado_civil_geo` — the extractor's
    # OWN nearest-printed-label read beside a RadioButton's `rect`
    # (comprador/vendedor templates) — `BAIXA`: an inferred geometric match,
    # never the document's own labelled field. See the module docstring's
    # note on why the export VALUE itself is never decoded by position.
    estado_civil = None
    estado_civil_conf = NENHUMA
    if campos.get("estado_civil_texto"):
        estado_civil = estado_civil_de_texto(campos["estado_civil_texto"])
        estado_civil_conf = ALTA if estado_civil else NENHUMA
    elif campos.get("estado_civil_geo"):
        estado_civil = estado_civil_de_texto(campos["estado_civil_geo"])
        estado_civil_conf = BAIXA if estado_civil else NENHUMA

    regime_bens = None
    regime_bens_conf = NENHUMA
    if campos.get("regime_bens_geo"):
        regime_bens = regime_bens_de_texto(campos["regime_bens_geo"])
        regime_bens_conf = BAIXA if regime_bens else NENHUMA

    endereco = _endereco_de_campos(campos)

    telefone = _limpar_texto(campos.get("telefone", ""))
    email = _limpar_texto(campos.get("email", ""))

    return PessoaFichaCadastral(
        papel=papel,
        nome=nome, nome_confianca=ALTA,
        cpf=cpf_norm, cpf_confianca=cpf_confianca,
        rg=rg, rg_confianca=rg_conf, rg_orgao=rg_orgao, rg_orgao_confianca=rg_orgao_conf,
        data_nascimento=data_nasc, data_nascimento_confianca=data_nasc_conf,
        estado_civil=estado_civil, estado_civil_confianca=estado_civil_conf,
        regime_bens=regime_bens, regime_bens_confianca=regime_bens_conf,
        nacionalidade=nacionalidade, nacionalidade_confianca=nacionalidade_conf,
        profissao=profissao, profissao_confianca=profissao_conf,
        endereco=endereco,
        telefone=telefone, email=email,
    )


def _endereco_de_campos(campos: dict[str, str]) -> Optional[EnderecoLido]:
    """The structured-parts form (comprador/vendedor) beats the raw-block
    form (FGTS's `ENDEREÇO`/`ENDEREÇOCONT`): a CEP or a bairro captured as
    its OWN field is exact digital data; the raw block still has to be
    re-parsed by `address.find_endereco`, which is a strictly weaker
    signal. `cidade`/`uf` alone (no `cep`, no `bairro`) are withheld — see
    the module docstring's FGTS `MUNICIPIO`/`ESTADO` ambiguity note: those
    columns describe up to three DIFFERENT locations on that form (home /
    work / employer), so a bare cidade/uf match is not trustworthy without
    a `cep` or `bairro` alongside it to confirm this is the residential
    block."""
    estruturado = any(
        campos.get(k) for k in ("endereco_cep", "endereco_bairro", "endereco_logradouro")
    )
    if estruturado:
        cep = _limpar_texto(campos.get("endereco_cep", ""))
        cep_digits = re.sub(r"\D", "", cep or "")
        cep_fmt = f"{cep_digits[:5]}-{cep_digits[5:]}" if len(cep_digits) == 8 else cep
        logradouro = _limpar_texto(campos.get("endereco_logradouro", ""))
        bairro = _limpar_texto(campos.get("endereco_bairro", ""))
        candidato = EnderecoLido(
            cep=cep_fmt,
            logradouro=logradouro,
            numero=_limpar_texto(campos.get("endereco_numero", "")),
            complemento=_limpar_texto(campos.get("endereco_complemento", "")),
            bairro=bairro,
            cidade=_limpar_texto(campos.get("endereco_cidade", "")),
            # F2 (live prod test, 2026-09-30): this ComboBox/Text field
            # carried a full state name ("São Paulo") rather than its sigla
            # on one measured form — `normalizar_uf` resolves either shape
            # and withholds anything that resolves to neither.
            uf=normalizar_uf(campos.get("endereco_uf", "")),
            confianca="alta" if cep_fmt else "baixa",
            rotulo="FICHA CADASTRAL",
        )
        # `EnderecoLido.presente`'s own bar — the SAME one every downstream
        # consumer (`identidade_extracao_service.aplicar_endereco_ao_
        # cliente`) already gates on: `cep`+`logradouro`, or (no CEP at
        # all) `logradouro`+`numero`+`cidade`+`uf`. A bare `bairro` with
        # nothing else is not a usable address.
        return candidato if candidato.presente else None
    bruto = _limpar_texto(campos.get("endereco_bruto", ""))
    cont = _limpar_texto(campos.get("endereco_bruto_cont", ""))
    if not bruto:
        return None
    texto = f"Endereço: {bruto} {cont or ''}".strip()
    lido = find_endereco(texto)
    return lido if lido.presente else None


def montar_pessoas(
    campos_por_pagina: dict[int, list[CampoWidget]],
    *,
    papel_por_pagina: Optional[dict[int, str]] = None,
) -> tuple[PessoaFichaCadastral, ...]:
    """Every page's classified widgets → the people this form names, in
    page order. `papel_por_pagina` is an optional caller hint (the upload's
    own declared shape — "this is a seller form", "this is the buyer
    form") passed straight through as `PessoaFichaCadastral.papel`; absent
    a hint, `papel` is `None`.

    `estado_civil_geo`/`regime_bens_geo` (a RadioButton) and `estado_civil_
    texto` (a ComboBox/Text) arrive HERE already resolved to the option's
    own printed LABEL TEXT — `ficha_cadastral_extractor.py`'s own job (it
    is the one place fitz/page geometry is available); this function is
    pure and only ever sees strings, same as every other campo. Any OTHER
    `RadioButton` this module has no business reading (the caller never
    classifies one — see `classificar_campo`'s own exclusions) is filtered
    upstream, never reaches here."""
    papel_por_pagina = papel_por_pagina or {}
    pessoas: list[PessoaFichaCadastral] = []
    for pagina in sorted(campos_por_pagina):
        campos: dict[str, str] = {}
        for cw in campos_por_pagina[pagina]:
            if cw.valor and cw.campo not in campos:
                campos[cw.campo] = cw.valor
        pessoa = _pessoa_de_campos(campos, papel=papel_por_pagina.get(pagina))
        if pessoa is not None:
            pessoas.append(pessoa)
    return tuple(pessoas)


__all__ = [
    "CAMPOS",
    "ESTADO_CIVIL_OPCOES",
    "REGIME_BENS_OPCOES",
    "FichaCadastralLida",
    "PessoaFichaCadastral",
    "classificar_campo",
    "estado_civil_de_texto",
    "regime_bens_de_texto",
    "montar_pessoas",
    "CampoWidget",
]
