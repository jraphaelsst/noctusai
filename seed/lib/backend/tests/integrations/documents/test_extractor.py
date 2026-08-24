"""Ladder + Protocol conformance.

The ladder tests matter because the whole cost argument for this module
rests on rung 1 short-circuiting rung 2: if a digital PDF still reaches
vision, we have reimplemented matricula_service's mistake with extra steps.
"""
from datetime import date
from unittest.mock import patch

import pytest

from noctusai_lib.integrations.documents import (
    ExtractionConfidence,
    FakeIdentityExtractor,
    IdentityDocumentKind,
    IdentityExtractor,
    IdentityFields,
    TextSource,
    make_identity_extractor,
)
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor

RG_TEXT = "REPUBLICA FEDERATIVA DO BRASIL\nDATA DE EXPEDICAO 10/03/1995\nDATA DE NASCIMENTO 12/05/1980"


class _StubResolved:
    def __init__(self, text="", error=None, error_message=None):
        self.text, self.error, self.error_message = text, error, error_message


class _StubResolver:
    """Stands in for the media resolver's vision rung."""

    def __init__(self, resolved=None):
        self._resolved = resolved or _StubResolved(text=RG_TEXT)
        self.calls = 0

    async def resolve(self, media):
        self.calls += 1
        return self._resolved


def _extractor(resolver=None):
    return LadderIdentityExtractor(resolver=resolver or _StubResolver())


class TestFactoryAndProtocol:
    def test_default_is_the_fake(self):
        assert isinstance(make_identity_extractor(), FakeIdentityExtractor)

    def test_real_selects_the_ladder(self):
        assert isinstance(make_identity_extractor(real=True), LadderIdentityExtractor)

    def test_both_adapters_satisfy_the_protocol(self):
        assert isinstance(FakeIdentityExtractor(), IdentityExtractor)
        assert isinstance(LadderIdentityExtractor(), IdentityExtractor)


class TestLadder:
    @pytest.mark.asyncio
    async def test_pdf_with_a_text_layer_never_reaches_vision(self):
        """🔴 The cost + accuracy argument for the whole module."""
        resolver = _StubResolver()
        with patch(
            "noctusai_lib.integrations.media.extract_pdf_text", return_value=RG_TEXT
        ):
            out = await _extractor(resolver).extract(
                b"%PDF-1.4", mimetype="application/pdf", filename="rg.pdf"
            )
        assert resolver.calls == 0, "paid for a vision call on a digital PDF"
        assert out.source is TextSource.TEXT_LAYER
        assert out.data_nascimento == date(1980, 5, 12)
        assert out.data_nascimento_confianca is ExtractionConfidence.ALTA

    @pytest.mark.asyncio
    async def test_scanned_pdf_falls_through_to_vision(self):
        resolver = _StubResolver()
        with patch("noctusai_lib.integrations.media.extract_pdf_text", return_value=""):
            out = await _extractor(resolver).extract(
                b"%PDF-1.4", mimetype="application/pdf", filename="rg.pdf"
            )
        assert resolver.calls == 1
        assert out.source is TextSource.OCR
        assert out.data_nascimento == date(1980, 5, 12)

    @pytest.mark.asyncio
    async def test_image_skips_the_text_layer_rung_entirely(self):
        resolver = _StubResolver()
        out = await _extractor(resolver).extract(
            b"\xff\xd8\xff", mimetype="image/jpeg", filename="rg.jpg"
        )
        assert resolver.calls == 1
        assert out.source is TextSource.OCR


class TestFailuresAreReturnedNotRaised:
    @pytest.mark.asyncio
    async def test_resolver_exception_becomes_a_typed_error(self):
        class _Boom:
            async def resolve(self, media):
                raise RuntimeError("vision down")

        out = await _extractor(_Boom()).extract(b"x", mimetype="image/png")
        assert out.error == "resolver_failed"
        assert out.data_nascimento is None
        assert out.persistable_data_nascimento is False

    @pytest.mark.asyncio
    async def test_resolver_reported_error_is_propagated(self):
        resolver = _StubResolver(
            _StubResolved(error="pdf_tooling_unavailable", error_message="no PyMuPDF")
        )
        out = await _extractor(resolver).extract(b"x", mimetype="application/pdf")
        assert out.error == "pdf_tooling_unavailable"

    @pytest.mark.asyncio
    async def test_empty_bytes(self):
        out = await _extractor().extract(b"", mimetype="application/pdf")
        assert out.error == "empty_document"

    @pytest.mark.asyncio
    async def test_legible_but_field_absent_is_not_an_error(self):
        """Distinct from a failure: retrying it would be pointless."""
        resolver = _StubResolver(_StubResolved(text="CONTRATO DE LOCACAO"))
        out = await _extractor(resolver).extract(b"x", mimetype="image/png")
        assert out.error is None
        assert out.data_nascimento is None
        assert out.data_nascimento_confianca is ExtractionConfidence.NENHUMA


class TestPersistableIsTheOnlyWriteGate:
    def test_alta_with_a_value_is_persistable(self):
        assert IdentityFields(
            data_nascimento=date(1980, 5, 12),
            data_nascimento_confianca=ExtractionConfidence.ALTA,
        ).persistable_data_nascimento

    def test_baixa_is_never_persistable(self):
        assert not IdentityFields(
            data_nascimento=date(1980, 5, 12),
            data_nascimento_confianca=ExtractionConfidence.BAIXA,
        ).persistable_data_nascimento

    def test_alta_without_a_value_is_not_persistable(self):
        assert not IdentityFields(data_nascimento_confianca=ExtractionConfidence.ALTA).persistable_data_nascimento


class TestKindClassification:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("rg.pdf", IdentityDocumentKind.RG),
            ("identidade.jpg", IdentityDocumentKind.RG),
            ("cpf.pdf", IdentityDocumentKind.CPF),
            ("cnh-frente.png", IdentityDocumentKind.CNH),
            ("scan001.pdf", IdentityDocumentKind.UNKNOWN),
        ],
    )
    async def test_fake_and_real_agree(self, filename, expected):
        fake = await FakeIdentityExtractor().extract(b"x", filename=filename)
        real = await _extractor().extract(b"x", mimetype="image/png", filename=filename)
        assert fake.kind is expected
        assert real.kind is expected


RG_TEXT_COM_NOME = (
    "REPUBLICA FEDERATIVA DO BRASIL\n"
    "NOME\n"
    "JOAO PEREIRA DA SILVA\n"
    "FILIACAO\n"
    "ANTONIO PEREIRA DA SILVA\n"
    "MARIA APARECIDA DOS SANTOS\n"
    "DATA DE EXPEDICAO 10/03/1995\n"
    "DATA DE NASCIMENTO 12/05/1980\n"
)


class TestNameConfidenceIsTemperedByTextSource:
    """🔴 The gate that decides whether a name is written or merely offered.

    A misread name is well-formed and plausible, so nothing downstream can
    catch it. The text source is the only real evidence available: a PDF
    text layer IS the document's characters; a vision pass is a model's
    transcription of them.
    """

    @pytest.mark.asyncio
    async def test_text_layer_keeps_alta_and_is_persistable(self):
        with patch(
            "noctusai_lib.integrations.media.extract_pdf_text",
            return_value=RG_TEXT_COM_NOME,
        ):
            out = await _extractor().extract(
                b"%PDF-1.4", mimetype="application/pdf", filename="rg.pdf"
            )
        assert out.source is TextSource.TEXT_LAYER
        assert out.nome == "JOAO PEREIRA DA SILVA"
        assert out.nome_confianca is ExtractionConfidence.ALTA
        assert out.persistable_nome is True

    @pytest.mark.asyncio
    async def test_vision_pass_degrades_to_baixa_and_is_only_a_suggestion(self):
        resolver = _StubResolver(_StubResolved(text=RG_TEXT_COM_NOME))
        out = await _extractor(resolver).extract(b"\x89PNG", mimetype="image/png")

        assert resolver.calls == 1
        assert out.source is TextSource.OCR
        assert out.nome == "JOAO PEREIRA DA SILVA"
        assert out.nome_confianca is ExtractionConfidence.BAIXA
        assert out.persistable_nome is False
        assert out.sugestao_nome is True

    @pytest.mark.asyncio
    async def test_the_birthdate_is_NOT_tempered_the_same_way(self):
        """The asymmetry is deliberate, so it gets a test of its own.

        The birthdate only ever lands in an empty column and has a
        plausibility gate; the name is compared against a registration and
        has neither. Tempering both identically would either block a safe
        write or permit an unsafe one.
        """
        resolver = _StubResolver(_StubResolved(text=RG_TEXT_COM_NOME))
        out = await _extractor(resolver).extract(b"\x89PNG", mimetype="image/png")

        assert out.data_nascimento == date(1980, 5, 12)
        assert out.data_nascimento_confianca is ExtractionConfidence.ALTA
        assert out.persistable_data_nascimento is True

    @pytest.mark.asyncio
    async def test_filiacao_is_not_read_through_the_ladder_either(self):
        """The parser's guard, verified end-to-end through the adapter."""
        with patch(
            "noctusai_lib.integrations.media.extract_pdf_text",
            return_value=RG_TEXT_COM_NOME,
        ):
            out = await _extractor().extract(
                b"%PDF-1.4", mimetype="application/pdf", filename="rg.pdf"
            )
        assert "ANTONIO" not in (out.nome or "")
        assert "MARIA" not in (out.nome or "")

    @pytest.mark.asyncio
    async def test_a_document_with_no_name_label_yields_no_name(self):
        with patch(
            "noctusai_lib.integrations.media.extract_pdf_text", return_value=RG_TEXT
        ):
            out = await _extractor().extract(
                b"%PDF-1.4", mimetype="application/pdf", filename="rg.pdf"
            )
        assert out.nome is None
        assert out.nome_confianca is ExtractionConfidence.NENHUMA
        assert out.persistable_nome is False
        # …and the birthdate on the same document is still read.
        assert out.data_nascimento == date(1980, 5, 12)
