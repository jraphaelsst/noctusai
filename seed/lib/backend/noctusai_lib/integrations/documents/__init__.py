"""Identity documents → typed fields. Protocol + Fake + Real + factory.

**What ships**

- `IdentityFields` / `IdentityDocumentKind` / `ExtractionConfidence` /
  `TextSource` value objects, and the `IdentityExtractor` Protocol.
- `find_birthdate(text)` / `find_name(text)` / `find_gender(text)` — the pure,
  label-anchored Brazilian parsers. Usable on their own wherever text is
  already in hand.
- `FakeIdentityExtractor` — deterministic; the dev/test default.
- `LadderIdentityExtractor` — PDF text layer → rasterize→vision, composing
  `integrations.media`. Imported lazily.
- `make_identity_extractor(real=...)` — factory.

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
from noctusai_lib.integrations.documents.matricula import find_matricula
from noctusai_lib.integrations.documents.name import find_name, looks_like_a_name
from noctusai_lib.integrations.documents.fake import (
    FakeIdentityExtractor,
    classify_kind,
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


def __getattr__(name: str):  # pragma: no cover - lazy proxy
    """Lazy-load `LadderIdentityExtractor` on first access, so importing
    this package never requires PyMuPDF / the LLM stack."""
    if name == "LadderIdentityExtractor":
        from noctusai_lib.integrations.documents.real import LadderIdentityExtractor

        return LadderIdentityExtractor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ExtractionConfidence",
    "FakeIdentityExtractor",
    "IdentityDocumentKind",
    "IdentityExtractor",
    "IdentityFields",
    "LadderIdentityExtractor",
    "TextSource",
    "classify_kind",
    "find_birthdate",
    "find_name",
    "find_gender",
    "find_matricula",
    "looks_like_a_name",
    "make_identity_extractor",
    "normalize",
    "normalize_lines",
    "strip_accents_upper",
]
