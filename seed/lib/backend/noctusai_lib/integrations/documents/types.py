"""Identity-document extraction value objects + Protocol.

The seam turns an identity document (RG / CPF / CNH — bytes plus a
mimetype) into a small set of **typed fields**, not prose. That is the
whole reason this module exists next to `integrations.media` rather than
inside it: `media.ResolvedMedia.text` is a narrative rendering built for
a chatbot to read, and a narrative is not something a database column can
consume without a second, lossy parse at every call site.

WHY CONFIDENCE IS PART OF THE CONTRACT
--------------------------------------
OCR on a photographed ID confuses `0/O`, `1/I`, `5/S` and `8/B`, which
produces dates that are *well-formed and wrong* — `12/05/1980` reading as
`12/05/1930`. A caller that receives a bare `date` has no way to tell that
apart from a date lifted cleanly off a digital PDF's text layer, so it
either writes both (storing guesses as facts) or writes neither (making
the extractor useless).

So `confidence` is mandatory, and the contract is that only `ALTA` is safe
to persist unattended. `BAIXA` is a suggestion for a human to confirm.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Protocol, runtime_checkable


class IdentityDocumentKind(str, Enum):
    """Classified identity-document category."""

    RG = "rg"
    CPF = "cpf"
    CNH = "cnh"
    UNKNOWN = "unknown"


class ExtractionConfidence(str, Enum):
    """How much the caller may trust a extracted field.

    ALTA — the value sat next to its own label (`DATA DE NASCIMENTO: …`)
        and passed every plausibility gate. Safe to persist unattended.
    BAIXA — a plausible value was found, but not label-anchored (or the
        text came off a rasterize→vision pass, where digit confusion is
        real). Surface it for a human to confirm; do NOT persist silently.
    NENHUMA — nothing usable. Not an error: a legible document may simply
        not carry the field.
    """

    ALTA = "alta"
    BAIXA = "baixa"
    NENHUMA = "nenhuma"


class TextSource(str, Enum):
    """Which rung of the extraction ladder produced the text.

    Recorded because it is the single best predictor of transcription
    error: a PDF text layer is exact, a vision pass over a phone photo is
    not. `confidence` is derived partly from this.
    """

    TEXT_LAYER = "texto"        # PDF's own text layer — exact
    OCR = "ocr"                 # rasterize → vision — approximate
    NENHUMA = "nenhuma"         # no text could be obtained at all


@dataclass(frozen=True)
class IdentityFields:
    """Typed fields lifted from one identity document.

    Every field is Optional: a document that is legible but simply does
    not carry a birthdate is a successful extraction with
    `data_nascimento=None`, not a failure. Failures are carried in
    `error`, so a caller can distinguish "read it, wasn't there" from
    "couldn't read it" — a distinction that decides whether retrying is
    worth anything.
    """

    kind: IdentityDocumentKind = IdentityDocumentKind.UNKNOWN
    data_nascimento: Optional[date] = None
    confidence: ExtractionConfidence = ExtractionConfidence.NENHUMA
    source: TextSource = TextSource.NENHUMA
    #: The label the date was found next to, verbatim. Kept for audit —
    #: it is what lets a human check the extractor's reasoning later
    #: without re-reading the document (which would be another LGPD
    #: content access).
    matched_label: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def persistable(self) -> bool:
        """True iff this result may be written to a record unattended.

        The one place the ALTA-only rule is expressed, so no call site has
        to re-derive it (and none can quietly get it wrong)."""
        return (
            self.data_nascimento is not None
            and self.confidence is ExtractionConfidence.ALTA
        )


@runtime_checkable
class IdentityExtractor(Protocol):
    """Bytes + mimetype → typed identity fields.

    Implementations MUST NOT raise for an unreadable/corrupt document —
    they return `IdentityFields` with `error` set. An extractor that
    raises into a background job turns a bad upload into a lost job.
    """

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> IdentityFields:
        ...


__all__ = [
    "ExtractionConfidence",
    "IdentityDocumentKind",
    "IdentityExtractor",
    "IdentityFields",
    "TextSource",
]
