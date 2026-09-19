"""Derive a matrícula's OWN street + officialised número — the address a deed
must print instead of a CRM/Vista mirror's público endereço.

🔴 WHY THIS EXISTS
-------------------
At least one tenant deliberately publishes the PORTARIA (gatehouse) address
in the CRM's público `Endereco`/`Numero` fields, to keep agents outside the
firm from harvesting the real property address — see
`KB § INTEGRATIONS/vista.md` and `social-wiring`'s
`contrato_gerador/dados.py` (`Imovel.endereco` docstring). A signed
instrument must never carry that decoy: it needs the address the matrícula
itself states, the one a cartório actually compares its own book against.

Fourth sibling of `matricula_abertura.py` / `matricula_ato_detalhes.py`: pure,
deterministic (no LLM), offset-driven internally, same "a label not
confidently matched yields nothing, never a guess" contract those two share.

🔴 WHY THE NÚMERO NEEDS ITS OWN PASS OVER THE AVERBAÇÕES
-----------------------------------------------------------
The abertura names the street (and often the lote/quadra/loteamento) but not
always the número — a loteamento is frequently opened "s/nº" (sem número),
with the número OFFICIALISED later by a specific averbação ("para ficar
constando a oficialização do nº 535"). A property can carry SEVERAL
numbering averbações over its life (prefeitura renumbering, a later
subdivision, ...): this module always prefers the HIGHEST-numbered averbação
that states one — later averbações supersede earlier ones, and taking the
FIRST match found scanning top-to-bottom would silently prefer an old,
superseded number over a live one.

🔴 "S/Nº" IS A CONFIRMED STATE, NOT A GAP
--------------------------------------------
Some properties genuinely have no número. An EXPLICIT "s/nº" statement
anywhere in the scanned text, with no later officialisation overriding it, is
a CONFIRMED absence (`numero_confirmado_ausente=True`): the caller should
print "s/nº", never treat it the same as "nothing found" (a real gap the
caller must name, e.g. via `derivacao.Avaliacao.falta`).

WHY STRINGS, NOT OFFSETS
-------------------------
`matricula_abertura.py`/`matricula_ato_detalhes.py` return offsets because a
route re-slices the CALLER's own text for UI highlighting. Nothing consumes
that here (yet) — this module's only consumer composes a printable short
address — so it returns the literal, byte-identical substrings directly
(never re-cased/re-typed: matched against an accent/case-folded copy of the
input, then sliced from the ORIGINAL so casing and accents survive). A future
UI-highlighting consumer should add an offset-returning sibling rather than
retrofit this one, mirroring how `matricula_ato_detalhes` sits beside
`matricula_atos` instead of replacing it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from noctusai_lib.integrations.documents.matricula_atos import (
    normalized_with_offsets,
    segment_matricula_atos,
)

#: Tight form: the número sits RIGHT after the street, comma-separated, in
#: the SAME sentence — "situada na Rua X, nº 100," — high confidence both
#: fields describe the same fact. Deliberately does NOT match "situada na
#: Alameda Alemanha, constituído pelo lote nº 14": the qualifier
#: ("constituído pelo lote") between the comma and "nº" means that number is
#: a LOTE number, not a street number, and the character class excluding
#: commas keeps this pattern from reaching past it.
_LOGRADOURO_COM_NUMERO = re.compile(
    r"SITUAD[OA]\s+(?:NO|NA|EM|A)\s+([^,]+?)\s*,\s*N[ºO°]\.?\s*(\d[\w/-]*)\s*(?:,|\.|$)"
)

#: Loose form: the street alone, whatever follows the comma.
_LOGRADOURO = re.compile(r"SITUAD[OA]\s+(?:NO|NA|EM|A)\s+([^,.\n]+)")

#: An averbação that OFFICIALISES a número — "para ficar constando a
#: oficialização do nº 535", "fica oficializado o número 535" — within ~60
#: normalised chars of "OFICIALIZA..." so the match cannot reach across
#: unrelated prose into an unrelated number.
_OFICIALIZACAO = re.compile(r"OFICIALIZA\w*[^\n]{0,60}?N[ºO°]?\.?\s*(\d[\w/-]*)")

#: An EXPLICIT "sem número" statement — "s/nº", "S/N", "sem número".
_SEM_NUMERO = re.compile(r"S\s*/\s*N[ºO°]?\b|SEM\s+N[ºO°]MERO")


@dataclass(frozen=True)
class EnderecoMatricula:
    """The matrícula's own address, as literal substrings of the caller's
    text (never re-cased/re-typed). `None` fields are genuinely unresolved —
    the caller decides what that means (usually `Avaliacao.falta`)."""

    logradouro: Optional[str] = None
    numero: Optional[str] = None
    #: True only when the absence of a número is a CONFIRMED fact (an
    #: explicit "s/nº" with no later officialisation overriding it) — not
    #: merely "no officialisation act was found in the scanned text".
    numero_confirmado_ausente: bool = False


def _fatiar(texto: str, norm: str, origem: list[int], m: "re.Match[str]", grupo: int) -> str:
    a, b = m.start(grupo), m.end(grupo)
    if a == b:
        return ""
    inicio = origem[a]
    fim = origem[b - 1] + 1 if b > 0 else inicio
    return texto[inicio:fim].strip()


def derivar_endereco(texto_imovel: str, texto_atos: str = "") -> EnderecoMatricula:
    """`texto_imovel` is the abertura's property description — the
    `IMÓVEL:` block a matrícula transcription carries (e.g.
    `Matricula.descricao_imovel_texto`, or the whole quote when no such
    block was isolated — the same fallback `contexto.py` already applies to
    the OBJETO clause). `texto_atos` is the matrícula's full selected quote
    (`Matricula.texto` / `PermutaImovel.descricao_matricula`) — only its
    `AV` acts (`segment_matricula_atos`) are scanned, HIGHEST número first,
    for a later officialisation.
    """
    norm_im, orig_im = normalized_with_offsets(texto_imovel or "")

    logradouro: Optional[str] = None
    numero: Optional[str] = None
    m = _LOGRADOURO_COM_NUMERO.search(norm_im)
    if m:
        logradouro = _fatiar(texto_imovel, norm_im, orig_im, m, 1) or None
        numero = _fatiar(texto_imovel, norm_im, orig_im, m, 2) or None
    else:
        m2 = _LOGRADOURO.search(norm_im)
        if m2:
            logradouro = _fatiar(texto_imovel, norm_im, orig_im, m2, 1) or None

    ausente = bool(_SEM_NUMERO.search(norm_im))

    if numero is None and texto_atos:
        averbacoes = sorted(
            (a for a in segment_matricula_atos(texto_atos) if a.kind == "AV" and a.numero is not None),
            key=lambda a: a.numero,  # type: ignore[arg-type,return-value]
            reverse=True,
        )
        for ato in averbacoes:
            corpo = texto_atos[ato.start : ato.end]
            norm_ato, orig_ato = normalized_with_offsets(corpo)
            mo = _OFICIALIZACAO.search(norm_ato)
            if mo:
                achado = _fatiar(corpo, norm_ato, orig_ato, mo, 1)
                if achado:
                    numero = achado
                    ausente = False
                    break
        if numero is None and not ausente:
            norm_atos, _orig_atos = normalized_with_offsets(texto_atos)
            ausente = bool(_SEM_NUMERO.search(norm_atos))

    return EnderecoMatricula(
        logradouro=logradouro,
        numero=numero,
        numero_confirmado_ausente=numero is None and ausente,
    )


__all__ = ["EnderecoMatricula", "derivar_endereco"]
