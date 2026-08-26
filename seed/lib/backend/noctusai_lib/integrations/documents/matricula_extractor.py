"""Certidão de matrícula → the property's registry number. Protocol + Fake +
Real + factory.

Sibling of the identity extractor, sharing its ladder (`ladder.py`) and its
confidence vocabulary (`types.ExtractionConfidence` / `types.TextSource`), and
differing in exactly one place that matters: **how hard it tempers a
vision-read value.**

🔴 WHY THIS IS THE STRICTEST MEMBER OF THE FAMILY
-------------------------------------------------
Every other extracted field has *some* structural defence against a bad
transcription:

- a birthdate has a plausibility gate (a year of 1830 is rejected),
- a name has shape (`looks_like_a_name` refuses a run of digits),
- a gênero has a two-element alphabet, so OCR damage yields *nothing*
  rather than the other value.

A matrícula number has **none of these**. It is a bare integer whose valid
range is "whatever this cartório has issued", so `12345` misread as `12845`
is indistinguishable from a correct read by any check this module could
make — and digits are precisely where a vision pass fails (`0/O`, `1/I`,
`5/S`, `8/B`).

What a wrong number costs is also worse. A wrong birthdate is an
embarrassment on a record. A wrong matrícula number identifies a DIFFERENT
PROPERTY in the registry, and it does so silently, all the way to a cartório
rejecting the paperwork mid-sale.

So: **`alta` is reachable only off a PDF text layer.** Anything read by
vision is demoted to `baixa` unconditionally — a suggestion for a human to
confirm, never an unattended write. This is stricter than the name's
tempering (which demotes only `alta`), because for the name a `baixa` read
was already going to a human anyway; here the demotion is the whole defence.

CONSUMER CONTRACT
-----------------
Only `persistable` may be written unattended. Store `source` and
`numero_matricula_rotulo` alongside any stored value: unlike an identity
document, nobody re-reads a matrícula casually, so the provenance columns
are the only way the number stays attributable and correctable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from noctusai_lib.integrations.documents.ladder import DocumentTextLadder
from noctusai_lib.integrations.documents.matricula import find_matricula
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence,
    TextSource,
)


@dataclass(frozen=True)
class MatriculaFields:
    """What one certidão de matrícula yielded.

    A single field today. It is still a dataclass rather than a bare tuple
    for the same reason `IdentityFields` is: `error` has to be tellable
    apart from "read it fine, the number wasn't there", because only one of
    those is worth retrying — and a tuple makes that distinction positional
    and therefore easy to drop.

    Extending it (área, proprietário, ônus) means adding fields here; the
    parser stays in `matricula.py`.
    """

    numero_matricula: Optional[str] = None
    numero_matricula_confianca: ExtractionConfidence = ExtractionConfidence.NENHUMA
    #: The label the number was found next to, verbatim — what lets a human
    #: check the reasoning without re-opening the document.
    numero_matricula_rotulo: Optional[str] = None

    source: TextSource = TextSource.NENHUMA
    error: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def presente(self) -> bool:
        """Did the extractor find anything at all?

        `bool(...)` rather than `is not None`, so an empty string counts as
        absent — matching `IdentityFields.presente` so the two results are
        read the same way.
        """
        return bool(self.numero_matricula)

    @property
    def persistable(self) -> bool:
        """May this be written to `imovel_dados.numero_matricula` unattended?

        `alta` only — and see the module header for why `alta` is reachable
        only off a PDF text layer.
        """
        return (
            self.presente
            and self.numero_matricula_confianca is ExtractionConfidence.ALTA
        )

    @property
    def sugestao(self) -> bool:
        """Found, but not trusted enough to write without a human."""
        return (
            self.presente
            and self.numero_matricula_confianca is ExtractionConfidence.BAIXA
        )


@runtime_checkable
class MatriculaExtractor(Protocol):
    """Bytes + mimetype → the property's registry number.

    Implementations MUST NOT raise for an unreadable/corrupt document — they
    return `MatriculaFields` with `error` set. An extractor that raises into
    a background job turns a bad upload into a lost job.
    """

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> MatriculaFields:
        ...


class FakeMatriculaExtractor:
    """Deterministic extractor — the dev/test default.

    Returns a fixed, obviously-synthetic number so a fixture that leaks into
    a real screen is recognisable as fake rather than plausible.
    """

    #: Deliberately not a realistic-looking number.
    NUMERO = "99999"

    async def extract(
        self,
        content: bytes,
        *,
        mimetype: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> MatriculaFields:
        if not content:
            return MatriculaFields(
                error="empty_document", error_message="no bytes to read"
            )
        return MatriculaFields(
            numero_matricula=self.NUMERO,
            numero_matricula_confianca=ExtractionConfidence.ALTA,
            numero_matricula_rotulo="MATRICULA N",
            source=TextSource.TEXT_LAYER,
        )


class LadderMatriculaExtractor:
    """Text-layer-first, vision-second matrícula reader.

    Construct via `make_matricula_extractor(real=True)`.
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
    ) -> MatriculaFields:
        if not content:
            return MatriculaFields(
                error="empty_document", error_message="no bytes to read"
            )

        text, source, err = await self._ladder.to_text(content, mimetype, filename)
        if err is not None:
            return MatriculaFields(
                source=source, error=err[0], error_message=err[1]
            )
        if not text.strip():
            # Legible pipeline, nothing readable in it. Not an error — a
            # caller must be able to tell this apart from a crash, because
            # retrying it is pointless.
            return MatriculaFields(source=source)

        numero, confianca, rotulo = find_matricula(text)
        return MatriculaFields(
            numero_matricula=numero,
            numero_matricula_confianca=ExtractionConfidence(
                self._temper(confianca, source)
            ),
            numero_matricula_rotulo=rotulo,
            source=source,
        )

    @staticmethod
    def _temper(confidence: str, source: TextSource) -> str:
        """Demote anything that did not come off a PDF's own text layer.

        🔴 STRICTER THAN `_temper_name_confidence`, DELIBERATELY. That one
        demotes only `alta`, because a `baixa` name was already headed for a
        human. Here the rule is flattened to "not a text layer ⇒ not `alta`",
        which is the same demotion — but the reasoning is different and worth
        stating: for the name, tempering guards an OVERWRITE; for a matrícula
        number there is no structural check downstream at all, so tempering
        is the ONLY thing standing between a misread digit and a wrong
        property in the registry.
        """
        if confidence == "alta" and source is not TextSource.TEXT_LAYER:
            return "baixa"
        return confidence


def make_matricula_extractor(
    *,
    real: bool = False,
    org_id: Optional[str] = None,
    document_prompt: Optional[str] = None,
) -> MatriculaExtractor:
    """Return a matrícula extractor.

    Fake-by-default, the posture every seed IO module takes: a consumer that
    forgets to configure the real adapter gets deterministic behaviour, not a
    surprise LLM bill or an import error in a slim image.
    """
    if not real:
        return FakeMatriculaExtractor()
    return LadderMatriculaExtractor(org_id=org_id, document_prompt=document_prompt)


__all__ = [
    "FakeMatriculaExtractor",
    "LadderMatriculaExtractor",
    "MatriculaExtractor",
    "MatriculaFields",
    "make_matricula_extractor",
]
