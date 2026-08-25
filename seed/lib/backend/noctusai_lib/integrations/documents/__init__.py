"""Identity documents → typed fields. Protocol + Fake + Real + factory.

**What ships**

- `IdentityFields` / `IdentityDocumentKind` / `ExtractionConfidence` /
  `TextSource` value objects, and the `IdentityExtractor` Protocol.
- `find_birthdate(text)` / `find_name(text)` / `find_gender(text)` — the pure,
  label-anchored Brazilian parsers. Usable on their own wherever text is
  already in hand.
- `FakeIdentityExtractor` — deterministic; the dev/test default.
- `LadderIdentityExtractor` — identity documents → `IdentityFields`.
  Imported lazily.
- `make_identity_extractor(real=...)` — factory.
- `find_matricula(text)` + `MatriculaFields` / `FakeMatriculaExtractor` /
  `LadderMatriculaExtractor` / `make_matricula_extractor(real=...)` — the
  same shape for a certidão de matrícula. See `matricula_extractor.py` for
  why it tempers a vision read harder than anything else here.
- `DocumentTextLadder` — the shared "bytes → cheapest readable text" rung
  chooser both real extractors compose.

**Why this is a seed module and not product code.** RG/CPF extraction is
requested as *the canonical procedure*, and the platform already has the
counter-example of what happens otherwise:
`erp-imobiliario/app/services/matricula_service.py` is a product-local
PDF extractor that predates `integrations.media` and now duplicates it
(OCR-only — it pays for a vision call per page even when the PDF has a
text layer). A second product-local copy would make that a pattern rather
than an accident.

**Relationship to `integrations.media`.** `media` answers "bytes → text
a model can read". This answers "document → fields a column can store".
They are different questions: `ResolvedMedia.text` is deliberately
narrative, and every consumer that needed a typed value out of it would
otherwise re-parse that prose itself, differently, at each call site.

🔴 **Consumer contract.** Confidence is PER FIELD. Only a value whose
`persistable_<field>` property is true may be written unattended
(`<field>_confianca == ALTA`); anything else is a suggestion for a human
to confirm. Persist `source` and the field's `_rotulo` alongside any
stored value — reading an identity document is a logged, LGPD-relevant
access, and an unattributed value cannot be audited or corrected later.

**The two fields have deliberately different write semantics**, and a
consumer must honour both:

- `data_nascimento` — FIRST WRITER WINS. Only ever written into an empty
  column; a value already present, from any source, is left alone.
- `nome` — THE OFFICIAL DOCUMENT WINS. Written even over an existing
  value, because a name typed into a lead form is a convenience spelling
  and the one on the RG/CPF is the legal one. This is why its confidence
  is tempered by text source (`real._temper_name_confidence`): an
  overwrite must not be driven by a vision-pass guess.
"""
from noctusai_lib.integrations.documents.birthdate import find_birthdate, normalize
from noctusai_lib.integrations.documents.factory import make_identity_extractor
from noctusai_lib.integrations.documents.gender import find_gender
from noctusai_lib.integrations.documents.ladder import (
    DocumentTextLadder,
    looks_like_pdf,
)
from noctusai_lib.integrations.documents.matricula import find_matricula
from noctusai_lib.integrations.documents.matricula_extractor import (
    FakeMatriculaExtractor,
    MatriculaExtractor,
    MatriculaFields,
    make_matricula_extractor,
)
from noctusai_lib.integrations.documents.name import find_name, looks_like_a_name
from noctusai_lib.integrations.documents.fake import (
    FakeIdentityExtractor,
    classify_kind,
)
from noctusai_lib.integrations.documents.transcription import (
    DocumentTranscriber,
    FakeDocumentTranscriber,
    TranscribedPage,
    Transcription,
    make_document_transcriber,
)
from noctusai_lib.integrations.documents.text import (
    normalize_lines,
    strip_accents_upper,
)
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    IdentityDocumentKind,
    IdentityExtractor,
    IdentityFields,
    TextSource,
)


#: Attribute name → the module it lives in, for the lazy proxy below. Both
#: real extractors are listed: neither may be imported eagerly, since each
#: pulls `integrations.media` (PyMuPDF / the LLM stack) on its ladder's first
#: use, and a slim image must still be able to import this package.
_LAZY: dict[str, str] = {
    "LadderIdentityExtractor": "noctusai_lib.integrations.documents.real",
    "LadderMatriculaExtractor": (
        "noctusai_lib.integrations.documents.matricula_extractor"
    ),
    "LadderDocumentTranscriber": (
        "noctusai_lib.integrations.documents.transcription"
    ),
}


def __getattr__(name: str):  # pragma: no cover - lazy proxy
    """Lazy-load the real extractors on first access, so importing this
    package never requires PyMuPDF / the LLM stack."""
    modulo = _LAZY.get(name)
    if modulo is not None:
        import importlib

        return getattr(importlib.import_module(modulo), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DocumentTextLadder",
    "DocumentTranscriber",
    "ExtractionConfidence",
    "FakeDocumentTranscriber",
    "FakeIdentityExtractor",
    "FakeMatriculaExtractor",
    "IdentityDocumentKind",
    "IdentityExtractor",
    "IdentityFields",
    "LadderDocumentTranscriber",
    "LadderIdentityExtractor",
    "LadderMatriculaExtractor",
    "MatriculaExtractor",
    "MatriculaFields",
    "TextSource",
    "TranscribedPage",
    "Transcription",
    "classify_kind",
    "find_birthdate",
    "find_gender",
    "find_matricula",
    "find_name",
    "looks_like_a_name",
    "looks_like_pdf",
    "make_document_transcriber",
    "make_identity_extractor",
    "make_matricula_extractor",
    "normalize",
    "normalize_lines",
    "strip_accents_upper",
]
