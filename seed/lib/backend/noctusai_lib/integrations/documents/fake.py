"""Deterministic identity extractor — the dev/test default.

No IO, no LLM, no PyMuPDF. Every seed IO module ships one of these so a
consumer's tests exercise the real call path (`await extract(...)`,
`IdentityFields` in, out) without a network or a heavy dependency, and so
a slim environment can import the package at all.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    IdentityDocumentKind,
    IdentityFields,
    TextSource,
)


def classify_kind(
    mimetype: Optional[str] = None, filename: Optional[str] = None
) -> IdentityDocumentKind:
    """Best-effort document kind from the filename.

    Shared by both adapters so Fake and Real classify identically — a Fake
    that classified differently would let a consumer's tests pass against
    behaviour the Real adapter never exhibits.
    """
    name = (filename or "").lower()
    if "cnh" in name:
        return IdentityDocumentKind.CNH
    if "cpf" in name:
        return IdentityDocumentKind.CPF
    if "rg" in name or "identidade" in name:
        return IdentityDocumentKind.RG
    return IdentityDocumentKind.UNKNOWN


class FakeIdentityExtractor:
    """Returns a canned result, honouring the Protocol exactly.

    Defaults to a high-confidence 1980-05-12 so the happy path needs no
    setup. Pass `result=` to script a specific outcome (a low-confidence
    read, a field-absent document, a failure) — the three cases a consumer
    must branch on.
    """

    def __init__(self, result: Optional[IdentityFields] = None) -> None:
        self._result = result
        self.calls: list[tuple[int, Optional[str], Optional[str]]] = []

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> IdentityFields:
        self.calls.append((len(content or b""), mimetype, filename))
        if self._result is not None:
            return self._result
        if not content:
            return IdentityFields(
                kind=classify_kind(mimetype, filename),
                error="empty_document",
                error_message="no bytes to read",
            )
        return IdentityFields(
            kind=classify_kind(mimetype, filename),
            data_nascimento=date(1980, 5, 12),
            confidence=ExtractionConfidence.ALTA,
            source=TextSource.TEXT_LAYER,
            matched_label="DATA DE NASCIMENTO",
        )


__all__ = ["FakeIdentityExtractor", "classify_kind"]
