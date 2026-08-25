"""The real extractor — the two-rung ladder, then the pure parser.

WHY THIS COMPOSES `integrations.media` RATHER THAN RE-DOING IT
-------------------------------------------------------------
`media` already owns "bytes → text": PDF text layer via PyMuPDF with a
pdfminer fallback, and rasterize→vision (with refusal-retry) for scanned
documents. Re-implementing that here would fork a validated seam — which
is exactly what `products/erp-imobiliario/.../matricula_service.py` did,
and why it pays for a vision call on every page of PDFs that carry a
perfectly good text layer.

So this module owns only what `media` does not: **turning a document's
text into typed identity fields.**

THE LADDER LIVES IN `ladder.py`
-------------------------------
Choosing the cheapest rung (PDF text layer → rasterize→vision) used to be
this class's private `_to_text`. It moved to `DocumentTextLadder` the moment
a second extractor needed it — see that module's header. This class now
composes one and keeps only the identity-specific half.

Which rung answered is still recorded on the result, because it is the best
available predictor of transcription error and the thing an auditor needs
to see later.

🔴 RESIDUAL RISK, STATED PLAINLY
--------------------------------
The plausibility gate in `birthdate` catches gross OCR damage (a year of
1830, a date in 2027). It does NOT catch a confusion between two
*plausible* years — `1980` misread as `1930` passes every check this
module can make. That risk is inherent to reading a photographed
document, and it is why the consumer contract requires storing
`source` + `matched_label` as provenance: the value stays attributable and
correctable rather than becoming an anonymous fact in a column.
"""
from __future__ import annotations

import logging
from typing import Optional

from noctusai_lib.integrations.documents.birthdate import find_birthdate
from noctusai_lib.integrations.documents.gender import find_gender
from noctusai_lib.integrations.documents.fake import classify_kind
from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.name import find_name
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    IdentityFields,
    TextSource,
)

logger = logging.getLogger(__name__)


class LadderIdentityExtractor:
    """Text-layer-first, vision-second identity extractor.

    Construct via `make_identity_extractor(real=True)`.
    """

    def __init__(
        self,
        *,
        org_id: Optional[str] = None,
        document_prompt: Optional[str] = None,
        resolver=None,
    ) -> None:
        self._ladder = DocumentTextLadder(
            org_id=org_id,
            document_prompt=document_prompt,
            resolver=resolver,
        )

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> IdentityFields:
        kind = classify_kind(mimetype, filename)
        if not content:
            return IdentityFields(
                kind=kind,
                error="empty_document",
                error_message="no bytes to read",
            )

        text, source, err = await self._ladder.to_text(content, mimetype, filename)
        if err is not None:
            return IdentityFields(kind=kind, source=source, error=err[0], error_message=err[1])
        if not text.strip():
            # Legible pipeline, nothing readable in it. Not an error —
            # a caller must be able to tell this apart from a crash,
            # because retrying it is pointless.
            return IdentityFields(kind=kind, source=source)

        data, data_conf, data_label = find_birthdate(text)
        nome, nome_conf, nome_label = find_name(text)
        nome_conf = self._temper_name_confidence(nome_conf, source)
        # Gender is NOT tempered by source, unlike the name. Its alphabet has
        # two elements and its parser refuses every unlabelled single letter,
        # so an OCR pass cannot turn "Masculino" into a different VALID value —
        # it can only turn it into nothing. The name's risk is a plausible
        # misreading; this field has no plausible misreadings to make.
        genero, genero_conf, genero_label = find_gender(text)

        return IdentityFields(
            kind=kind,
            data_nascimento=data,
            data_nascimento_confianca=ExtractionConfidence(data_conf),
            data_nascimento_rotulo=data_label,
            nome=nome,
            nome_confianca=ExtractionConfidence(nome_conf),
            nome_rotulo=nome_label,
            genero=genero,
            genero_confianca=ExtractionConfidence(genero_conf),
            genero_rotulo=genero_label,
            source=source,
        )

    @staticmethod
    def _temper_name_confidence(confidence: str, source: TextSource) -> str:
        """A name read off a vision pass is a suggestion, never a fact.

        🔴 THIS IS THE GATE ON AN OVERWRITE, WHICH IS WHY IT IS STRICTER
        THAN THE BIRTHDATE'S.

        The birthdate is only ever written into an empty column, so its
        worst case is a wrong value where there was none. The name
        deliberately REPLACES whatever is already on the record — the
        official document is meant to win — so its worst case is
        destroying a correct, human-entered name.

        A PDF text layer is an exact transcription: those characters ARE
        the document's characters, and `alta` survives. A vision pass over
        a photographed card is a transcription by a model, and a
        transcription error produces a name that is well-formed, plausible
        and wrong — invisible to every structural check `name` can make.
        So it degrades to `baixa`, which routes it into the existing
        confirm/discard surface. The document still wins; a human just
        spends one click agreeing that the model read it correctly.
        """
        if confidence == "alta" and source is not TextSource.TEXT_LAYER:
            return "baixa"
        return confidence


__all__ = ["LadderIdentityExtractor"]
