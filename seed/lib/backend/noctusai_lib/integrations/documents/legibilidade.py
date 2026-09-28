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
#: real date field — the value either looks like a date or it does not.
_ROTULO_DATA = "DATA"

#: Accepts `10/03/1995`, `10-03-1995`, `10.03.1995`, with a 2-or-4-digit
#: year — the shapes every sibling parser's own date regex already accepts
#: (see `birthdate.py`). Not stricter than that on purpose: this check is
#: "does this look like a date at all", not "is this a plausible date" —
#: `birthdate.find_birthdate`'s own plausibility gate already owns the
#: latter for the one field it extracts.
_DATA_RE = re.compile(r"^\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}$")

#: A label containing this token introduces a CEP.
_ROTULO_CEP = "CEP"

#: A label containing this token introduces a CPF. Deliberately broad
#: (matches `CPF`, `C.P.F` once normalised, `CPF/MF`, `CPF DO CONJUGE`,
#: `CPF DA MAE`) — this check only asks "does the value under THIS label
#: pass the CPF check-digit arithmetic", never who the CPF belongs to, so a
#: parent's or spouse's CPF label is just as valid a thing to validate.
_ROTULO_CPF = "CPF"

#: A label whose only token is `UF` (after splitting on whitespace) —
#: `NATURALIDADE`, `NOME`, etc. never match, since none of them contains the
#: standalone word `UF`.
_ROTULO_UF_TOKEN = "UF"

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
    #: `"alta_taxa_ilegivel"`, `"nome_igual_filiacao"`). Empty for `OK`.
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


def _mismatches_tipo(linhas: list[str]) -> list[str]:
    """Label/value TYPE mismatches — the signal that catches a confident,
    well-formed, WRONG transcription (see the module docstring's measured
    case). Skips any value already carrying an ilegível marker: a model
    that admits it could not read a field is a different, already-covered
    signal (`_taxa_ilegivel` below), not a second, redundant mismatch.
    """
    motivos: list[str] = []
    viu_data_invalida = viu_cep_invalido = viu_cpf_invalido = viu_uf_invalida = False

    for linha in linhas:
        rotulo, valor = _dividir_rotulo_valor(linha)
        if rotulo is None or not valor or _tem_marcador_ilegivel(valor):
            continue

        if _ROTULO_DATA in rotulo and not viu_data_invalida:
            if not _DATA_RE.match(valor):
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
                # `nenhuma` on its own terms.
                viu_cpf_invalido = True

        if rotulo.split() and _ROTULO_UF_TOKEN in rotulo.split() and not viu_uf_invalida:
            candidato = strip_accents_upper(valor).replace(".", "").replace("-", "").strip()
            if candidato and (len(candidato) != 2 or candidato not in UFS):
                viu_uf_invalida = True

    if viu_data_invalida:
        motivos.append("campo_data_invalido")
    if viu_cep_invalido:
        motivos.append("cep_invalido")
    if viu_cpf_invalido:
        motivos.append("cpf_invalido")
    if viu_uf_invalida:
        motivos.append("uf_invalida")
    return motivos


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
    filiacao = _nome_igual_filiacao(linhas, nome_titular)
    if filiacao:
        motivos.append(filiacao)

    if not motivos:
        return LegibilidadeAvaliacao(status=LegibilidadeStatus.OK)

    mensagens = {
        "campo_data_invalido": "um campo de data trouxe um valor que nao parece uma data",
        "cep_invalido": "um CEP trouxe um valor que nao tem 8 digitos",
        "cpf_invalido": "um CPF trouxe um valor que nao passa na validacao dos digitos verificadores",
        "uf_invalida": "uma UF trouxe um valor que nao e uma sigla de estado valida",
        "alta_taxa_ilegivel": "uma parte substancial dos campos veio marcada como ilegivel",
        "nome_igual_filiacao": "o nome do titular e identico ao de um dos pais (filiacao) no mesmo documento",
    }
    mensagem = " | ".join(mensagens[m] for m in motivos)
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
