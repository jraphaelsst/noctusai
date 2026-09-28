"""Legibilidade (readability) assessment over a document transcription.

OWNER DECISION (2026-09-28, verbatim intent): "when a document's readability
is compromised, we'll warn on the human-gate review, so humans are aware the
doc is risky and readability is compromised — human check is mandatory."

🔴 THE MEASURED FAILURE THIS CLOSES
------------------------------------
A phone SCREENSHOT of the CNH Digital app (the card small in frame) put the
holder's identity through Haiku vision transcription. The model hallucinated
a well-formed, PLAUSIBLE-LOOKING wrong reading — not a crash, not an empty
field, a confident wrong answer:

- `DATA DE NASCIMENTO: BRASILEROCA` — a date-typed label with a word for a
  value.
- `CEP: 99 de abril` — a postal-code label with a date-shaped phrase.
- Several fields marked `(ilegível)`.
- The holder `NOME` was actually the mother's (`FILIAÇÃO`) name.

Every one of those is a **structural** signal — the LABEL announces what
TYPE of value belongs there, and the value does not match — that this module
can check without ever re-reading the document or asking a second model.
None of `real.py`'s per-field parsers catch it: `find_birthdate` only
validates a date it FOUND against plausibility bounds, it has no opinion
about a `DATA` label with no date-shaped value at all; `find_name` has no
concept of "this exact string also appears as a parent's name two lines
down". This module is the missing cross-field pass.

WHY THIS IS A SEPARATE MODULE, NOT ANOTHER PER-FIELD PARSER
-------------------------------------------------------------
Every sibling here (`birthdate`, `cpf`, `rg`, ...) answers "what is the
value of THIS field". This module answers a different question — "is this
TRANSCRIPTION, as a whole, trustworthy enough to write unattended" — over
the same text every one of them already reads. Keeping it separate means a
consumer can ask both questions independently: `find_cpf` still returns
its own confidence for the CPF field specifically, and `avaliar_legibilidade`
separately says whether the READING AS A WHOLE looks damaged.

WHY THIS ONLY FIRES RELIABLY ON THE OCR RUNG, AND WHY THAT IS FINE
---------------------------------------------------------------------
The label/value mismatch signal (see `_MISMATCHES_ROTULO`) keys off the
`RÓTULO: valor` — one field per line — shape `real._IDENTITY_DOCUMENT_PROMPT`
asks the vision rung to produce. A PDF text-layer transcription (rung 1,
exact, no model in the loop) is very unlikely to be laid out that way, so
this signal simply finds nothing to check there — never a false positive,
because there is no per-field line to misjudge. That asymmetry is exactly
right: rung 1 is a lossless character copy and does not need this check;
rung 2 is a model's transcription of a photograph and is precisely where a
confident wrong answer can happen. Running this pass unconditionally (never
gated on `TextSource`) costs nothing on the safe rung and catches everything
on the risky one.

THRESHOLDS ARE CONSERVATIVE, ON PURPOSE
------------------------------------------
A clean, well-transcribed document must never be flagged — a false
`comprometida` trains people to ignore the banner, which is worse than not
having it. See each threshold's own comment for the reasoning; each is
covered by a "stays `ok`" test using a normal, correctly-labelled
transcription.

🔴 MEASURED AGAINST 28 REAL PRODUCTION TRANSCRIPTIONS (P2 CORPUS) —
TIGHTENED 2026-09-28
--------------------------------------------------------------------
The first cut of this module, measured against 28 real identity
transcriptions from the same production prompt, flagged 17/28 as
`comprometida` — correctly catching the hallucinated screenshot, but wrongly
flagging 17 genuine documents (too aggressive to withhold most good
readings) — AND missed a second, real hallucinated RG scan. Two root causes,
both fixed below rather than papered over with a lower bar:

1. **`campo_data_invalido` false-fired on COMPOUND date labels.** A real
   CNH's own label is often `DATA, LOCAL E UF DE NASCIMENTO` or `DATA E
   LOCAL DE NASCIMENTO / DATE AND PLACE OF BIRTH`, whose value is
   `01/02/1980, COTIA, SP` — a date PLUS more text. The original check
   required the WHOLE value to be nothing but a date (`fullmatch`); the
   fix is "does the value CONTAIN a date", which is what "this label's type
   is satisfied" actually means.
2. **`uf_invalida` false-fired on any label merely CONTAINING the token
   `UF`.** A real CNH's `4c DOC IDENTIDADE / ÓRG EMISSOR / UF` groups three
   sub-fields into one label; `UF` being one whitespace-separated token in
   it is not the same as the label BEING a UF field. Tightened to an EXACT
   match against a small set of bare UF labels (`UF`, `ESTADO`) — a
   compound label is simply not checked by this signal at all (the date/
   CEP/CPF checks still cover whatever real sub-fields it groups).

A third, narrower fix: **a lone `cpf_invalido` — no other signal on the same
document — is demoted to informational, not a `comprometida` verdict.** A
single CPF whose check digits fail is exactly what ONE OCR digit slip on an
otherwise-clean document looks like (`cpf.py`'s own parser already demotes
that reading to `baixa`/`nenhuma` on its own terms); nothing else here
distinguishes "genuinely damaged transcription" from "one field's ordinary
OCR noise" the way a co-occurring signal does. Every OTHER signal keeps its
original stand-alone-sufficient behaviour — this demotion is scoped to
`cpf_invalido` alone, deliberately, not a blanket "need two signals" rule
that would also swallow a real single-signal case like `nome_igual_filiacao`.

THE MISSED HALLUCINATION (a real, separate RG scan) added three signals this
module did not have before:

3. `endereco_sem_texto` — an `ENDERECO`-labelled value with no real WORD in
   it (a token of 4+ letters) — `"12.345.6789 - 2 via"` names no street,
   only digits and a two-letter/short suffix; a real address always names
   one.
4. `campo_incompativel_documento_pessoal` — a business/tax-registration
   marker (`ICMS`, `INSCRIÇÃO ESTADUAL`, `CONTRIBUINTE`, or a CNPJ-shaped
   `NN.NNN.NNN/NNNN`-ish number) anywhere in an identity-document
   transcription. None of RG/CPF/CNH/CIN/certidão/comprovante ever
   legitimately carries one — a hallucinated identity document borrowing
   phrases from a business-registration document is exactly the failure
   mode this catches.
5. `texto_repetido` — a run of two-or-more real words (4+ letters, so
   `DE`/`DO`/`DA` connectors never count) repeating later in the SAME line
   — `SECÇÃO DE SEGURANÇA PUBLICA DO ESTADO DE SEGURANÇA PUBLICA` restates
   "SEGURANÇA PUBLICA", the shape a model produces when it loses its place
   mid-transcription and re-reads the same phrase.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from noctusai_lib.integrations.documents.address import UFS
from noctusai_lib.integrations.documents.cpf import is_valid as _cpf_is_valid
from noctusai_lib.integrations.documents.cpf import only_digits as _cpf_only_digits
from noctusai_lib.integrations.documents.text import normalize_lines, strip_accents_upper

#: The aviso code this module's finding is surfaced under (`IdentityFields
#: .aviso`, "+"-joined with any other code the extractor already raises —
#: see `real.py`'s `avisos` list). Consumers should not string-match the
#: reason CODES below against `aviso_mensagem`; they are for the human-facing
#: message only. To test for this specific finding, use
#: `IdentityFields.leitura_comprometida` (or check for this constant inside
#: `aviso.split("+")`).
AVISO_LEITURA_COMPROMETIDA = "leitura_comprometida"

#: `[ILEGÍVEL]` / `(ilegível)` — the two spellings this parser family's
#: prompts ask a model to use when a value cannot be read (see
#: `real._IDENTITY_DOCUMENT_PROMPT`, `guia_itbi._ILEGIVEL`,
#: `financiamento_imobiliario._ILEGIVEL`). Matched accent/case/bracket
#: insensitively since a model does not always reproduce the exact prompt
#: spelling.
_ILEGIVEL_MARCADOR = "ILEGIVEL"

#: A label containing this substring introduces a DATE-shaped value
#: (`DATA DE NASCIMENTO`, `DATA DE EXPEDICAO`, `DATA DE CASAMENTO`, `DATA DE
#: EMISSAO`, `DATA DE VALIDADE`, or a bare `DATA`). Broad on purpose: every
#: date-carrying label in this document family contains the word `DATA`, and
#: there is no cost to checking one extra label that turns out not to be a
#: real date field — the value either CONTAINS a date-shaped run or it does
#: not (see `_DATA_RE`'s own comment — a real CNH compounds this label with
#: `LOCAL`/`UF`, so the value legitimately carries more than the date).
_ROTULO_DATA = "DATA"

#: Matches `10/03/1995`, `10-03-1995`, `10.03.1995` (2-or-4-digit year)
#: ANYWHERE in the value — deliberately a `search`-shaped pattern, not
#: anchored to the whole string. A real CNH's compound label (`DATA, LOCAL E
#: UF DE NASCIMENTO`) prints `01/02/1980, COTIA, SP` — a date PLUS the
#: place — and requiring the value to be NOTHING BUT a date rejected every
#: one of those as a false mismatch (measured, P2 corpus, 2026-09-28). This
#: check only asks "does this label's date-type get satisfied somewhere in
#: the value" — `birthdate.find_birthdate`'s own plausibility gate is what
#: judges whether a date THIS module found is a good one.
_DATA_RE = re.compile(r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}")

#: A label containing this token introduces a CEP.
_ROTULO_CEP = "CEP"

#: A label containing this token introduces a CPF. Deliberately broad
#: (matches `CPF`, `C.P.F` once normalised, `CPF/MF`, `CPF DO CONJUGE`,
#: `CPF DA MAE`) — this check only asks "does the value under THIS label
#: pass the CPF check-digit arithmetic", never who the CPF belongs to, so a
#: parent's or spouse's CPF label is just as valid a thing to validate. A
#: CNH's own `Nº DE REGISTRO` / `CAT HAB` labels never contain this
#: substring, so they are never mistaken for a CPF field by this check
#: (regression-covered in the test file).
_ROTULO_CPF = "CPF"

#: A label that IS (exactly, once normalised) a bare UF field — never a
#: label that merely CONTAINS the token `UF` among others. A real CNH
#: groups three sub-fields into one label (`DOC IDENTIDADE / ÓRG EMISSOR /
#: UF`), where `UF` is one whitespace-separated token among several; that
#: compound label is not itself a UF field and must not be checked as one
#: (measured, P2 corpus, 2026-09-28 — 13/28 false alarms from this exact
#: shape). `NATURALIDADE`, `NOME`, etc. never equal either string.
_ROTULOS_UF_ESTRITOS = frozenset({"UF", "ESTADO"})

#: A label containing this token introduces a postal ADDRESS.
_ROTULO_ENDERECO = "ENDERECO"

#: The shortest word length this module treats as a genuine WORD rather
#: than a connector/suffix (`DE`, `DO`, `2`, `VIA`). A real street/city name
#: always carries at least one word this long; a hallucinated address that
#: is really just digits plus a short suffix (`"12.345.6789 - 2 via"`) does
#: not. Chosen from the measured miss, not tuned finer than that one data
#: point warrants.
_PALAVRA_MINIMA = 4

#: Business/tax-registration markers that never legitimately appear on a
#: PERSONAL identity document (RG/CPF/CNH/CIN/certidão/comprovante) — every
#: one of them belongs to a company-registration document instead
#: (`cartao_cnpj.py`'s own family, never this one). Checked over the WHOLE
#: line, not just a label, because the measured miss's garbled text did not
#: always carry a clean `RÓTULO: valor` split.
_MARCADORES_INCOMPATIVEIS = ("ICMS", "INSCRICAO ESTADUAL", "CONTRIBUINTE")

#: A CNPJ-shaped run (`NN.NNN.NNN/NNNN`, loosely) — a real CNPJ is
#: `NN.NNN.NNN/NNNN-NN`, but the measured miss's hallucinated text did not
#: reproduce the trailing check digits either. Loose on purpose: a personal
#: identity document has NO legitimate reason to print anything in this
#: shape at all, so there is no plausible false positive to guard against.
_CNPJ_LIKE_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{2,4}")

#: Block openers naming a PARENT — see `labels.py`'s own note on why
#: `FILIACAO` starts a different person's region. Kept narrow to PARENTS
#: specifically (never `CONJUGE`/`RESPONSAVEL`) because the measured failure
#: this module closes is a mother's name landing in the holder's own `NOME`
#: field — a spouse's name colliding with the holder's is a different,
#: already-handled case (`real.py`'s `titulares_multiplos` aviso).
_BLOCO_FILIACAO = ("FILIACAO", "NOME DO PAI", "NOME DA MAE", "PAI", "MAE")

#: Ilegível-marker share thresholds. Both must hold — a lone marker on an
#: otherwise-full document (say, 1 of 12 fields) is normal and expected
#: ("this one field genuinely wasn't legible"); only a document where a
#: SUBSTANTIAL share came back unreadable is itself suspect enough to warrant
#: a human looking at the whole thing, not just the flagged field.
_ILEGIVEL_CONTAGEM_MINIMA = 2
_ILEGIVEL_TAXA_MINIMA = 0.25


class LegibilidadeStatus(str, Enum):
    """The document-wide verdict — never a per-field one."""

    OK = "ok"
    COMPROMETIDA = "comprometida"


@dataclass(frozen=True)
class LegibilidadeAvaliacao:
    """The verdict plus WHY, so a human reviewing the banner sees the
    specific signal(s) that fired instead of a bare "trust me"."""

    status: LegibilidadeStatus
    #: Reason codes, stable and machine-checkable (`"campo_data_invalido"`,
    #: `"cep_invalido"`, `"cpf_invalido"`, `"uf_invalida"`,
    #: `"endereco_sem_texto"`, `"campo_incompativel_documento_pessoal"`,
    #: `"texto_repetido"`, `"alta_taxa_ilegivel"`, `"nome_igual_filiacao"`).
    #: Empty for `OK` — including when the ONLY signal that fired is a weak
    #: one (`_SINAIS_FRACOS`) that alone does not compromise the document.
    motivos: tuple[str, ...] = ()
    #: The pt-BR sentence naming every reason, `" | "`-joined — the same
    #: shape `real.py`'s `aviso_mensagem` already uses for other findings.
    #: `None` for `OK`.
    mensagem: Optional[str] = None

    @property
    def comprometida(self) -> bool:
        return self.status is LegibilidadeStatus.COMPROMETIDA


def _dividir_rotulo_valor(linha: str) -> tuple[Optional[str], str]:
    """`"RÓTULO: valor"` -> `("RÓTULO", "valor")`; no colon -> `(None, linha)`.

    Only the FIRST colon splits — a value that itself contains one (a time,
    a URL) still separates correctly from its label.
    """
    if ":" not in linha:
        return None, linha
    rotulo, _, valor = linha.partition(":")
    return rotulo.strip(), valor.strip()


def _tem_marcador_ilegivel(valor: str) -> bool:
    return _ILEGIVEL_MARCADOR in strip_accents_upper(valor)


def _tem_palavra_real(valor: str, *, minimo: int = _PALAVRA_MINIMA) -> bool:
    """Does any token, once its OWN punctuation is stripped, read as a word
    at least `minimo` letters long?

    Punctuation is stripped per token first — `"RUA DAS FLORES,
    123".split()` -> `[..., "FLORES,", "123"]`, and `"FLORES,"` is not
    `.isalpha()` with the comma still attached, which would wrongly read a
    perfectly genuine address as having no real word. `"12.345.6789 - 2
    via".split()` -> `[..., "via"]` — stripped, `"via"` IS alphabetic but
    only 3 letters, so this still returns `False`: a real street/city name
    always carries at least one longer one.
    """
    for tok in valor.split():
        letras = tok.strip(".,;/-").replace(".", "")
        if letras.isalpha() and len(letras) >= minimo:
            return True
    return False


def _mismatches_tipo(linhas: list[str]) -> list[str]:
    """Label/value TYPE mismatches — the signal that catches a confident,
    well-formed, WRONG transcription (see the module docstring's measured
    case). Skips any value already carrying an ilegível marker: a model
    that admits it could not read a field is a different, already-covered
    signal (`_taxa_ilegivel` below), not a second, redundant mismatch.
    """
    motivos: list[str] = []
    viu_data_invalida = viu_cep_invalido = viu_cpf_invalido = False
    viu_uf_invalida = viu_endereco_sem_texto = False

    for linha in linhas:
        rotulo, valor = _dividir_rotulo_valor(linha)
        if rotulo is None or not valor or _tem_marcador_ilegivel(valor):
            continue

        if _ROTULO_DATA in rotulo and not viu_data_invalida:
            if not _DATA_RE.search(valor):
                viu_data_invalida = True

        if _ROTULO_CEP in rotulo and not viu_cep_invalido:
            if len(_cpf_only_digits(valor)) != 8:
                viu_cep_invalido = True

        if _ROTULO_CPF in rotulo and not viu_cpf_invalido:
            digitos = _cpf_only_digits(valor)
            if len(digitos) == 11 and not _cpf_is_valid(valor):
                # Only flag an 11-digit run that FAILS the checksum — a
                # value that is not eleven digits at all under a CPF label
                # is far more likely a transcription that dropped digits
                # than a type mismatch this check should own, and CPF's own
                # sibling parser (`cpf.py`) already demotes it to `baixa`/
                # `nenhuma` on its own terms. `avaliar_legibilidade` also
                # demotes a LONE `cpf_invalido` to non-comprometida — see
                # its own docstring.
                viu_cpf_invalido = True

        # EXACT match only — a compound label merely CONTAINING the token
        # `UF` (`DOC IDENTIDADE / ÓRG EMISSOR / UF`) is not itself a UF
        # field. See `_ROTULOS_UF_ESTRITOS`'s own comment.
        if rotulo in _ROTULOS_UF_ESTRITOS and not viu_uf_invalida:
            candidato = strip_accents_upper(valor).replace(".", "").replace("-", "").strip()
            if candidato and (len(candidato) != 2 or candidato not in UFS):
                viu_uf_invalida = True

        if _ROTULO_ENDERECO in rotulo and not viu_endereco_sem_texto:
            if not _tem_palavra_real(valor):
                viu_endereco_sem_texto = True

    if viu_data_invalida:
        motivos.append("campo_data_invalido")
    if viu_cep_invalido:
        motivos.append("cep_invalido")
    if viu_cpf_invalido:
        motivos.append("cpf_invalido")
    if viu_uf_invalida:
        motivos.append("uf_invalida")
    if viu_endereco_sem_texto:
        motivos.append("endereco_sem_texto")
    return motivos


def _campo_incompativel(linhas: list[str]) -> Optional[str]:
    """A business/tax-registration marker anywhere in the transcription —
    never a label-anchored check, because the measured miss's garbled text
    did not always carry a clean `RÓTULO: valor` split. See
    `_MARCADORES_INCOMPATIVEIS`/`_CNPJ_LIKE_RE`'s own comments for why
    neither has a plausible false positive on a genuine identity document.
    """
    for linha in linhas:
        if any(marcador in linha for marcador in _MARCADORES_INCOMPATIVEIS):
            return "campo_incompativel_documento_pessoal"
        if _CNPJ_LIKE_RE.search(linha):
            return "campo_incompativel_documento_pessoal"
    return None


def _texto_repetido(linhas: list[str]) -> Optional[str]:
    """A run of 3 consecutive REAL words repeating later in the SAME line.

    🔴 WHY EXACTLY 3, AND WHY 2-OF-3 MUST BE LONG — MEASURED, NOT GUESSED
    -----------------------------------------------------------------------
    A first cut checked 2-word grams too, and flagged a REAL certidão de
    casamento: `"ALMIR TEIXEIRA DA COSTA ... filho de PEDRO TEIXEIRA DA
    COSTA"` repeats the bigram `TEIXEIRA DA` — genuinely, because the son
    shares his father's surname, which is the ORDINARY case a certidão de
    casamento exists to record, not a transcription defect. Two words is
    simply not enough signal to tell "the model lost its place" apart from
    "two related people share a name" in running Portuguese prose.

    Three words fixes it two ways at once: (a) `TEIXEIRA DA COSTA` is never
    duplicated intact in that fixture (the comma after the first `COSTA,`
    drops it from the word list before the gram can form), so the false
    match disappears; (b) requiring at least 2-of-3 words to be a REAL word
    (4+ letters — so grams built mostly from `DE`/`DO`/`DA` connectors,
    ordinary in Portuguese, never count) is what still lets `DE SEGURANCA
    PUBLICA` register as the phrase, not the throwaway `DE` beside it. See
    the module docstring's `SECÇÃO DE SEGURANÇA PUBLICA DO ESTADO DE
    SEGURANÇA PUBLICA` example — the shape a model produces when it loses
    its place mid-transcription and re-reads the same phrase.
    """
    tamanho = 3
    for linha in linhas:
        palavras = [p for p in linha.split() if p.isalpha()]
        if len(palavras) < tamanho + 1:
            continue
        vistos: set[tuple[str, ...]] = set()
        for i in range(len(palavras) - tamanho + 1):
            grama = tuple(palavras[i : i + tamanho])
            if sum(1 for p in grama if len(p) >= _PALAVRA_MINIMA) < 2:
                continue
            if grama in vistos:
                return "texto_repetido"
            vistos.add(grama)
    return None


def _taxa_ilegivel(linhas: list[str]) -> Optional[str]:
    """A SUBSTANTIAL share of the document's own lines came back marked
    unreadable — see the module-level threshold constants for why both a
    minimum count and a minimum share must hold."""
    if not linhas:
        return None
    contagem = sum(1 for linha in linhas if _tem_marcador_ilegivel(linha))
    if contagem < _ILEGIVEL_CONTAGEM_MINIMA:
        return None
    if (contagem / len(linhas)) < _ILEGIVEL_TAXA_MINIMA:
        return None
    return "alta_taxa_ilegivel"


def _nome_igual_filiacao(linhas: list[str], nome_titular: Optional[str]) -> Optional[str]:
    """Does the holder's own extracted name equal a parent's, printed under
    a `FILIAÇÃO`/`PAI`/`MÃE` label on this SAME transcription?

    Exact match only (after accent/case/whitespace normalisation) — the
    measured failure is the holder's `NOME` field landing on the mother's
    name VERBATIM, not merely a similar one, and a substring/fuzzy match
    would risk flagging a genuinely distinct but similarly-spelled name.
    `nome_titular` is whatever the caller is ABOUT to write as the holder's
    name (post titular-selection), so this checks the value that would
    actually be persisted, not a raw candidate the extractor already
    discarded.
    """
    if not nome_titular:
        return None
    alvo = " ".join(strip_accents_upper(nome_titular).split())
    if not alvo:
        return None

    for linha in linhas:
        rotulo, valor = _dividir_rotulo_valor(linha)
        if rotulo is None or not valor:
            continue
        if not any(bloco in rotulo for bloco in _BLOCO_FILIACAO):
            continue
        for candidato in valor.split(" E "):
            nome_candidato = " ".join(candidato.strip().split())
            if nome_candidato and nome_candidato == alvo:
                return "nome_igual_filiacao"
    return None


#: pt-BR sentence per reason code — the same shape `real.py`'s
#: `aviso_mensagem` already uses. Keyed by every code `avaliar_legibilidade`
#: can return; a code missing here is a bug, not a silent gap (the `[m]`
#: lookup below raises `KeyError` rather than swallowing an unrecognised
#: reason).
_MENSAGENS = {
    "campo_data_invalido": "um campo de data trouxe um valor que nao parece uma data",
    "cep_invalido": "um CEP trouxe um valor que nao tem 8 digitos",
    "cpf_invalido": "um CPF trouxe um valor que nao passa na validacao dos digitos verificadores",
    "uf_invalida": "uma UF trouxe um valor que nao e uma sigla de estado valida",
    "endereco_sem_texto": "um endereco trouxe um valor sem nenhum nome de rua ou cidade reconhecivel",
    "campo_incompativel_documento_pessoal": (
        "o documento traz um campo de cadastro empresarial/tributario "
        "(ICMS, inscricao estadual ou um numero no formato de CNPJ), que "
        "nao pertence a um documento de identidade pessoal"
    ),
    "texto_repetido": "um trecho do texto se repete, sinal de uma leitura desorientada",
    "alta_taxa_ilegivel": "uma parte substancial dos campos veio marcada como ilegivel",
    "nome_igual_filiacao": "o nome do titular e identico ao de um dos pais (filiacao) no mesmo documento",
}

#: A signal in here is sufficient ON ITS OWN to flag `comprometida` (every
#: signal defaults to stand-alone-sufficient — this set exists only to
#: document that fact and give `_SINAIS_FRACOS` something to be an
#: exception TO). Not consulted directly; see `avaliar_legibilidade`'s own
#: demotion logic.
#:
#: `cpf_invalido`, alone, is the one signal this module demotes: a single
#: CPF check-digit failure with NOTHING else wrong is exactly what one
#: ordinary OCR digit slip on an otherwise-clean document looks like
#: (measured, P2 corpus, 2026-09-28 — 2/28 false alarms were a lone
#: `cpf_invalido`) — `cpf.py`'s own parser already demotes that reading to
#: `baixa`/`nenhuma` on its own terms, so this module adds no NEW
#: information by escalating the whole document on that signal alone. Any
#: OTHER signal co-occurring with it still flags `comprometida` as normal —
#: this is a demotion of the LONE case, not of the signal itself.
_SINAIS_FRACOS = frozenset({"cpf_invalido"})


def avaliar_legibilidade(
    text: str, *, nome_titular: Optional[str] = None
) -> LegibilidadeAvaliacao:
    """Pure, deterministic readability assessment over one transcription.

    `text` is the SAME text a caller already passed to `find_birthdate` /
    `find_name` / etc. — no second read, no model call. `nome_titular` is
    optional: pass whatever the caller is about to persist as the holder's
    name to enable the filiação cross-check; omit it and every other signal
    still runs.
    """
    linhas = normalize_lines(text)

    motivos: list[str] = []
    motivos += _mismatches_tipo(linhas)
    taxa = _taxa_ilegivel(linhas)
    if taxa:
        motivos.append(taxa)
    incompativel = _campo_incompativel(linhas)
    if incompativel:
        motivos.append(incompativel)
    repetido = _texto_repetido(linhas)
    if repetido:
        motivos.append(repetido)
    filiacao = _nome_igual_filiacao(linhas, nome_titular)
    if filiacao:
        motivos.append(filiacao)

    if not motivos or set(motivos) <= _SINAIS_FRACOS:
        # Either nothing fired, or every signal that fired is a WEAK one
        # (today only a lone `cpf_invalido`) — see `_SINAIS_FRACOS`'s own
        # comment. `set(...) <=` (subset) rather than an equality/length
        # check so this stays correct if a weak signal is ever able to fire
        # more than once in the same document.
        return LegibilidadeAvaliacao(status=LegibilidadeStatus.OK)

    mensagem = " | ".join(_MENSAGENS[m] for m in motivos)
    return LegibilidadeAvaliacao(
        status=LegibilidadeStatus.COMPROMETIDA,
        motivos=tuple(motivos),
        mensagem=mensagem,
    )


__all__ = [
    "AVISO_LEITURA_COMPROMETIDA",
    "LegibilidadeAvaliacao",
    "LegibilidadeStatus",
    "avaliar_legibilidade",
]
