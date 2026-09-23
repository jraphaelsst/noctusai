"""Content-based document-kind signal — independent of what a caller (an
operator, a form) BELIEVES a document is.

WHY THIS EXISTS
----------------
`fake.classify_kind` already answers "what kind of document is this", but
purely from the FILENAME — it is a best-effort hint for a Fake/dev adapter,
never evidence about the document's actual content. Real, measured
2026-09-23: at least two "CNH_<nome>.pdf" / "Vendedora - CNH <nome>.pdf"
uploads were typed `tipo_documento='rg'` in production — the operator (or
the self-serve upload flow) picked the wrong option, the identity extractor
still read the card fine (it is type-agnostic by design — see
`real.LadderIdentityExtractor`'s own docstring), and nothing anywhere ever
noticed the declared type and the document's own content disagreed. A
`"roteiro"` (a real-estate visit route sheet) and an ads report have also
been uploaded as `tipo_documento='rg'` in production, with zero identity
markers of any kind.

WHAT THIS MODULE DOES NOT DO
-----------------------------
It never RETYPES a document — see `real.py`'s own `_ler`, which sets
`IdentityFields.tipo_provavel` from this module's classifier but never
touches `kind`, never overwrites any field, and the DB row's own
`tipo_documento` is exclusively an operator/product decision this module
has no path to write. A consumer (the product layer, which alone knows the
document's DECLARED type) compares `tipo_provavel` against that declared
type and decides whether to surface an `aviso` — this module supplies the
CONTENT half of that comparison, never the verdict.

Pure — no IO, no LLM, no network, same discipline as every sibling parser
in this package.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.integrations.documents.text import strip_accents_upper

#: Phrases that, present ANYWHERE in the transcribed text, strongly signal
#: this `tipo_documento`. Checked in THIS order — a CNH shares some
#: boilerplate with an RG ("REPUBLICA FEDERATIVA DO BRASIL"), so a CNH
#: marker is checked first and wins outright; a document naming BOTH an RG
#: marker and a CNH marker is a CNH (measured: every real CNH sample in
#: this family prints "REPUBLICA FEDERATIVA DO BRASIL" too, but no real RG
#: sample prints "CARTEIRA NACIONAL DE HABILITACAO").
_CNH_MARCADORES = (
    "CARTEIRA NACIONAL DE HABILITACAO",
    "CNH DIGITAL",
    "PERMISSAO PARA DIRIGIR",
    "DEPARTAMENTO NACIONAL DE TRANSITO",
    "DRIVER LICENSE",
)

#: `CERTIDAO DE CASAMENTO` / `CERTIDAO DE NASCIMENTO` checked BEFORE the
#: bare RG markers: a certidão's own boilerplate ("REGISTRO CIVIL DAS
#: PESSOAS NATURAIS") shares the word "REGISTRO" with `REGISTRO GERAL`
#: (the RG marker), but never the phrase itself.
_CERTIDAO_CASAMENTO_MARCADORES = ("CERTIDAO DE CASAMENTO",)
_CERTIDAO_NASCIMENTO_MARCADORES = ("CERTIDAO DE NASCIMENTO",)

_RG_MARCADORES = (
    "CARTEIRA DE IDENTIDADE",
    "CEDULA DE IDENTIDADE",
    "REGISTRO GERAL",
    "INSTITUTO DE IDENTIFICACAO",
    "SECRETARIA DE SEGURANCA PUBLICA",
    "SECRETARIA DE ESTADO DA SEGURANCA PUBLICA",
)

#: A CPF card's own boilerplate — checked LAST among the four positive
#: classes: "CADASTRO DE PESSOAS FISICAS" ALSO prints on an RG/CNH's own
#: `4D CPF` field context in some layouts, so a document that ALSO carries
#: an RG/CNH/certidão marker is judged that richer type first.
_CPF_MARCADORES = ("CADASTRO DE PESSOAS FISICAS",)


def classificar_tipo_provavel(text: str) -> Optional[str]:
    """Best-effort content signal for which `tipo_documento` this text
    belongs to — independent of any caller's own belief about it.

    Returns one of `"cnh"` / `"certidao_casamento"` /
    `"certidao_nascimento"` / `"rg"` / `"cpf"`, or `None` when no marker
    phrase is present at all.

    🔴 `None` IS NOT A CLAIM. It means this text carries none of the
    phrases this module currently recognises — NOT "this is not an
    identity document". A short, badly-OCR'd, or unusually-worded real ID
    can legitimately return `None`. A caller wanting the OTHER signal —
    "this transcript carries no identity content whatsoever" — combines a
    `None` here with the extractor's own field yield (`IdentityFields.
    presente()` across `types.CAMPOS`); see the module docstring.
    """
    norm = strip_accents_upper(text or "")
    if not norm:
        return None
    if any(m in norm for m in _CNH_MARCADORES):
        return "cnh"
    if any(m in norm for m in _CERTIDAO_CASAMENTO_MARCADORES):
        return "certidao_casamento"
    if any(m in norm for m in _CERTIDAO_NASCIMENTO_MARCADORES):
        return "certidao_nascimento"
    if any(m in norm for m in _RG_MARCADORES):
        return "rg"
    if any(m in norm for m in _CPF_MARCADORES):
        return "cpf"
    return None


__all__ = ["classificar_tipo_provavel"]
