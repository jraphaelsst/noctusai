"""Identity documents → typed fields. Protocol + Fake + Real + factory.

**What ships**

- `IdentityFields` / `IdentityDocumentKind` / `ExtractionConfidence` /
  `TextSource` value objects, and the `IdentityExtractor` Protocol.
- `find_birthdate(text)` — the pure, label-anchored Brazilian birthdate
  parser. Usable on its own wherever text is already in hand.
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

🔴 **Consumer contract.** Only `IdentityFields.persistable` results may be
written unattended (`confidence == ALTA`). Anything else is a suggestion
for a human to confirm. Persist `source` and `matched_label` alongside any
stored value — reading an identity document is a logged, LGPD-relevant
access, and an unattributed value cannot be audited or corrected later.
"""
from noctusai_lib.integrations.documents.birthdate import find_birthdate, normalize
from noctusai_lib.integrations.documents.factory import make_identity_extractor
from noctusai_lib.integrations.documents.fake import (
    FakeIdentityExtractor,
    classify_kind,
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
    "make_identity_extractor",
    "normalize",
]
