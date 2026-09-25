"""Read an RG (registro geral) number and its issuing body off a document.

Fifth sibling of `birthdate.py`, `name.py`, `gender.py` and `cpf.py`, and the
same shape on purpose: pure, label-anchored, import-free of the rest of the
package, returning `(value, confidence, matched_label)` with confidence as a
plain string — plus `find_rg_orgao(text)` for the issuer, which travels with
the number.

🔴 THE RG IS THE HARDEST OF THE FIVE, AND THE REASON IS STRUCTURAL
-------------------------------------------------------------------
There is no national RG format and no national check digit. Each state issues
its own, so `52.179.965-X` (SP, nine characters, alphanumeric check) and
`M-1.234.567` (MG, letter prefix) and a bare seven-digit number are all valid
RGs. That removes both anchors the other parsers rely on:

- Unlike `cpf`, there is no checksum to verify a candidate against. A run of
  eight digits is just a run of eight digits.
- Unlike `birthdate`, the value has no self-evident structure. A well-formed
  date is itself evidence; `52179965` is equally consistent with an RG, a
  matrícula, a protocol number, a CEP with a suffix, or half a phone number.

So this parser is **label-anchored or nothing**, the same discipline
`gender.py` applies to a bare `M`. There is exactly one exception, and it is
earned by punctuation rather than by a label — see `find_rg`.

🔴 AN UNLABELLED ELEVEN-DIGIT NUMBER THAT PASSES THE CPF CHECK IS NEVER THE RG
-------------------------------------------------------------------------------
Both numbers are printed on the same card, frequently one line apart. Without
this guard, an unlabelled CPF sitting near no RG label at all would be
promoted to a punctuated-shape RG guess — a wrong value that is well-formed,
plausible, and silently overwrites a correct one. The `cpf` module's
validator is the discriminator, and it is the one place this module reaches
outside itself: a shared *pure function*, no package state, so the
import-free property that matters (no cycles, no IO) holds.

🔴 THE GUARD DOES NOT APPLY TO A LABELLED CANDIDATE (2026-09-23)
-------------------------------------------------------------------
A value an explicit RG label anchors is different evidence: the new-model
CNH/CIN convention prints the identity-document number AS the holder's CPF
digits (issuer `IIGDR`) — real, measured 2026-09-23. See `find_rg`'s own
comment at the point this is enforced for the full reasoning; the short
version is that `is_same_as_cpf` exists precisely to flag this case to a
downstream caller, and a value filtered out here never reaches it.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from noctusai_lib.integrations.documents.cpf import is_valid as _cpf_is_valid
from noctusai_lib.integrations.documents.cpf import only_digits as _cpf_only_digits
from noctusai_lib.integrations.documents.labels import Achado, label_before

#: Same window as every sibling — these are the same document layouts.
_LABEL_WINDOW = 48

#: Labels that genuinely introduce the holder's own RG.
_RG_LABELS = (
    "REGISTRO GERAL",
    "CARTEIRA DE IDENTIDADE",
    "CEDULA DE IDENTIDADE",
    "DOC. IDENTIDADE",
    "DOCUMENTO DE IDENTIDADE",
    "IDENTIDADE",
    "R.G",
    "RG",
)

#: Labels that introduce somebody else's number, or a different number.
#:
#: `CPF` is the load-bearing decoy here for the reason in the module docstring.
#: `REGISTRO DE IMOVEIS` and `MATRICULA` matter because this same extractor
#: runs over documents uploaded to a property's file, where an eight-digit
#: number under the word "REGISTRO" is a matrícula, not a person.
_BLOCO_LABELS = (
    "FILIACAO",
    "PAI",
    "MAE",
    "CONJUGE",
    "NOME DA MAE",
    "NOME DO PAI",
    "RESPONSAVEL",
)

#: Labels naming a DIFFERENT KIND of number. `CPF` is the load-bearing one for
#: the reason in the module docstring; `MATRICULA` and `REGISTRO DE IMOVEIS`
#: matter because this same extractor runs over documents uploaded to a
#: property's file, where an eight-digit number is a matrícula, not a person.
_VALOR_LABELS = (
    "CPF",
    "C.P.F",
    "CNPJ",
    "MATRICULA",
    "REGISTRO DE IMOVEIS",
    "PIS",
    "PASEP",
    "CNS",
    "TITULO DE ELEITOR",
    "CERTIDAO",
)

#: `52.179.965-X`, `52.179.965-1`, `52179965X`, `1234567`, `44886493866`.
#:
#: 5–10 digits in the body for the punctuated/checked shapes: below five is
#: not an RG anywhere, and eleven or more with a check suffix is a CPF or
#: something longer. The optional check character is a digit or `X` — `X`
#: is a real check value in São Paulo, not a placeholder.
#:
#: The BARE (no check suffix) run is widened to 5–11: an eleven-digit bare
#: run is ordinarily a CPF, but the new-model CNH/CIN convention prints the
#: identity-document number AS the holder's CPF digits (issuer `IIGDR`) —
#: real, measured 2026-09-23 — and that candidate must reach `find_rg`'s own
#: label-vs-unlabelled split to be judged, not be invisible to the regex
#: before it gets the chance. Safe to widen only here: `find_rg`'s
#: unlabelled arm still runs every eleven-digit bare candidate through
#: `_e_um_cpf` and only a LABELLED one skips that check (see `find_rg`).
#:
#: 🔴 P1/883 live bug (2026-09-24): the dígito verificador's separator gets
#: `\s*` on each side, not a bare `-`. A real CNH's "DOC. IDENTIDADE" value
#: transcribed as `13.032.360 - 3` (a space either side of the dash — a
#: routine vision-transcription artifact, not a malformed document) missed
#: the FIRST alternative below entirely (it required the dash immediately
#: adjacent), fell through to the plain-digits alternative, and matched
#: `13.032.360` — the DV silently dropped, not merely low-confidence.
#: `normalize()` has already collapsed any run of whitespace to a single
#: space by the time this runs, so `\s*` here never eats more than one.
#:
#: The lookarounds stop the pattern from biting a slice out of a longer run.
_RG_RE = re.compile(
    r"(?<![\dXx.\-/])("
    r"\d{1,3}(?:\.\d{3})+\s*-\s*[\dXx]"  # 52.179.965-X / 52.179.965 - X
    r"|\d{1,3}(?:\.\d{3})+"             # 52.179.965
    r"|\d{5,10}\s*-\s*[\dXx]"           # 52179965-X / 52179965 - X
    r"|\d{5,10}[Xx]"                    # 52179965X
    r"|\d{5,11}"                        # 52179965 / 44886493866
    r")(?![\dXx.\-/])"
)

#: The 27 Brazilian state abbreviations. Shared by every UF-shaped match
#: below — `_ORGAO_RE` (issuer adjacent to a UF), `_UF_ROTULO_RE` (a
#: standalone "UF:" sub-field) and `_orgao_rotulado`'s own inline check.
_UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)
_UFS_ALTERNATIVA = "|".join(sorted(_UFS))

#: `SSP/SP`, `SSP-SP`, `SSP SP`, `DETRAN/RJ`, `PC/MG`, `SDS/PE`, `IFP/RJ`.
#: The issuer is 2–8 letters, the UF exactly two.
#: 🔴 THE SEPARATOR IS MANDATORY, and that is not cosmetic. With it optional,
#: `[A-Z]{2,8}` happily splits a single word: `NATURAL` matched as `NATUR` +
#: `AL` (Alagoas), yielding a confident `NATUR/AL` issuer out of an address
#: line. Requiring a real separator makes the acronym and the UF two tokens.
_ORGAO_RE = re.compile(
    r"\b([A-Z]{2,8})\s*(?:[/\-]\s*|\s+)(" + _UFS_ALTERNATIVA + r")\b"
)

#: Words that precede a state abbreviation without being an issuing body —
#: an address line ending in a city and UF is the common one.
_ORGAO_NAO = frozenset({
    "NASCIDO", "NATURAL", "NATURALIDADE", "CIDADE", "MUNICIPIO",
    "BAIRRO", "RUA", "AV", "AVENIDA", "CEP", "UF", "EM", "DE", "DO", "DA",
})

#: A short window immediately BEFORE an issuer-shaped match. When it carries
#: one of these, the match is a JURISDICTION or BIRTHPLACE reference — the
#: notary office/comarca administering a document, or the city a CNH's own
#: "DATA, LOCAL E UF DE NASCIMENTO" field prints — not an issuing BODY.
#: "Comarca de Cotia/SP" is the address of the cartório that produced a
#: certidão; "16/02/1997 SAO PAULO/SP" under a NASCIMENTO field is where the
#: holder was BORN. Neither identifies who issues an RG. Distinct from
#: `_ORGAO_NAO` (which rejects by the CAPTURED WORD itself, e.g. `NATURAL`):
#: this rejects by the WORD(S) BEFORE it, because "COTIA" / "PAULO" are
#: ordinary place names with no reason to be on that blocklist otherwise.
#: `NASCIMENTO`/`NATURALIDADE` joined 2026-09-23 — real, measured: a CNH's
#: birthplace line ("SAO PAULO/SP") was misread as the issuing body when no
#: real issuer acronym sat adjacent to the RG number on that same document.
_ORGAO_CONTEXTO_JURISDICAO = (
    "COMARCA", "TABELIONATO", "CARTORIO", "SERVENTIA", "NASCIMENTO", "NATURALIDADE",
)
_JURISDICAO_WINDOW = 40


def normalize(text: str) -> str:
    """Upper-case, accent-stripped, whitespace-collapsed. As the siblings do."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped.upper())


def only_alnum(value: str) -> str:
    """Digits and letters, punctuation dropped, upper-cased.

    Mirrors `social_wiring.normalizar_documento()` so a value compared in the
    database and a value compared here reduce identically.
    """
    return re.sub(r"[^0-9A-Z]", "", (value or "").upper())


def _label_before(haystack: str, at: int) -> Achado:
    """Delegate to the shared label window — see `labels.py`.

    The end-position-then-length rule there is what makes `CARTEIRA DE
    IDENTIDADE` win over the `IDENTIDADE` nested inside it.
    """
    return label_before(
        haystack,
        at,
        labels=_RG_LABELS,
        blocos=_BLOCO_LABELS,
        valores=_VALOR_LABELS,
        window=_LABEL_WINDOW,
    )


def _e_um_cpf(bruto: str) -> bool:
    """Is this candidate actually the CPF printed on the same card?

    See the module docstring — this is the guard that stops an UNLABELLED
    CPF from being promoted to a punctuated-shape RG guess. `find_rg` calls
    this only for candidates with no RG label anchoring them; a labelled
    candidate is a different question this function does not answer.
    """
    apenas_digitos = re.sub(r"\D", "", bruto)
    return len(apenas_digitos) == 11 and _cpf_is_valid(apenas_digitos)


def find_rg(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract the holder's RG number.

    Returns `(value, confidence, matched_label)`, the value **verbatim as
    printed** (`52.179.965-X`), confidence one of `"alta"` / `"baixa"` /
    `"nenhuma"`.

    - **alta** — label-anchored, and every labelled reading agrees.
    - **baixa** — unlabelled, but punctuated in the RG's own shape
      (`52.179.965-X`: dotted thousands plus a check character). That
      punctuation is the one piece of self-evidence an RG carries; a bare run
      of digits has none, so it is rejected outright rather than downgraded.
    - **nenhuma** — nothing, or readings that disagree. Disagreement is
      reported as absence, never resolved by preferring one.

    🔴 The value is NOT reformatted, unlike `cpf.find_cpf`. There is no
    canonical RG format to normalise to — imposing São Paulo's dotted form on
    a Minas Gerais number would invent punctuation the document does not
    have. Comparison is `only_alnum`'s job; storage keeps what was printed —
    with ONE narrow exception: a space either side of the DV's dash
    (`13.032.360 - 3`) is collapsed to `13.032.360-3`. That whitespace is a
    transcription artifact, never something printed on the card, and
    leaving it in was the P1/883 live bug's proximate cause — see `_RG_RE`.
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma", None)

    rotulados: list[tuple[str, str]] = []
    pontuados: list[str] = []

    for m in _RG_RE.finditer(norm):
        # A space either side of the DV's dash is transcription noise, not
        # something printed on the card — collapse it so the stored value
        # is `13.032.360-3`, not `13.032.360 - 3`. The dotted thousands
        # stay untouched (that punctuation choice IS the document's own).
        bruto = re.sub(r"\s*-\s*", "-", m.group(1))

        achado = _label_before(norm, m.start())
        if achado.rejeitado:
            continue

        if achado.rotulo:
            # 🔴 THE CPF-SHAPE GUARD DOES NOT APPLY HERE, AND THAT IS
            # DELIBERATE (2026-09-23). It exists for the UNLABELLED case
            # below — a bare digit run near no RG label at all must not be
            # silently promoted just because it happens to validate as a
            # CPF. A candidate an explicit RG label anchors is different
            # evidence entirely: the new-model CNH/CIN convention prints
            # the identity-document number AS the holder's CPF digits under
            # `DOC IDENTIDADE / ORG. EMISSOR / UF` (issuer `IIGDR`) — real,
            # measured 2026-09-23 (a "CNH Digital" PDF whose 4c field reads
            # `44886493866 SP`, the same eleven digits as the 4d `CPF`
            # field two lines below). Filtering it out here before the
            # label even gets to say so silently dropped a real, well-
            # evidenced RG — the exact class `rg.is_same_as_cpf`'s own
            # docstring already anticipates ("a real CIN holder's RG
            # legitimately equals their CPF... nothing in this module
            # refuses a write over it") but which a value that never
            # SURVIVES to be compared can never reach. A labelled reading
            # that is ALSO the CPF is a fact for `is_same_as_cpf` to flag
            # downstream, not a reason to discard it upstream.
            #
            # A labelled RG inside a filiação block is ambiguous, not wrong.
            # It joins the punctuated (low-confidence) pile rather than the
            # trusted one, so a human confirms whose document it is.
            if achado.rebaixado:
                pontuados.append(bruto)
            else:
                rotulados.append((bruto, achado.rotulo))
            continue

        if _e_um_cpf(bruto):
            continue

        # Unlabelled: only the fully punctuated shape survives. Dotted
        # thousands AND a check character — either alone is too common.
        if "." in bruto and "-" in bruto:
            pontuados.append(bruto)

    if rotulados:
        distintos = {only_alnum(v) for v, _ in rotulados}
        if len(distintos) == 1:
            return (rotulados[0][0], "alta", rotulados[0][1])
        return (None, "nenhuma", None)

    if pontuados:
        distintos = {only_alnum(v) for v in pontuados}
        if len(distintos) == 1:
            return (pontuados[0], "baixa", None)

    return (None, "nenhuma", None)


#: How far AFTER the RG number an issuer may sit and still be "its" issuer.
#: Every Brazilian layout prints the pair on one line — `13032360 SSP/SP`
#: (CNH field 4c), `52.179.965-X SSP-SP` (a contract qualification) — so a
#: short window is enough, and a short window is what keeps a birthplace or
#: an address line two fields later from being read as the issuer.
_ADJACENTE_WINDOW = 24


#: How far AFTER an explicit "ÓRG. EMISSOR" label its own value, and a
#: separately-labelled "UF", may sit — wide enough to span a CNH-e's own
#: `DOC. IDENTIDADE / ÓRG. EMISSOR / UF` box once `normalize()` collapses its
#: three column labels onto one line.
_ORGAO_ROTULO_WINDOW = 40

#: The CNH-e's own field label. Matches "ÓRG. EMISSOR"/"ÓRGÃO EMISSOR"
#: (accent already stripped by `normalize()` -> "ORG"/"ORGAO"), "ORG.
#: EMISSOR" and the bare "ORG EMISSOR".
_ORGAO_ROTULO_RE = re.compile(r"\bORG(?:AO)?\.?\s*EMISSOR\b\s*[:.\-]?\s*")

#: A standalone "UF: SP" sub-field — the third column of the same box.
_UF_ROTULO_RE = re.compile(r"\bUF\s*[:.\-]?\s*(" + _UFS_ALTERNATIVA + r")\b")


def _orgao_rotulado(norm: str) -> Optional[str]:
    """`ÓRG. EMISSOR: SSP` (plus a separately-labelled `UF: SP`, or the UF
    printed right after the acronym), or `None`.

    🔴 THE SHAPE SCAN CANNOT SEE THIS BOX. `_ORGAO_RE`/`_orgao_adjacente`
    read the issuer off its PRINTED SHAPE — an acronym immediately touching
    a UF, `SSP/SP`. A CNH-e's own `DOC. IDENTIDADE / ÓRG. EMISSOR / UF` field
    prints the acronym and the UF as TWO SEPARATE labelled sub-fields, one
    per column — real, measured, P1/883 2026-09-25: once
    `_IDENTITY_DOCUMENT_PROMPT` actually reaches the vision call for a PDF
    (see `media.real_adapter.RealMediaResolver._doc_prompt_override`), the
    transcription preserves each column as its own `RÓTULO: valor` line, and
    a shape scan sees no two tokens touching. An explicit label is stronger
    evidence than the shape guess anyway — the same reason every other
    labelled reading in this package outranks an unlabelled one.
    """
    m = _ORGAO_ROTULO_RE.search(norm)
    if not m:
        return None
    janela = norm[m.end() : m.end() + _ORGAO_ROTULO_WINDOW]
    mv = re.match(r"([A-Z]{2,8})\b", janela)
    if not mv:
        return None
    orgao = mv.group(1)
    if orgao in _ORGAO_NAO:
        return None
    # The UF printed right after the acronym on the SAME line — the
    # ordinary adjacent shape, just reached through the label this time
    # ("ÓRG. EMISSOR: SSP/SP", "ÓRG. EMISSOR: SSP SP").
    resto = janela[mv.end():]
    minline = re.match(r"\s*(?:[/\-]\s*|\s+)([A-Z]{2})\b", resto)
    if minline and minline.group(1) in _UFS:
        return f"{orgao}/{minline.group(1)}"
    # The UF as its OWN labelled sub-field, a few tokens later — the box's
    # third column.
    muf = _UF_ROTULO_RE.search(janela)
    if muf:
        return f"{orgao}/{muf.group(1)}"
    return None


def _orgao_valido(norm: str, m: "re.Match[str]") -> Optional[str]:
    """`ORGAO/UF` for an issuer-shaped match, or None when it is a
    place name / jurisdiction rather than an issuing body."""
    orgao, uf = m.group(1), m.group(2)
    if orgao in _ORGAO_NAO or orgao == uf:
        return None
    janela = norm[max(0, m.start() - _JURISDICAO_WINDOW) : m.start()]
    if any(p in janela for p in _ORGAO_CONTEXTO_JURISDICAO):
        return None
    return f"{orgao}/{uf}"


def _orgao_adjacente(norm: str, rg: str) -> Optional[str]:
    """The issuer printed immediately after this RG number, if any.

    🔴 WHY ADJACENCY BEATS "FIRST MATCH". A CNH carries field 3 — "DATA,
    LOCAL E UF DE NASCIMENTO: 20/04/1964 SAO PAULO/SP" — ABOVE field 4c,
    "13032360 SSP/SP". Scanning by shape alone, `PAULO/SP` is issuer-shaped
    and comes first, so the old rule returned a city as the issuing body at
    `baixa` — which the source-tempering then dropped, storing the RG with
    NO issuer at all (live: Regina Maria Pelosi's CNH, 2026-09-21). The
    number itself says where its issuer is: right beside it.
    """
    alvo = only_alnum(rg)
    if not alvo:
        return None
    for m in _RG_RE.finditer(norm):
        if only_alnum(m.group(1)) != alvo:
            continue
        fim = m.end()
        trecho = norm[fim : fim + _ADJACENTE_WINDOW]
        o = _ORGAO_RE.search(trecho)
        # Only separators may stand between the number and the issuer —
        # "13032360 SSP/SP", "52.179.965-X - SSP-SP" — never another word.
        if o is not None and re.fullmatch(r"[\s\-/,]*", trecho[: o.start()]):
            valido = _orgao_valido(trecho, o)
            if valido is not None:
                return valido
    return None


def find_rg_orgao(text: str, rg: Optional[str] = None) -> tuple[Optional[str], str]:
    """Extract the issuing body and UF — `SSP/SP`.

    When `rg` is given (the number `find_rg` read off the same text), the
    issuer printed right after that number wins at `alta` — see
    `_orgao_adjacente`. Only when there is no adjacent issuer does the
    shape-scan below run; only when THAT finds nothing either does the
    explicit `ÓRG. EMISSOR` label (`_orgao_rotulado`) get a turn.

    Returns `(value, confidence)`. A shape-scan match carries no matched
    label to report (the issuer is identified by its own SHAPE, not by a
    label preceding it); a `_orgao_rotulado` match DOES have one but is
    reported the same shape as every sibling here for a uniform contract.

    - **alta** — exactly one issuer-shaped token in the text, OR an explicit
      `ÓRG. EMISSOR` label with its own value.
    - **baixa** — several shape-scan matches that disagree. The FIRST is
      returned rather than nothing, because on these layouts the issuer is
      printed adjacent to the RG and the later matches are almost always an
      address line; a human confirms. This is the one place in the family
      where a disagreement is not reported as absence, and the reason is
      that the alternative — an RG number stored with no issuer — is itself
      an incomplete qualification.
    - **nenhuma** — none.

    Normalised to `ORGAO/UF` regardless of the separator printed.
    """
    norm = normalize(text or "")
    if not norm:
        return (None, "nenhuma")

    if rg:
        adjacente = _orgao_adjacente(norm, rg)
        if adjacente is not None:
            return (adjacente, "alta")

    achados: list[str] = []
    for m in _ORGAO_RE.finditer(norm):
        valido = _orgao_valido(norm, m)
        if valido is not None:
            achados.append(valido)

    if achados:
        if len(set(achados)) == 1:
            return (achados[0], "alta")
        return (achados[0], "baixa")

    # 🔴 P1/883 (2026-09-25): a CNH-e's own `DOC. IDENTIDADE / ÓRG. EMISSOR /
    # UF` box prints the acronym and the UF as two SEPARATE labelled
    # sub-fields — see `_orgao_rotulado`'s own docstring for the full
    # reasoning. Tried last, after both shape-based routes, because an
    # explicit label here is narrower evidence (one specific field name)
    # than the general acronym/UF shape every other Brazilian layout uses.
    rotulado = _orgao_rotulado(norm)
    if rotulado is not None:
        return (rotulado, "alta")

    return (None, "nenhuma")


def is_same_as_cpf(rg: Optional[str], cpf: Optional[str]) -> bool:
    """Does this RG collapse onto this CPF once punctuation is dropped?

    🔴 THE REAL BUG THIS GUARDS AGAINST
    -------------------------------------
    A qualificação form (or a copy-paste import) puts the CPF into the RG
    field verbatim — a signatory's card is on file, the operator opens two
    boxes, and the same eleven digits land in both. Nothing about either
    value is individually wrong: the CPF is a real, valid CPF; the "RG" is
    the right *shape* for one of the many states that issue bare numeric
    RGs. Only comparing the two catches it.

    `only_alnum` is the RG's own comparison form (mirrors
    `social_wiring.normalizar_documento`); a CPF run through it strips to
    the same eleven characters `cpf.only_digits` produces, since a CPF's
    only punctuation is dots and a dash. Comparing the two normalised forms
    therefore catches the copy regardless of which field carried the
    punctuation, or whether either did.

    Either value missing returns `False` — there is nothing to compare, and
    "nothing" is not "the same".

    🔴 THIS FUNCTION DETECTS; IT DOES NOT REFUSE (2026-09-22). A collision is
    not always the copy-paste bug above: the Carteira de Identidade Nacional
    (CIN) uses the CPF number AS the identity number by design, so a real
    CIN holder's RG legitimately equals their CPF. Callers decide what to do
    with `True` — `social_wiring`'s contract-generation gate surfaces it as
    an operator-confirmable warning, never a hard block; nothing in this
    module (or its consumers, as of the date above) refuses a write over it.
    """
    if not rg or not cpf:
        return False
    return only_alnum(rg) == _cpf_only_digits(cpf)


__all__ = ["find_rg", "find_rg_orgao", "is_same_as_cpf", "normalize", "only_alnum"]
