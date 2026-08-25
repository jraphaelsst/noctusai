"""The matrícula extractor: the shared ladder, then the tempering rule.

Two things are actually being defended here.

1. **Rung 1 short-circuits rung 2.** The entire cost argument for this
   module family rests on a digital PDF never reaching vision. It is the
   same assertion `test_extractor.py` makes for identity documents, and it
   is repeated rather than shared because the two extractors could drift
   apart and only a per-extractor test would notice.

2. **Vision can never produce `alta`.** This is the one rule that stands
   between an OCR digit slip and a wrong property in the registry, and it
   is stricter than anything the identity extractor does.
"""
import pytest

from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    FakeMatriculaExtractor,
    MatriculaExtractor,
    MatriculaFields,
    TextSource,
    make_matricula_extractor,
)
from noctusai_lib.integrations.documents.matricula_extractor import (
    LadderMatriculaExtractor,
)

#: A heading whose matrícula number is label-anchored and unambiguous.
CERTIDAO_TEXT = (
    "REGISTRO DE IMOVEIS DA COMARCA DE SAO PAULO\n"
    "LIVRO N 2 FOLHA 145\n"
    "MATRICULA N 12.345\n"
    "IMOVEL: APARTAMENTO 71, RUA DAS ACACIAS\n"
)


class _StubResolved:
    def __init__(self, text="", error=None, error_message=None):
        self.text, self.error, self.error_message = text, error, error_message


class _StubResolver:
    """Stands in for the media resolver's vision rung."""

    def __init__(self, resolved=None):
        self._resolved = resolved or _StubResolved(text=CERTIDAO_TEXT)
        self.calls = 0

    async def resolve(self, media):
        self.calls += 1
        return self._resolved


def _extractor(resolver=None):
    return LadderMatriculaExtractor(resolver=resolver or _StubResolver())


class TestFactoryAndProtocol:
    def test_default_is_the_fake(self):
        assert isinstance(make_matricula_extractor(), FakeMatriculaExtractor)

    def test_real_selects_the_ladder(self):
        assert isinstance(
            make_matricula_extractor(real=True), LadderMatriculaExtractor
        )

    def test_both_adapters_satisfy_the_protocol(self):
        assert isinstance(FakeMatriculaExtractor(), MatriculaExtractor)
        assert isinstance(LadderMatriculaExtractor(), MatriculaExtractor)


class TestTheLadderShortCircuits:
    @pytest.mark.asyncio
    async def test_a_pdf_with_a_text_layer_never_reaches_vision(self, monkeypatch):
        """The whole cost argument in one assertion."""
        resolver = _StubResolver()
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.extract_pdf_text",
            lambda content: CERTIDAO_TEXT,
        )
        got = await _extractor(resolver).extract(
            b"%PDF-1.7", mimetype="application/pdf"
        )
        assert resolver.calls == 0
        assert got.source is TextSource.TEXT_LAYER
        assert got.numero_matricula == "12345"

    @pytest.mark.asyncio
    async def test_a_pdf_with_no_text_layer_falls_through_to_vision(
        self, monkeypatch
    ):
        resolver = _StubResolver()
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.extract_pdf_text",
            lambda content: "",
        )
        got = await _extractor(resolver).extract(
            b"%PDF-1.7", mimetype="application/pdf"
        )
        assert resolver.calls == 1
        assert got.source is TextSource.OCR

    @pytest.mark.asyncio
    async def test_an_image_goes_straight_to_vision(self):
        resolver = _StubResolver()
        got = await _extractor(resolver).extract(b"\xff\xd8", mimetype="image/jpeg")
        assert resolver.calls == 1
        assert got.source is TextSource.OCR


class TestVisionCanNeverBeTrustedUnattended:
    """🔴 The rule that keeps a misread digit out of the registry."""

    @pytest.mark.asyncio
    async def test_a_text_layer_read_is_alta_and_persistable(self, monkeypatch):
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.extract_pdf_text",
            lambda content: CERTIDAO_TEXT,
        )
        got = await _extractor().extract(b"%PDF-1.7", mimetype="application/pdf")
        assert got.numero_matricula_confianca is ExtractionConfidence.ALTA
        assert got.persistable is True
        assert got.sugestao is False

    @pytest.mark.asyncio
    async def test_the_same_text_read_by_vision_is_only_a_suggestion(self):
        """Identical text, identical label — demoted purely for its source.

        A vision pass confuses 0/O, 1/I, 5/S and 8/B, and a matrícula number
        has no plausibility gate that could catch the result. So the SOURCE
        is the whole of the evidence, and it is not enough.
        """
        got = await _extractor().extract(b"\xff\xd8", mimetype="image/jpeg")
        assert got.numero_matricula == "12345"
        assert got.numero_matricula_confianca is ExtractionConfidence.BAIXA
        assert got.persistable is False
        assert got.sugestao is True

    @pytest.mark.asyncio
    async def test_a_baixa_parse_off_a_text_layer_stays_baixa(self, monkeypatch):
        """Tempering only ever demotes — it must not promote.

        A body-only match (the heading did not survive) is `baixa` from the
        parser. Coming off an exact text layer must not launder it into
        `alta`, because the doubt is about WHICH matrícula it is, not about
        the transcription.
        """
        corpo = "AV.1 ORIGINADA DA MATRICULA N 9.876 DESTE REGISTRO"
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.extract_pdf_text",
            lambda content: corpo,
        )
        got = await _extractor().extract(b"%PDF-1.7", mimetype="application/pdf")
        assert got.numero_matricula == "9876"
        assert got.numero_matricula_confianca is ExtractionConfidence.BAIXA
        assert got.persistable is False


class TestFailuresAreReturnedNotRaised:
    """A detached job must never lose a document to an exception."""

    @pytest.mark.asyncio
    async def test_empty_bytes_are_an_error_not_a_crash(self):
        got = await _extractor().extract(b"", mimetype="application/pdf")
        assert got.error == "empty_document"
        assert got.numero_matricula is None

    @pytest.mark.asyncio
    async def test_a_resolver_exception_becomes_a_recorded_error(self):
        class _Boom:
            async def resolve(self, media):
                raise RuntimeError("vision down")

        got = await _extractor(_Boom()).extract(b"\xff\xd8", mimetype="image/jpeg")
        assert got.error == "resolver_failed"
        assert "vision down" in (got.error_message or "")

    @pytest.mark.asyncio
    async def test_a_resolver_reported_error_is_propagated(self):
        resolver = _StubResolver(_StubResolved(error="refusal", error_message="no"))
        got = await _extractor(resolver).extract(b"\xff\xd8", mimetype="image/jpeg")
        assert got.error == "refusal"

    @pytest.mark.asyncio
    async def test_legible_but_empty_is_not_an_error(self):
        """🔴 The distinction that decides whether retrying is worth anything.

        A blank page read successfully is a finished job, not a failed one.
        """
        resolver = _StubResolver(_StubResolved(text="   \n  "))
        got = await _extractor(resolver).extract(b"\xff\xd8", mimetype="image/jpeg")
        assert got.error is None
        assert got.numero_matricula is None
        assert got.presente is False

    @pytest.mark.asyncio
    async def test_a_document_with_no_labelled_number_reads_as_absent(self):
        """Read fine, number wasn't there — also not an error."""
        resolver = _StubResolver(_StubResolved(text="ESCRITURA PUBLICA DE COMPRA"))
        got = await _extractor(resolver).extract(b"\xff\xd8", mimetype="image/jpeg")
        assert got.error is None
        assert got.numero_matricula is None
        assert got.persistable is False
        assert got.sugestao is False


class TestMatriculaFieldsPredicates:
    def test_an_empty_string_counts_as_absent(self):
        """Mirrors `IdentityFields.presente` — a value of "" is a failed read
        wearing a success, and every downstream check would repeat the thought."""
        f = MatriculaFields(
            numero_matricula="",
            numero_matricula_confianca=ExtractionConfidence.ALTA,
        )
        assert f.presente is False
        assert f.persistable is False

    def test_nenhuma_is_neither_persistable_nor_a_suggestion(self):
        f = MatriculaFields(numero_matricula="123")
        assert f.persistable is False
        assert f.sugestao is False


class TestTheFake:
    @pytest.mark.asyncio
    async def test_it_returns_an_obviously_synthetic_number(self):
        """A fixture that leaks into a real screen must look fake, not plausible."""
        got = await FakeMatriculaExtractor().extract(b"x", mimetype="application/pdf")
        assert got.numero_matricula == "99999"
        assert got.persistable is True

    @pytest.mark.asyncio
    async def test_it_still_refuses_empty_bytes(self):
        got = await FakeMatriculaExtractor().extract(b"")
        assert got.error == "empty_document"
