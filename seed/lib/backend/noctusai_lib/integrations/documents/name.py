"""Label-anchored full-name extraction from Brazilian identity-document text.

Pure — no IO, no LLM, no network. Text in, name and confidence out.

WHY THIS IS HARDER THAN THE DATE
--------------------------------
A date is self-delimiting: `12/05/1980` is recognisable as a date with no
context at all, so `birthdate` can find every candidate first and use
labels only to CHOOSE between them. A name has no shape. `FULANO DE TAL
SILVA` and `SECRETARIA DE SEGURANCA PUBLICA` are the same kind of string
to a regex. So here the label is not a tie-breaker, it is the ONLY
evidence — an unlabelled line is never read as a name, at any confidence.

THE DECOY THAT MATTERS: FILIAÇÃO
--------------------------------
Every Brazilian RG prints the holder's name and then, directly beneath it,
the names of BOTH PARENTS under `FILIAÇÃO`. Those are real, perfectly
well-formed Brazilian full names sitting two lines from the right answer.
Any approach that scores "does this look like a name?" picks one of them a
large fraction of the time — and produces a plausible human name, so
nothing downstream can tell it went wrong.

Two independent guards therefore exist, and both are load-bearing:

1. Labels like `NOME DO PAI` / `NOME DA MAE` are matched LONGEST-FIRST, so
   they are recognised as decoys rather than as the bare `NOME` nested
   inside them.
2. A `FILIAÇÃO` header poisons the lines that follow it, because the
   common layout puts the parents on their own unlabelled lines under it.

THE INSTITUTIONAL BLOCKLIST
---------------------------
ID documents are covered in official phrases that pass every structural
name test: `REPUBLICA FEDERATIVA DO BRASIL`, `SECRETARIA DE SEGURANCA
PUBLICA`, `CADASTRO DE PESSOAS FISICAS`. They are rejected by name rather
than by cleverness, because a heuristic that could tell them apart from a
person's name would be a heuristic that sometimes rejects real people.

ONE DELIBERATE OMISSION
-----------------------
**No unlabelled fallback.** `birthdate` will return a lone plausible date
at `baixa` when nothing is labelled. The equivalent here would be "the
longest name-shaped line", which on an RG is frequently a parent. Absence
is reported instead.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from noctusai_lib.integrations.documents.text import normalize_lines, strip_accents_upper

#: Bounds on a stored name. The floor rejects label noise (`RG`, `ID`);
#: the ceiling rejects a run-on line that swallowed the next field.
MIN_NAME_LEN = 4
MAX_NAME_LEN = 80
MIN_WORDS = 2
MAX_WORDS = 8

#: Portuguese name particles. They are the reason a plain "every word must
#: be at least two letters" rule does not work — `FULANO E SILVA` is a
#: real name shape.
_PARTICLES = frozenset({"DA", "DE", "DO", "DAS", "DOS", "E", "D", "DI", "DU", "VON", "VAN"})

#: Labels that introduce the DOCUMENT HOLDER's name. Order is irrelevant;
#: `_label_at` always takes the longest match at a position.
_NAME_LABELS = (
    "NOME COMPLETO",
    "NOME E SOBRENOME",
    "NOME CIVIL",
    "NOME",
)

#: A certidão de casamento's "nome que passou a adotar" clause can state
#: each spouse's post-marriage name under the PRONOUN, not `NOME`
#: (`Ele: <nome dele>` / `Ela: <nome dela>`, one per line). Kept
#: OUT of `_NAME_LABELS`: `ELE`/`ELA` are common Portuguese words, so
#: `_candidatos` below requires an EXPLICIT separator (`:` or `-`)
#: immediately after the label before treating the tail as a value — a bare
#: `ELE COMPARECEU PERANTE O OFICIAL` never reaches this path. The
#: word-boundary fix on `_label_at` (below) is what makes recognising a
#: 3-letter label safe at all — without it `ELE`/`ELA` match mid-word
#: (`AQUELE`, `PELA`, `JANELA`).
_PRONOUN_NAME_LABELS = ("ELE", "ELA")

#: A certidão de casamento's own convention: ONE header over TWO co-equal
#: names (the spouses), unlike an RG/CNH's singular "NOME" over one. It is a
#: SEPARATE set, not folded into `_NAME_LABELS`, because it is handled by a
#: different code path below — see `_MULTI_HOLDER_LABELS`'s use in
#: `find_name`. `_label_at`'s word-boundary rule already stops "NOME" from
#: matching inside it, so without this entry a certidão's header is simply
#: invisible to this parser — see the module's own header comment on the
#: defect this fixes.
_MULTI_HOLDER_LABELS = (
    "NOMES",
    # Newer CRC layouts head the same block "Nome atual dos cônjuges". Without
    # these, longest-match found only the bare `NOME` and read the heading's
    # own tail — "ATUAL DOS CONJUGES" — as the holder's name (live, a real
    # certidão, 2026-09-21).
    "NOME ATUAL DOS CONJUGES",
    "NOMES ATUAIS DOS CONJUGES",
    "NOME DOS CONJUGES",
    "NOMES DOS CONJUGES",
)

#: Labels that introduce SOMEONE ELSE's name, or a name-shaped value that
#: is not a person. Longest-first matching is what makes these win over
#: the bare `NOME` they contain.
_DECOY_NAME_LABELS = (
    "NOME DO PAI",
    "NOME DA MAE",
    "NOME DO CONJUGE",
    "NOME DA MAE OU PAI",
    "NOME DO RESPONSAVEL",
    "NOME DO ORGAO",
    "NOME DA EMPRESA",
    "NOME DO AGENTE",
    "NOME EMPRESARIAL",
    "NOME FANTASIA",
    "FILIACAO",
    "PAI",
    "MAE",
    "CONJUGE",
    "RESPONSAVEL",
)

#: Lines that begin a section whose following lines are other people.
_POISONING_HEADERS = ("FILIACAO",)

#: How many lines after a poisoning header stay poisoned. Two, because a
#: Brazilian RG lists exactly two parents.
_POISON_SPAN = 2

#: Official phrases that are structurally indistinguishable from names.
_INSTITUTIONAL = frozenset(
    {
        "REPUBLICA FEDERATIVA DO BRASIL",
        "MINISTERIO DA FAZENDA",
        "MINISTERIO DA ECONOMIA",
        "SECRETARIA DA RECEITA FEDERAL",
        "RECEITA FEDERAL",
        "CADASTRO DE PESSOAS FISICAS",
        "SECRETARIA DE SEGURANCA PUBLICA",
        "SECRETARIA DE ESTADO DA SEGURANCA PUBLICA",
        "INSTITUTO DE IDENTIFICACAO",
        "CARTEIRA DE IDENTIDADE",
        "REGISTRO GERAL",
        "REGISTRO NACIONAL",
        "VALIDA EM TODO O TERRITORIO NACIONAL",
        "DOCUMENTO DE IDENTIDADE",
        "CARTEIRA NACIONAL DE HABILITACAO",
        "DEPARTAMENTO DE TRANSITO",
        "LEI N 7 116 DE 29 08 83",
        "ASSINATURA DO TITULAR",
        "POLEGAR DIREITO",
    }
)

#: Words that never appear inside a personal name but do appear in the
#: institutional strings above. A second, cheaper net for phrasings the
#: exact blocklist has not seen.
_INSTITUTIONAL_TOKENS = frozenset(
    {
        "REPUBLICA", "FEDERATIVA", "MINISTERIO", "SECRETARIA", "RECEITA",
        "CADASTRO", "PESSOAS", "FISICAS", "SEGURANCA", "PUBLICA", "INSTITUTO",
        "IDENTIFICACAO", "CARTEIRA", "IDENTIDADE", "REGISTRO", "NACIONAL",
        "TERRITORIO", "DOCUMENTO", "HABILITACAO", "DEPARTAMENTO", "TRANSITO",
        "ASSINATURA", "TITULAR", "POLEGAR", "VALIDA", "VALIDO", "EXPEDICAO",
        "EMISSAO", "VALIDADE", "NATURALIDADE", "FILIACAO", "ORGAO", "EMISSOR",
        "ESTADO", "MUNICIPIO", "COMARCA", "CARTORIO", "LIVRO", "FOLHA", "TERMO",
        "OBSERVACOES", "ASSINADO", "DIGITALMENTE",
        # Field labels that are name-SHAPED ("Número do CPF" is three
        # letters-only words) and sit inside a certidão's holder block.
        "CPF", "NUMERO", "MATRICULA",
    }
)

#: Characters a Brazilian personal name may contain once accents are
#: stripped. Digits are absent on purpose — a "name" with a digit in it is
#: a misread label or a document number.
_NAME_CHARS = re.compile(r"^[A-Z' -]+$")

#: Separators that sit between a label and its value. `*` joined 2026-09-23:
#: a real cartório template (`CERTIDÃO DE CASAMENTO`, `NOMES:` block) wraps
#: every printed value in a footnote asterisk — `* CAIO BRAGANTIN SPOLTORE
#: *` — which `_NAME_CHARS` correctly refuses to treat as part of the name
#: itself; without it here, the leading/trailing `*` alone was enough to
#: fail the shape check on an otherwise well-formed, label-anchored name.
_SEPARATORS = " :\t-–—.|*"


def _label_at(line: str, pos: int) -> tuple[Optional[str], bool]:
    """Longest label starting at `pos`, and whether it is a decoy.

    Longest-first is the entire defence against `NOME DO PAI` being read
    as `NOME` followed by a value of `DO PAI`.

    🔴 BOTH ENDS OF THE LABEL MUST SIT ON A WORD BOUNDARY, NOT JUST THE
    RIGHT ONE. The original rule only checked the character AFTER the
    match (`NOMEACAO` must not match `NOME`) — a match starting mid-word
    was never excluded, because every existing label was long/distinctive
    enough that it never came up. It matters now: `ELE`/`ELA`
    (`_PRONOUN_NAME_LABELS`) are common Portuguese word FRAGMENTS —
    `AQUELE`, `PELA`, `JANELA` all contain one verbatim — so a short label
    is only safe to add once a mid-word start is rejected here, for every
    label, not merely the new ones.
    """
    if pos > 0 and (line[pos - 1].isalnum() or line[pos - 1] == "'"):
        return (None, False)
    best: tuple[str, bool] | None = None
    for label, is_decoy in (
        [(x, True) for x in _DECOY_NAME_LABELS]
        + [(x, False) for x in _NAME_LABELS]
        + [(x, False) for x in _MULTI_HOLDER_LABELS]
        + [(x, False) for x in _PRONOUN_NAME_LABELS]
    ):
        if not line.startswith(label, pos):
            continue
        # A label must end at a word boundary, else `NOMEACAO` matches `NOME`.
        end = pos + len(label)
        if end < len(line) and line[end].isalnum():
            continue
        if best is None or len(label) > len(best[0]):
            best = (label, is_decoy)
    return best if best is not None else (None, False)


def _find_label(line: str) -> tuple[Optional[str], bool, int]:
    """First label occurring in `line`, its decoy flag, and where it ends."""
    for i in range(len(line)):
        label, is_decoy = _label_at(line, i)
        if label is not None:
            return (label, is_decoy, i + len(label))
    return (None, False, -1)


def looks_like_a_name(candidate: str) -> bool:
    """Structural plausibility for a Brazilian personal name.

    Deliberately strict. A false accept writes a wrong name onto a client
    record; a false reject leaves a field empty, which is visible.

    Normalises its own input, so callers outside this module (the checklist
    derivation asks "is this registration value a full name?") can pass raw
    mixed-case, accented text. `find_name` passes text that is already
    normalised, and normalisation is idempotent.
    """
    value = " ".join(strip_accents_upper(candidate or "").split())
    value = value.strip(_SEPARATORS).strip()
    if not (MIN_NAME_LEN <= len(value) <= MAX_NAME_LEN):
        return False
    if not _NAME_CHARS.match(value):
        return False
    if value in _INSTITUTIONAL:
        return False

    words = value.split()
    if not (MIN_WORDS <= len(words) <= MAX_WORDS):
        return False
    if any(w in _INSTITUTIONAL_TOKENS for w in words):
        return False

    substantive = [w for w in words if w not in _PARTICLES]
    if len(substantive) < 2:
        return False
    if any(len(w) < 2 for w in substantive):
        return False
    return True


#: A bare CPF-shaped VALUE line (`303.102.653-55` / 11 raw digits), so the
#: multi-holder scan below can skip over it without stopping. Deliberately
#: shape-only — this module stays import-free of `cpf.py` (see the module
#: docstring), so it recognises "this line is a document number", never
#: verifies the check digits.
_CPF_SHAPE_RE = re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$|^\d{11}$")


def _strip_trailing_citation(value: str) -> str:
    """Drop a trailing registry-citation / same-row field-label clause that
    rides on the SAME transcribed line as a real name.

    Two real shapes measured on production certidões (2026-09-23), both
    the same underlying mistake wearing a different label:

    1. A registry citation glued onto the name line —
       `FULANO DE TAL SILVA LIVRO B-123 FOLHA 45 TERMO 6789` — where the
       averbação's own LIVRO/FOLHA/TERMO reference sits on the SAME OCR
       line as the spouse's name.
    2. A wide `NOMES` table where the next column's `CPF` header (or the
       row's own `MATRICULA`/`NUMERO` label) lands on the same visual row
       as a holder's name, so the joined line reads `ROBERTO CASSEMIRO
       DOS SANTOS ... CPF` — one holder's name in a two-spouse certidão,
       the OTHER spouse's row starting fresh below it.

    `looks_like_a_name` correctly rejects either raw line outright (an
    institutional token anywhere in it fails the whole-line check) — but
    the REAL name is right there, unbroken, before the decoration starts.
    Rejecting the whole line throws away well-evidenced holder data for a
    formatting accident, so every candidate line is tried both AS-IS and
    with its trailing institutional-token clause cut before being judged.

    Only ever shortens the TAIL — trimming a prefix decoy would risk
    cutting into the actual name — and only when the trim leaves at least
    one word behind; an all-institutional line still correctly falls
    through unchanged to `looks_like_a_name`'s ordinary rejection.
    """
    words = (value or "").split()
    for i, w in enumerate(words):
        if w in _INSTITUTIONAL_TOKENS and i > 0:
            return " ".join(words[:i])
    return value


def _coleta_titulares_multiplos(
    lines: list[str], start: int, label: str
) -> list[tuple[str, str]]:
    """Every co-equal name under a MULTI-HOLDER header (`NOMES`), starting
    right after it.

    A certidão de casamento's holder block interleaves each spouse's name
    with a `CPF` label and its value (`ALMIR ... / CPF / 303.102.653-55 /
    MARIANA ... / CPF / 478.982.096-30`). This walks PAST those CPF lines
    rather than stopping at the first one, so BOTH names are collected as
    candidates under the SAME label — which is what turns "found nothing"
    into "found two, cannot choose" (see `find_name_conflitos`). It stops at
    the first line that is neither a name nor one of those interleaved
    document-number lines — the next section of the document.
    """
    candidatos: list[tuple[str, str]] = []
    j = start
    while j < len(lines):
        linha = lines[j]
        # See `_strip_trailing_citation`: a wide `NOMES` table routinely
        # lands the NEXT column's `CPF` header on the same visual row as
        # this holder's name — trim it before judging the line, so a real,
        # well-evidenced name is not thrown away for a layout accident.
        candidato = _strip_trailing_citation(linha)
        if looks_like_a_name(candidato):
            candidatos.append((candidato.strip(_SEPARATORS).strip(), label))
            j += 1
            continue
        if linha == "CPF" or _CPF_SHAPE_RE.match(linha):
            j += 1
            continue
        break
    return candidatos


def _candidatos(text: str) -> list[tuple[str, str]]:
    """Every (name, label) candidate on the document, before collapsing more
    than one distinct reading to absence.

    Shared by `find_name` (which collapses) and `find_name_conflitos`
    (which reports the collapse's cause) — see that function's docstring
    for why the split exists.
    """
    lines = normalize_lines(text)
    if not lines:
        return []

    poisoned_until = -1
    candidates: list[tuple[str, str]] = []

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if any(line.startswith(h) for h in _POISONING_HEADERS):
            poisoned_until = idx + _POISON_SPAN
            idx += 1
            continue
        if idx <= poisoned_until:
            idx += 1
            continue

        label, is_decoy, end = _find_label(line)
        if label is None or is_decoy:
            idx += 1
            continue

        if label in _MULTI_HOLDER_LABELS:
            candidates.extend(_coleta_titulares_multiplos(lines, idx + 1, label))
            idx += 1
            continue

        if label in _PRONOUN_NAME_LABELS:
            # `ELE`/`ELA` are ordinary Portuguese words as well as a label —
            # unlike every other entry here, an EXPLICIT separator right
            # after the pronoun is required before its tail is trusted as a
            # value at all ("ELE COMPARECEU..." never reaches `tail`, since
            # nothing follows `ELE` but a space). No next-line fallback for
            # the same reason: a pronoun that starts a SENTENCE, with the
            # actual value nowhere nearby, is the common case for these two
            # words — unlike `NOME`, where a label with no same-line value
            # genuinely means "the value is on the line below".
            if line[end : end + 1] not in ":-":
                idx += 1
                continue
            tail = line[end:].strip(_SEPARATORS).strip()
            tail_candidato = _strip_trailing_citation(tail)
            if tail and looks_like_a_name(tail_candidato):
                candidates.append((tail_candidato, label))
            idx += 1
            continue

        # Value on the same line, e.g. `NOME: FULANO DE TAL`.
        tail = line[end:].strip(_SEPARATORS).strip()
        tail_candidato = _strip_trailing_citation(tail)
        if tail and looks_like_a_name(tail_candidato):
            candidates.append((tail_candidato, label))
            idx += 1
            continue

        # Value on the NEXT line, e.g. `NOME` / `FULANO DE TAL`. Only when
        # the label line carried no value of its own — otherwise a label
        # whose value failed validation would reach past it and claim the
        # following field.
        if not tail and idx + 1 < len(lines):
            nxt = lines[idx + 1]
            nxt_candidato = _strip_trailing_citation(nxt)
            n_label, n_decoy, _ = _find_label(nxt)
            if n_label is None and looks_like_a_name(nxt_candidato):
                candidates.append((nxt_candidato.strip(_SEPARATORS).strip(), label))
        idx += 1

    return candidates


def find_name(text: str) -> tuple[Optional[str], str, Optional[str]]:
    """Extract the document holder's full name.

    Returns `(value, confidence, matched_label)` where confidence is
    `"alta"` / `"nenhuma"` — the string values of
    `types.ExtractionConfidence`, kept as plain strings so this module
    stays import-free of the rest of the package.

    `"baixa"` is never returned from here. A name is either label-anchored
    (in which case the evidence is as good as this parser can get) or it
    is not found. Downgrading to `baixa` on account of the TEXT SOURCE is
    the adapter's job, because only the adapter knows whether the text
    came off a PDF text layer or a vision pass.

    🔴 `nenhuma` HAS TWO DIFFERENT CAUSES, INDISTINGUISHABLE HERE
    ----------------------------------------------------------------
    "The document does not carry a name" and "the document names MORE THAN
    ONE person with equal prominence" (a certidão de casamento's two
    spouses) both collapse to `(None, "nenhuma", None)`. That collapse is
    the right call for THIS function — writing a coin-flip to a single
    `nome` column would be worse than writing nothing — but a caller that
    needs to tell the two apart (to ask "which one?" instead of silently
    doing nothing) should call `find_name_conflitos` instead.
    """
    candidates = _candidatos(text)
    if not candidates:
        return (None, "nenhuma", None)

    distinct = {v for v, _ in candidates}
    if len(distinct) > 1:
        # Two different strings both labelled as the holder's name means
        # the layout was misread — or, under `_MULTI_HOLDER_LABELS`, that
        # the document genuinely names more than one co-equal holder.
        # Either way this function cannot choose. See `find_name_conflitos`.
        return (None, "nenhuma", None)

    value, label = candidates[0]
    return (value, "alta", label)


def find_name_conflitos(text: str) -> Optional[list[str]]:
    """The NAMED reason `find_name` returned `nenhuma`, when the reason is
    ambiguity rather than absence.

    Returns the sorted distinct candidate names when MORE THAN ONE
    equally-labelled holder was found (two labelled names disagreeing, or a
    certidão's `NOMES` block naming two spouses); `None` when there is no
    such ambiguity — the ordinary "not on the document" case, which
    `find_name` already reports correctly on its own and which a caller
    must not re-surface as a fake conflict.
    """
    distinct = sorted({v for v, _ in _candidatos(text)})
    return distinct if len(distinct) > 1 else None


def chave_nome(valor: Optional[str]) -> str:
    """Accent-stripped, upper-cased, whitespace-collapsed — for MATCHING."""
    decomposto = unicodedata.normalize("NFKD", valor or "")
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())


def nomes_compativeis(a: Optional[str], b: Optional[str]) -> bool:
    """Could these two spellings name the same person?

    Equal modulo accents/case/spacing, OR every significant word (>2 letters)
    of one is contained in the other — a registered "REGINA MARIA PELOSI"
    against a certidão's maiden name "REGINA MARIA PELOSI RANGEL". The single
    definition of "same name" for every consumer that has to decide whether a
    document belongs to a person (the titular hint, a spouse, a comprovante's
    printed holder). Word containment only — a shared surname alone ("SILVA")
    never matches two different people, because every word of the shorter
    name must appear in the longer.
    """
    ka, kb = chave_nome(a), chave_nome(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    pa = {p for p in ka.split() if len(p) > 2}
    pb = {p for p in kb.split() if len(p) > 2}
    return bool(pa and pb and len(min(pa, pb, key=len)) >= 2 and (pa <= pb or pb <= pa))


__all__ = [
    "chave_nome",
    "nomes_compativeis",
    "MAX_NAME_LEN",
    "MAX_WORDS",
    "MIN_NAME_LEN",
    "MIN_WORDS",
    "find_name",
    "find_name_conflitos",
    "looks_like_a_name",
]
