"""Qualify a matrícula's parties by their DOCUMENT NUMBER, not a label.

`matricula_ato_detalhes._partes` reads `transmitentes`/`adquirentes` off
LABELS (`TRANSMITENTE:`, `ADQUIRENTE:`) or, failing that, a narrow narrative
verb+preposition cue. Real Brazilian registry acts are almost always narrative
prose with no such label — against the platform's own production corpus,
16 of 16 real acts came back with `transmitentes_confianca == "nenhuma"`. What
those acts DO carry, almost every time, is the rigid notarial qualification
formula:

    NOME EM MAIÚSCULAS, nacionalidade, estado civil, [maior,] profissão,
    RG nº <n>-<órgão>, CPF nº <n>, residente e domiciliado[a] na <endereço>

🔴 THE ANCHOR IS THE DOCUMENT NUMBER, NOT A LABEL
--------------------------------------------------
A CPF carries its own check digits (two of its eleven digits are a mod-11
function of the other nine), so a validated CPF is a MUCH stronger anchor
than any label a document-specific layout may or may not print. This module
inverts `matricula_ato_detalhes`'s strategy: find every checksum-valid
CPF/CNPJ first, then walk BACKWARD across the formula's own attribute chain
to the name that owns it, then harvest the attributes forward.

The one guard this needs that a labelled reader does not: a `selo digital` /
`protocolo` / `certidão negativa` / `CND` / `processo` number is also an
eleven-or-fourteen-digit run and can, by chance, pass the checksum. Any
document whose immediate left context names one of those is rejected before
a name is even looked for — see `_ISCA_DOCUMENTO`.

🔴 OFFSETS, NEVER TEXT — SAME DISCIPLINE AS THE SIBLING MODULES
------------------------------------------------------------------
`extrair_qualificacoes(text, start, end)` takes the CALLER's full buffer
(typically the whole matrícula transcription) plus a `[start, end)` window
(typically one act's span, from `matricula_atos.segment_matricula_atos`).
`Qualificacao.nome_inicio` / `.nome_fim` are offsets INTO THAT SAME `text` —
not act-relative — so a caller that always passes the same transcription
across every act gets one shared coordinate space, and `mesclar_qualificacoes`
below can point an operator at exactly which act named a field without the
caller re-deriving anything. Every other string field (`nacionalidade`,
`profissao`, `rg`, `endereco`, ...) is, like every sibling module in this
package, a literal substring of `text`, only trimmed at its edges.

🔴 UNKNOWN IS `None`, NEVER A GUESS
-----------------------------------
A field this module is not confident about is `None`. In particular:
`profissao` is free text with no closed vocabulary, so it is only filled
when the text between the known attributes and the RG label is short and
name-shaped; `nacionalidade` only recognises a small closed set of common
adjectives; a genuinely unsupported document layout (no CPF/CNPJ that
survives the checksum + isca guard, or one with no recognisable name before
it) contributes NO `Qualificacao` at all — it is not reported with a
"nenhuma" placeholder the way `matricula_ato_detalhes`'s per-act fields are,
because "no person is anchored here" is not itself a field of a person.

`estado_civil` is normalised to `civil_status.ESTADO_CIVIL_VALORES`'s closed
snake_case vocabulary — the same choice that module makes and for the same
reason (a downstream consumer branches on the VALUE, not the spelling).
Every other text field is read verbatim.

`confianca` (module-wide `ALTA` / `BAIXA`, reused from
`matricula_ato_detalhes`) grades the WHOLE qualification, not a per-field
score: `ALTA` when the formula fired cleanly (an RG was found, and a
nacionalidade or PJ marker anchored the name); `BAIXA` when a name and a
checksum-valid document were still found, but the formula was only partly
present. There is no per-instance `NENHUMA` — see above.

🔴 GENDER FROM GRAMMATICAL AGREEMENT, NOT A GUESS
---------------------------------------------------
Portuguese marks gender on the nationality/estado-civil adjectives
themselves (`brasileira` vs `brasileiro`, `casada` vs `casado`). `_genero`
reads whichever of those agreement points were found and returns `None` on
disagreement — the same "disagreement is absence, not a vote" rule every
sibling parser in this package (`cpf.py`, `birthdate.py`, ...) follows.

🔴 CROSS-ACT MERGE, FIELD-LEVEL PROVENANCE
--------------------------------------------
A later act frequently drops the whole formula and just says "já
qualificados" — the person was fully qualified in an EARLIER act and this
one refers back to them. `mesclar_qualificacoes` merges one extraction's
per-act readings by normalised CPF/CNPJ, FIRST-WRITER-WINS per field (the
same rule `documents/__init__.py`'s module docstring states for
`data_nascimento` — a value already set is never overwritten by a later,
less complete mention), and records which act supplied each field in
`QualificacaoConsolidada.origem` — the platform quotes this into a legal
instrument, and an operator must be able to see where a value came from.
Only pass acts belonging to the SAME extraction; merging across two
different matrículas would silently attribute one person's address to
another's CPF.

All fixture names, CPFs, CNPJs, RGs and addresses in this module's tests are
invented; the CPFs/CNPJs are check-digit-valid synthetic values.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Hashable, Literal, Optional, Sequence

from noctusai_lib.integrations.documents.civil_status import (
    _ESTADO_CIVIL_PALAVRAS,
    _ESTADO_CIVIL_VALOR_RE,
)
from noctusai_lib.integrations.documents.matricula_ato_detalhes import (
    ALTA,
    BAIXA,
    _CNPJ,
    _CPF,
    _FIM_FRASE,
    _PREFIXO_NOME,
    _SEPARA_PESSOA,
    _Texto,
    _digitos,
    _nome_valido,
    cpf_cnpj_valido,
    formatar_cpf_cnpj,
)

# The alternation helper is identical to the sibling's `_rx` — reused, not
# redefined, per this package's own N=2 recurrence rule.
from noctusai_lib.integrations.documents.matricula_ato_detalhes import _rx


@dataclass(frozen=True)
class Qualificacao:
    """One party, read off the document number that anchors them. `nome`,
    `nacionalidade`, `profissao`, `rg`, `rg_orgao_expedidor` and `endereco`
    are literal substrings of the caller's `text` (or `None`); `estado_civil`
    is normalised to `civil_status.ESTADO_CIVIL_VALORES`'s closed vocabulary.
    `nome_inicio` / `nome_fim` are offsets into that same `text` — see the
    module docstring."""

    nome: str
    cpf_cnpj: Optional[str]
    nacionalidade: Optional[str]
    estado_civil: Optional[str]
    profissao: Optional[str]
    rg: Optional[str]
    rg_orgao_expedidor: Optional[str]
    endereco: Optional[str]
    genero: Optional[Literal["m", "f"]]
    nome_inicio: int
    nome_fim: int
    confianca: str

    def to_json(self) -> dict:
        return {
            "nome": self.nome,
            "cpf_cnpj": self.cpf_cnpj,
            "nacionalidade": self.nacionalidade,
            "estado_civil": self.estado_civil,
            "profissao": self.profissao,
            "rg": self.rg,
            "rg_orgao_expedidor": self.rg_orgao_expedidor,
            "endereco": self.endereco,
            "genero": self.genero,
            "nome_inicio": self.nome_inicio,
            "nome_fim": self.nome_fim,
            "confianca": self.confianca,
        }


@dataclass(frozen=True)
class QualificacaoConsolidada:
    """One person, merged across every act of ONE extraction that named
    them. `origem[campo]` is whichever `ato_ref` (the caller's own act
    identifier — an act number, an offset, anything hashable) first supplied
    that field — see `mesclar_qualificacoes`."""

    qualificacao: Qualificacao
    origem: dict[str, Hashable]

    def to_json(self) -> dict:
        return {
            "qualificacao": self.qualificacao.to_json(),
            "origem": {k: v for k, v in self.origem.items()},
        }


# ─── documents (reject the selo/protocolo decoys) ─────────────────────────

_ISCA_DOCUMENTO = _rx(
    r"SELO(?:\s+DIGITAL)?|PROTOCOLO|PROT\.?|CERTIDAO\s+NEGATIVA|CND|PROCESSO"
)
_JANELA_ISCA = 40


def _isca_imediata(antes: str, rotulo_fim: int) -> bool:
    """Only whitespace/colon between an isca label's end and the candidate
    document — an isca label further BACK, with a DIFFERENT number's digits
    sitting in between, does not apply to THIS document. Without this, a
    real CPF that simply follows a `Selo digital:` decoy a few words later
    in the same sentence gets rejected right along with the decoy."""
    return re.fullmatch(r"[\s:]*", antes[rotulo_fim:]) is not None


def _documentos_validos(norm: str) -> list["re.Match[str]"]:
    """Every checksum-valid CPF/CNPJ in `norm`, isca-guarded, ordered, with
    a CPF-shaped submatch of an already-found CNPJ dropped (they overlap on
    the same digit run)."""
    achados: list["re.Match[str]"] = []
    for rx in (_CNPJ, _CPF):
        for m in rx.finditer(norm):
            if not cpf_cnpj_valido(m.group(1)):
                continue
            antes = norm[max(0, m.start() - _JANELA_ISCA) : m.start()]
            if any(
                _isca_imediata(antes, rot.end()) for rot in _ISCA_DOCUMENTO.finditer(antes)
            ):
                continue
            achados.append(m)
    achados.sort(key=lambda m: m.start())
    saida: list["re.Match[str]"] = []
    for m in achados:
        if any(o.start() <= m.start() and m.end() <= o.end() and o is not m for o in achados):
            continue  # a CPF-shaped run inside an already-counted CNPJ
        saida.append(m)
    return saida


def _ancoras(norm: str, documentos: Sequence["re.Match[str]"]) -> list[int]:
    """Per-document lower bound for its own qualification: the rightmost of
    block-start / the previous document's end / a `_SEPARA_PESSOA` match
    (semicolon, spouse-chain, numbered list) that sits before it."""
    separadores = [m.end() for m in _SEPARA_PESSOA.finditer(norm)]
    saida: list[int] = []
    for i, doc in enumerate(documentos):
        candidatos = [0]
        if i > 0:
            candidatos.append(documentos[i - 1].end())
        candidatos.extend(s for s in separadores if s <= doc.start())
        saida.append(max(c for c in candidatos if c <= doc.start()))
    return saida


# ─── name (walk back from the document to the nationality anchor) ─────────

_NACIONALIDADE = _rx(
    r"BRASILEIR[OA]S?|ESTRANGEIR[OA]S?|PORTUGUES[A]?S?|ITALIAN[OA]S?|ESPANHOL[A]?S?"
    r"|ALEMA[O]?S?|JAPONES[A]?S?|NORTE-?AMERICAN[OA]S?|AMERICAN[OA]S?|ARGENTIN[OA]S?"
    r"|URUGUAI[OA]S?|PARAGUAI[OA]S?|BOLIVIAN[OA]S?|CHINES[A]?S?|COREAN[OA]S?|FRANCES[A]?S?"
    r"|INGLES[A]?S?"
)

#: A legal entity's qualification names its TYPE instead of a nationality.
_PJ_MARCADOR = _rx(
    r"SOCIEDADE\s+(?:ANONIMA|LIMITADA|EMPRESARIA(?:\s+LIMITADA)?|SIMPLES|POR\s+ACOES)"
    r"|EIRELI|COOPERATIVA|ASSOCIACAO|FUNDACAO|INSTITUICAO\s+FINANCEIRA|EMPRESA\s+PUBLICA"
    r"|PESSOA\s+JURIDICA"
)

#: "vendido A <nome>" / "transmitiram por permuta o imóvel matriculado A
#: <nome>": a verb, an unbounded-but-capped run of connecting words (the
#: object description), then the preposition a name-boundary formula never
#: has any other reason to sit in front of. This is a NAME-BOUNDARY cue only
#: — it makes no claim about which side of the deal the named person is on;
#: `matricula_ato_detalhes._partes` is where role is decided. Without this,
#: `ancora` is the previous person's boundary (or block start), and the
#: prose of a verb clause sits between it and the name — exactly the prose
#: `_nome_valido`'s shape check cannot, on its own, tell apart from a name.
#: NOC-REMEDIATE[matricula-partes]: covers only "verb ... A <nome>" — a
#: seller introduced as "vendido POR <nome>" (mirrors
#: `matricula_ato_detalhes._NARRATIVA_TRANSMITENTE_VERBO`'s own gap) has no
#: cue here either, so that shape's own CPF/name still resolves off the
#: weaker structural `ancora` alone. Deferred until the real corpus shows
#: it — 2026-09-18
_NOME_INTRODUZIDO = _rx(
    r"(?:VENDID[OA]S?|VENDA|VENDEU|VENDERAM|DOAD[OA]S?|DOACAO|TRANSMITID[OA]S?"
    r"|TRANSMITIU|TRANSMITIRAM|ALIENOU|ALIENARAM|CEDEU|CEDERAM|PERMUTOU|PERMUTARAM"
    r"|DOOU|DOARAM|ADQUIRIU|ADQUIRIRAM|COMPROU|COMPRARAM|ARREMATOU|ARREMATARAM)"
    r"(?:\s+[A-Z]+){0,6}?\s+(?:A|AO|AOS|AS|PARA)"
)


def _ancora_refinada(norm: str, ancora: int, limite: int) -> int:
    """The end of the LAST name-introducing cue before `limite`, if any —
    tighter than the structural `ancora` whenever a verb clause sits
    between them."""
    fim = ancora
    for m in _NOME_INTRODUZIDO.finditer(norm, ancora, limite):
        fim = m.end()
    return fim


def _sem_asteriscos(norm: str, inicio: int, fim: int) -> tuple[int, int]:
    """Legacy transcription rows sometimes wrap a name in `**bold**`
    markup; neither `_PREFIXO_NOME` nor `_nome_valido`'s character class
    know that glyph, so it is stripped here before either sees the span."""
    while inicio < fim and norm[inicio] == "*":
        inicio += 1
    while fim > inicio and norm[fim - 1] == "*":
        fim -= 1
    return inicio, fim


def _nome_pessoa_fisica(norm: str, ancora: int, doc_inicio: int) -> Optional[tuple[int, int]]:
    """The name owning a CPF: the nearest nationality word before it (the
    formula's own second field), and everything name-shaped right before
    THAT — never everything between `ancora` and the document, which would
    just as happily swallow the connecting prose of a verb clause."""
    ancora = _ancora_refinada(norm, ancora, doc_inicio)
    achados = list(_NACIONALIDADE.finditer(norm, ancora, doc_inicio))
    if not achados:
        return None
    fim = achados[-1].start()
    while fim > ancora and norm[fim - 1] in " ,":
        fim -= 1
    p = _PREFIXO_NOME.match(norm, ancora, fim)
    inicio = p.end() if p else ancora
    inicio, fim = _sem_asteriscos(norm, inicio, fim)
    if inicio >= fim or not _nome_valido(norm[inicio:fim], minimo_palavras=2):
        return None
    return inicio, fim


def _nome_pessoa_juridica(norm: str, ancora: int, doc_inicio: int) -> Optional[tuple[int, int]]:
    """The razão social owning a CNPJ: the nearest `sociedade anônima` /
    `LTDA` / ... marker before it, same shape as the PF path."""
    ancora = _ancora_refinada(norm, ancora, doc_inicio)
    achados = list(_PJ_MARCADOR.finditer(norm, ancora, doc_inicio))
    if not achados:
        return None
    fim = achados[-1].start()
    while fim > ancora and norm[fim - 1] in " ,":
        fim -= 1
    p = _PREFIXO_NOME.match(norm, ancora, fim)
    inicio = p.end() if p else ancora
    inicio, fim = _sem_asteriscos(norm, inicio, fim)
    if inicio >= fim or not _nome_valido(norm[inicio:fim], minimo_palavras=1):
        return None
    return inicio, fim


# ─── the attributes between the name and (around) the document ────────────

_MAIOR = re.compile(r"[\s,]*MAIOR(?:ES)?(?:\s+DE\s+IDADE)?[\s,]*")
_PROFISSAO_PARADA = _rx(
    r"CEDULA\s+DE\s+IDENTIDADE|R\.?\s*G\.?|PORTADOR[A]?|INSCRIT[OA]S?"
    r"|CPF|C\.P\.F|CNPJ|C\.N\.P\.J"
)

_RG_ROTULO = _rx(r"CEDULA\s+DE\s+IDENTIDADE|R\.?\s*G\.?")
_RG_CONECTOR = re.compile(r"[\s,:\-–—]*(?:N[ºO°]\.?\s*)?")
#: The real corpus's RG shapes, all anchored on the SAME `num`: bare digits
#: (dotted or not); an optional single-character check digit (`-3`/`-X` —
#: the check digit can BE the letter X, same convention a CPF's own trailing
#: digits never use but an RG's does); an optional órgão, either
#: `SSP/SP`-shaped or a bare 2-letter UF (`-SP`, no `SSP`). The check digit
#: and the órgão are two INDEPENDENT optional groups, not one — a number can
#: carry either, both, or neither, and the órgão's own dash must not be
#: mistaken for the check digit's.
_RG_NUM = re.compile(
    r"(?P<num>\d[\d.]{1,13}\d|\d)"
    r"(?:-(?P<dv>[0-9X]))?"
    r"(?:-(?P<orgao>[A-Z]{2,10}(?:/[A-Z]{2,3})?))?"
)
#: A hyphen-joined OCR/transcription artifact ("...-SELO DIGITAL: ...") is
#: shaped exactly like an órgão (2+ uppercase letters) but is never one —
#: the same decoy class `_ISCA_DOCUMENTO` guards for documents, guarded here
#: for the órgão specifically since the real corpus puts a `Selo digital:`
#: line right after an `RG nº` match in roughly two thirds of acts.
_ORGAO_INVALIDO = frozenset(
    {"SELO", "DIGITAL", "PROTOCOLO", "PROCESSO", "PRENOTACAO", "CERTIDAO", "PROT"}
)

#: `dom`/`dom2` capture the gender-bearing `domiciliad[oa]` word ON ITS OWN
#: — the alternation's tail (`N[AO]`) is the preposition "na"/"no", which
#: ends in the SAME letters for unrelated reasons and would poison a naive
#: "last letter of the whole match" gender read.
_ENDERECO_ROTULO = _rx(
    r"RESIDENTE\s+E\s+(?P<dom>DOMICILIAD[OA])S?\s+N[AO]"
    r"|RESIDENTE\s+N[AO]"
    r"|(?P<dom2>DOMICILIAD[OA])S?\s+N[AO]"
)
#: An address clause runs until whatever comes next stops being an address —
#: most often the act moving on to state the price or a closing formula.
_ENDERECO_PARADA = _rx(
    r"PELO\s+VALOR|NO\s+VALOR|PELA\s+QUANTIA|CONFORME|NOS\s+TERMOS|PARA\s+PAGAMENTO"
)


def _profissao(norm: str, ini: int, fim: int) -> Optional[tuple[int, int]]:
    m_maior = _MAIOR.match(norm, ini, fim)
    ini2 = m_maior.end() if m_maior else ini
    m_parada = _PROFISSAO_PARADA.search(norm, ini2, fim)
    corte = m_parada.start() if m_parada else fim
    bruto = norm[ini2:corte]
    limpo = bruto.strip(" ,;")
    if not limpo:
        return None
    palavras = limpo.split()
    if not (1 <= len(palavras) <= 6) or not re.match(r"^[A-Z' /&.\-]+$", limpo):
        return None
    inicio = ini2 + (len(bruto) - len(bruto.lstrip(" ,;")))
    return inicio, inicio + len(limpo)


def _rg(norm: str, ini: int, fim: int) -> tuple[Optional[tuple[int, int]], Optional[tuple[int, int]]]:
    """(número span, órgão span) — tries every `RG` / `cédula de identidade`
    label in the window, because the "portador da cédula de identidade, RG
    nº ..." phrasing repeats the cue and the NUMBER sits after the second
    one."""
    for m_rot in _RG_ROTULO.finditer(norm, ini, fim):
        pos = m_rot.end()
        m_con = _RG_CONECTOR.match(norm, pos, fim)
        pos2 = m_con.end() if m_con else pos
        m_num = _RG_NUM.match(norm, pos2, fim)
        if m_num:
            # the check digit, when present, is part of the NUMBER — never
            # split off, never dropped.
            fim_num = m_num.end("dv") if m_num.group("dv") else m_num.end("num")
            orgao_texto = m_num.group("orgao")
            orgao_span = None
            if orgao_texto and orgao_texto.split("/")[0] not in _ORGAO_INVALIDO:
                orgao_span = (m_num.start("orgao"), m_num.end("orgao"))
            return (m_num.start("num"), fim_num), orgao_span
    return None, None


def _endereco(norm: str, ini: int, fim: int) -> Optional[tuple[tuple[int, int], Optional[str]]]:
    """(address span, the matched `domiciliad[oa]` word alone) — the word is
    returned separately from the whole rótulo because it, not the trailing
    "na"/"no" preposition, is the address clause's own gender agreement
    point, read by `_genero`."""
    m = _ENDERECO_ROTULO.search(norm, ini, fim)
    if not m:
        return None
    inicio = m.end()
    candidatos = [fim]
    corte_frase = _FIM_FRASE.search(norm, inicio, fim)
    if corte_frase:
        candidatos.append(corte_frase.start())
    corte_parada = _ENDERECO_PARADA.search(norm, inicio, fim)
    if corte_parada:
        candidatos.append(corte_parada.start())
    corte_valor = re.search(r"R\$", norm[inicio:fim])
    if corte_valor:
        candidatos.append(inicio + corte_valor.start())
    fim_endereco = min(candidatos)
    if fim_endereco <= inicio:
        return None
    return (inicio, fim_endereco), (m.group("dom") or m.group("dom2"))


#: Portuguese `-ista`/`-ante`/`-ente` profession nouns are EPICENE — the
#: same spelling for both genders (`o/a motorista`, `o/a dentista`, `o/a
#: gerente`) — so a plain "ends in A" check would read a male "motorista"
#: as feminine. Excluded from `_genero_de_profissao` rather than trusted.
_PROFISSAO_EPICENA = re.compile(r"(?:ISTA|ANTE|ENTE)$")


def _genero_de_profissao(profissao: Optional[str]) -> Optional[str]:
    """The gender-bearing FIRST word of a profession (`corretorA de
    imóveis` -> `corretorA`, `engenheirO civil` -> `engenheirO`), skipped
    when that word's own ending is epicene."""
    if not profissao:
        return None
    primeira = profissao.split()[0].upper() if profissao.split() else ""
    if _PROFISSAO_EPICENA.search(primeira):
        return None
    return primeira


def _genero(*tokens: Optional[str]) -> Optional[Literal["m", "f"]]:
    """Gender from Portuguese grammatical agreement — the same "disagreement
    is absence" rule every sibling parser in this package follows.

    🔴 A trailing plural "s" is stripped before reading the vowel.
    `_NACIONALIDADE` deliberately matches the plural ("ambos BRASILEIROS,
    casados" — a shared, already-qualified pair) — `BRASILEIROS` ends in
    "S", and a naive last-character read would silently agree with
    NEITHER "a" nor "o" and drop a real, unambiguous signal on the floor.
    """
    generos: set[str] = set()
    for tok in tokens:
        if not tok:
            continue
        limpo = tok.rstrip().rstrip(".")
        if len(limpo) > 1 and limpo[-1] == "S":
            limpo = limpo[:-1]
        ultima = limpo[-1:]
        if ultima == "A":
            generos.add("f")
        elif ultima == "O":
            generos.add("m")
    return next(iter(generos)) if len(generos) == 1 else None


# ─── public API ─────────────────────────────────────────────────────────


def extrair_qualificacoes(text: str, start: int, end: int) -> tuple[Qualificacao, ...]:
    """Every party qualified by a checksum-valid CPF/CNPJ in `text[start:end)`.

    `text` is the caller's own buffer (pass the SAME buffer across every
    call so `nome_inicio`/`nome_fim` share one coordinate space — see the
    module docstring); `start`/`end` are typically one act's span."""
    bloco = text[start:end]
    if not bloco.strip():
        return ()
    t = _Texto(bloco)
    norm = t.norm

    documentos = _documentos_validos(norm)
    if not documentos:
        return ()
    ancoras = _ancoras(norm, documentos)

    saida: list[Qualificacao] = []
    for i, doc in enumerate(documentos):
        ancora = ancoras[i]
        janela_fim = ancoras[i + 1] if i + 1 < len(documentos) else len(norm)

        pessoa_fisica = True
        nome_span = _nome_pessoa_fisica(norm, ancora, doc.start())
        if nome_span is None:
            pessoa_fisica = False
            nome_span = _nome_pessoa_juridica(norm, ancora, doc.start())
        if nome_span is None:
            continue
        nome_ini, nome_fim = nome_span
        nome = t.nome(nome_ini, nome_fim)
        if not nome:
            continue

        nacionalidade = estado_civil_raw = estado_civil = profissao = None
        rg = rg_orgao = endereco = None

        if pessoa_fisica:
            nac_m = list(_NACIONALIDADE.finditer(norm, nome_fim, doc.start()))
            atributo_ini = nome_fim
            if nac_m:
                m = nac_m[-1]
                nacionalidade = t.literal(m.start(), m.end())
                atributo_ini = m.end()
            ec_m = _ESTADO_CIVIL_VALOR_RE.search(norm, atributo_ini, doc.start())
            if ec_m:
                estado_civil_raw = norm[ec_m.start() : ec_m.end()]
                estado_civil = _ESTADO_CIVIL_PALAVRAS.get(estado_civil_raw)
                atributo_ini = ec_m.end()
            prof_span = _profissao(norm, atributo_ini, doc.start())
            if prof_span:
                profissao = t.literal(*prof_span)
            rg_span, orgao_span = _rg(norm, atributo_ini, min(doc.start(), janela_fim))
            if rg_span:
                rg = t.literal(*rg_span)
            if orgao_span:
                rg_orgao = t.literal(*orgao_span)

        endereco_achado = _endereco(norm, doc.end(), janela_fim)
        domiciliada_raw = None
        if endereco_achado:
            endereco_span, domiciliada_raw = endereco_achado
            endereco = t.literal(*endereco_span)

        # Gender: the PRIMARY signals are this person's own nacionalidade /
        # estado_civil / profissão-first-word — every one of them matched
        # strictly WITHIN this person's own pre-document attribute window,
        # never in a shared or bled window. The address clause's
        # domiciliad[oa] word is a real signal too (Larissa/Ivanir had
        # nothing BUT a profissão to go on, and an address-only reading is
        # the same shape), but it is a WEAKER one — its window runs from
        # this document to the next person's boundary, which a messier real
        # act can get wrong. It is only CONSULTED when no primary signal
        # fired at all; it never gets to override or "tie-break" a primary
        # read into a false disagreement.
        genero = _genero(
            nacionalidade and nacionalidade.upper(), estado_civil_raw, _genero_de_profissao(profissao)
        )
        if genero is None:
            genero = _genero(domiciliada_raw)

        completo = bool(rg) and bool(nacionalidade or not pessoa_fisica)
        confianca = ALTA if completo else BAIXA

        origem_ini, origem_fim = t.span(nome_ini, nome_fim)
        saida.append(
            Qualificacao(
                nome=nome,
                cpf_cnpj=formatar_cpf_cnpj(doc.group(1)),
                nacionalidade=nacionalidade,
                estado_civil=estado_civil,
                profissao=profissao,
                rg=rg,
                rg_orgao_expedidor=rg_orgao,
                endereco=endereco,
                genero=genero,
                nome_inicio=start + origem_ini,
                nome_fim=start + origem_fim,
                confianca=confianca,
            )
        )
    return tuple(saida)


#: The fields `mesclar_qualificacoes` merges — first writer wins, per field.
_CAMPOS_MESCLAVEIS: tuple[str, ...] = (
    "nome",
    "nacionalidade",
    "estado_civil",
    "profissao",
    "rg",
    "rg_orgao_expedidor",
    "endereco",
    "genero",
)


def mesclar_qualificacoes(
    por_ato: Sequence[tuple[Hashable, Sequence[Qualificacao]]],
) -> tuple[QualificacaoConsolidada, ...]:
    """Merge one extraction's per-act qualificações by normalised CPF/CNPJ.

    `por_ato` is `[(ato_ref, extrair_qualificacoes(...)), ...]` in the acts'
    natural (chronological) order. A field already set by an earlier act is
    never overwritten by a later, less complete mention — the same
    first-writer-wins rule `documents/__init__.py` states for
    `data_nascimento`. `nome_inicio`/`nome_fim` travel with whichever act
    supplied `nome`. Never mix acts from two different extractions into one
    call: the join key is a bare CPF/CNPJ, and a match across extractions
    would silently attribute one person's data to another's document."""
    ordem: list[str] = []
    cpf_cnpj: dict[str, str] = {}
    campos: dict[str, dict[str, Any]] = {}
    origem: dict[str, dict[str, Hashable]] = {}
    offsets: dict[str, tuple[int, int]] = {}
    confiancas: dict[str, str] = {}

    for ato_ref, qualificacoes in por_ato:
        for q in qualificacoes:
            chave = _digitos(q.cpf_cnpj or "")
            if not chave:
                continue
            if chave not in campos:
                ordem.append(chave)
                campos[chave] = {}
                origem[chave] = {}
                cpf_cnpj[chave] = q.cpf_cnpj  # type: ignore[assignment]
            alvo = campos[chave]
            for nome_campo in _CAMPOS_MESCLAVEIS:
                valor = getattr(q, nome_campo)
                if valor is not None and nome_campo not in alvo:
                    alvo[nome_campo] = valor
                    origem[chave][nome_campo] = ato_ref
                    if nome_campo == "nome":
                        offsets[chave] = (q.nome_inicio, q.nome_fim)
                        confiancas[chave] = q.confianca

    saida: list[QualificacaoConsolidada] = []
    for chave in ordem:
        alvo = campos[chave]
        if "nome" not in alvo:
            continue  # a document with no name resolved anywhere: nothing to report
        nome_ini, nome_fim = offsets.get(chave, (0, 0))
        qualificacao = Qualificacao(
            nome=alvo["nome"],
            cpf_cnpj=cpf_cnpj[chave],
            nacionalidade=alvo.get("nacionalidade"),
            estado_civil=alvo.get("estado_civil"),
            profissao=alvo.get("profissao"),
            rg=alvo.get("rg"),
            rg_orgao_expedidor=alvo.get("rg_orgao_expedidor"),
            endereco=alvo.get("endereco"),
            genero=alvo.get("genero"),
            nome_inicio=nome_ini,
            nome_fim=nome_fim,
            confianca=confiancas.get(chave, BAIXA),
        )
        saida.append(QualificacaoConsolidada(qualificacao=qualificacao, origem=dict(origem[chave])))
    return tuple(saida)


__all__ = [
    "Qualificacao",
    "QualificacaoConsolidada",
    "extrair_qualificacoes",
    "mesclar_qualificacoes",
]
