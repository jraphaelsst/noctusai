"""The ficha cadastral extractor: Fake/Real/factory + the two rungs.

Widget PDFs here are built PROGRAMMATICALLY via `fitz` — synthetic,
obviously-fake values, never the real corpus (which the harness's own
privacy rule forbids reading raw). `fitz` is a hard dependency of this test
module (`pytest.importorskip`), matching how `test_matricula_extractor.py`'s
sibling handles the media/PyMuPDF stack.
"""
import pytest

fitz = pytest.importorskip("fitz")

from noctusai_lib.integrations.documents.ficha_cadastral_extractor import (
    FakeFichaCadastralExtractor,
    FichaCadastralExtractor,
    LadderFichaCadastralExtractor,
    make_ficha_cadastral_extractor,
)
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource


def _pdf_com_campos(campos: list[tuple[str, str, str]]) -> bytes:
    """`[(field_name, field_value, field_type), ...]` → a minimal one-page
    fillable PDF. `field_type` is `"Text"` or `"ComboBox"` (a synthetic
    RadioButton group is not built here — PyMuPDF's own AcroForm `Kids`
    plumbing for one is out of scope for a test fixture; the geometric
    radio decode is covered on the real P3 corpus by `measure_ficha_
    cadastral.py`'s own report instead — see this feature's delivery note)."""
    doc = fitz.open()
    page = doc.new_page()
    y = 50
    for nome, valor, tipo in campos:
        w = fitz.Widget()
        w.field_name = nome
        if tipo == "ComboBox":
            w.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
            w.choice_values = [valor]
        else:
            w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.field_value = valor
        w.rect = fitz.Rect(50, y, 400, y + 15)
        page.add_widget(w)
        y += 20
    data = doc.tobytes()
    doc.close()
    return data


CPF_VALIDO = "123.456.789-09"


class TestFactoryAndProtocol:
    def test_default_is_the_fake(self):
        assert isinstance(make_ficha_cadastral_extractor(), FakeFichaCadastralExtractor)

    def test_real_selects_the_ladder(self):
        assert isinstance(
            make_ficha_cadastral_extractor(real=True), LadderFichaCadastralExtractor
        )

    def test_both_adapters_satisfy_the_protocol(self):
        assert isinstance(FakeFichaCadastralExtractor(), FichaCadastralExtractor)
        assert isinstance(LadderFichaCadastralExtractor(), FichaCadastralExtractor)


class TestFake:
    @pytest.mark.asyncio
    async def test_empty_bytes_is_an_error_not_a_crash(self):
        got = await FakeFichaCadastralExtractor().extract(b"")
        assert got.error == "empty_document"

    @pytest.mark.asyncio
    async def test_returns_obviously_synthetic_people(self):
        got = await FakeFichaCadastralExtractor().extract(b"fake bytes")
        assert len(got.pessoas) == 1
        assert "FAKE" in got.pessoas[0].nome


class TestWidgetRung:
    @pytest.mark.asyncio
    async def test_empty_bytes_is_an_error(self):
        got = await LadderFichaCadastralExtractor().extract(b"")
        assert got.error == "empty_document"

    @pytest.mark.asyncio
    async def test_reads_a_fillable_pdf_without_any_vision_call(self):
        pdf = _pdf_com_campos(
            [
                ("Nome completo 1", "FULANO DE TAL", "Text"),
                ("CPF 1", CPF_VALIDO, "Text"),
                ("Profissão 1", "ENGENHEIRO", "Text"),
                ("Data de Nascimento 1", "15/03/1985", "Text"),
            ]
        )
        extractor = LadderFichaCadastralExtractor()
        got = await extractor.extract(pdf, mimetype="application/pdf", filename="ficha.pdf")
        assert got.error is None
        assert got.source is TextSource.TEXT_LAYER
        assert len(got.pessoas) == 1
        pessoa = got.pessoas[0]
        assert pessoa.nome == "FULANO DE TAL"
        assert pessoa.cpf == CPF_VALIDO
        assert pessoa.cpf_confianca is ExtractionConfidence.ALTA
        assert pessoa.profissao == "engenheiro"

    @pytest.mark.asyncio
    async def test_estado_civil_combobox_is_alta(self):
        pdf = _pdf_com_campos(
            [
                ("Nome completo 1", "FULANA DE TAL", "Text"),
                ("CPF 1", CPF_VALIDO, "Text"),
                ("ESTADO CIVIL", "Solteiro(a)", "ComboBox"),
                ("Profissão 1", "MEDICA", "Text"),
            ]
        )
        got = await LadderFichaCadastralExtractor().extract(
            pdf, mimetype="application/pdf", filename="fgts.pdf"
        )
        assert len(got.pessoas) == 1
        pessoa = got.pessoas[0]
        assert pessoa.estado_civil == "solteiro"
        assert pessoa.estado_civil_confianca is ExtractionConfidence.ALTA

    @pytest.mark.asyncio
    async def test_a_bank_account_row_alone_yields_no_person(self):
        """Name + CPF with nothing else beside it — a re-print for payment
        purposes, not a person's own registration block."""
        pdf = _pdf_com_campos(
            [
                ("Nome do vendedor do imóvel", "FULANO DE TAL", "Text"),
                ("CPF_7", CPF_VALIDO, "Text"),
            ]
        )
        got = await LadderFichaCadastralExtractor().extract(
            pdf, mimetype="application/pdf", filename="ficha.pdf"
        )
        assert got.pessoas == ()


class _StubResolved:
    def __init__(self, text=""):
        self.text, self.error, self.error_message = text, None, None


class _StubResolver:
    def __init__(self, text: str):
        self._text = text
        self.calls = 0

    async def resolve(self, media):
        self.calls += 1
        return _StubResolved(text=self._text)


class TestVisionFallback:
    """No fillable fields at all (a flattened copy, or — measured on the P3
    corpus — a scanned FGTS form) falls through to the shared ladder, whose
    text is read by `ficha_cadastral_texto.parse_texto` — the REAL parser,
    not a stub, so this also exercises that module end to end."""

    @pytest.mark.asyncio
    async def test_a_pdf_with_no_widgets_falls_through_to_vision(self, monkeypatch):
        from noctusai_lib.integrations.media import PdfTextLayer

        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer",
            lambda content: PdfTextLayer(pages=(), tooling_available=True),
        )
        texto = (
            "Nome completo: FULANO DE TAL\n"
            f"CPF: {CPF_VALIDO}\n"
            "Profissão: PEDREIRO\n"
        )
        resolver = _StubResolver(texto)
        extractor = LadderFichaCadastralExtractor(resolver=resolver)

        pdf_sem_campos = fitz.open()
        pdf_sem_campos.new_page()
        data = pdf_sem_campos.tobytes()
        pdf_sem_campos.close()

        got = await extractor.extract(data, mimetype="application/pdf", filename="scan.pdf")
        assert resolver.calls == 1
        assert got.source is TextSource.OCR
        assert len(got.pessoas) == 1
        pessoa = got.pessoas[0]
        assert pessoa.cpf == CPF_VALIDO
        # Off a vision pass — tempered, never `ALTA`. See `ficha_cadastral_
        # texto.py`'s own module docstring.
        assert pessoa.cpf_confianca is ExtractionConfidence.BAIXA

    @pytest.mark.asyncio
    async def test_no_text_at_all_is_not_an_error(self, monkeypatch):
        from noctusai_lib.integrations.media import PdfTextLayer

        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer",
            lambda content: PdfTextLayer(pages=(), tooling_available=True),
        )
        resolver = _StubResolver("")
        extractor = LadderFichaCadastralExtractor(resolver=resolver)

        pdf_sem_campos = fitz.open()
        pdf_sem_campos.new_page()
        data = pdf_sem_campos.tobytes()
        pdf_sem_campos.close()

        got = await extractor.extract(data, mimetype="application/pdf", filename="scan.pdf")
        assert got.error is None
        assert got.pessoas == ()
