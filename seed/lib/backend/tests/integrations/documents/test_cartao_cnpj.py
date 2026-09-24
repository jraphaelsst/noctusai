"""`cartao_cnpj` — a Receita Cartão CNPJ (boxed-label web printout) → typed
fields.

All names, CNPJs and dates in this file are invented. `CNPJ_VALIDO`/
`CNPJ_INVALIDO` mirror `test_cnpj.py`'s own synthetic fixtures.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from noctusai_lib.integrations.documents import (
    CartaoCnpjExtractor,
    ExtractionConfidence,
    FakeCartaoCnpjExtractor,
    TextSource,
    make_cartao_cnpj_extractor,
    parse_cartao_cnpj,
)
from noctusai_lib.integrations.documents.cartao_cnpj import LadderCartaoCnpjExtractor

CNPJ_VALIDO = "11.222.333/0001-81"
CNPJ_INVALIDO = "11.222.333/0001-82"


def _cartao(
    *,
    cnpj: str = CNPJ_VALIDO,
    matriz_filial: str = "MATRIZ",
    nome_fantasia: str = "********",
    situacao_cadastral: str = "BAIXADA",
    situacao_especial: str = "********",
) -> str:
    """A full, well-formed synthetic Cartão CNPJ transcription — the
    `RÓTULO: valor` shape `DOCUMENT_PROMPT_CARTAO_CNPJ` asks for."""
    return (
        f"NUMERO DE INSCRICAO: {cnpj} {matriz_filial}\n"
        "DATA DE ABERTURA: 15/03/2010\n"
        "NOME EMPRESARIAL: RAZAO SOCIAL EXEMPLO LTDA\n"
        f"TITULO DO ESTABELECIMENTO (NOME DE FANTASIA): {nome_fantasia}\n"
        "PORTE: DEMAIS\n"
        "CODIGO E DESCRICAO DA NATUREZA JURIDICA: 206-2 - SOCIEDADE "
        "EMPRESARIA LIMITADA\n"
        "UF: SP\n"
        f"SITUACAO CADASTRAL: {situacao_cadastral}\n"
        "DATA DA SITUACAO CADASTRAL: 10/06/2021\n"
        "MOTIVO DE SITUACAO CADASTRAL: EXTINCAO POR ENCERRAMENTO "
        "LIQUIDACAO VOLUNTARIA\n"
        f"SITUACAO ESPECIAL: {situacao_especial}\n"
        "Emitido no dia 20/09/2026 as 14:33:10 (data e hora de Brasilia)\n"
    )


class TestFactoryAndProtocol:
    def test_default_is_the_fake(self):
        assert isinstance(make_cartao_cnpj_extractor(), FakeCartaoCnpjExtractor)

    def test_real_selects_the_ladder(self):
        assert isinstance(
            make_cartao_cnpj_extractor(real=True), LadderCartaoCnpjExtractor
        )

    def test_both_adapters_satisfy_the_protocol(self):
        assert isinstance(FakeCartaoCnpjExtractor(), CartaoCnpjExtractor)
        assert isinstance(LadderCartaoCnpjExtractor(), CartaoCnpjExtractor)


class TestFullParse:
    def test_every_field(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        assert f.cnpj == CNPJ_VALIDO
        assert f.cnpj_valido is True
        assert f.matriz_filial == "MATRIZ"
        assert f.data_abertura == date(2010, 3, 15)
        assert f.razao_social == "RAZAO SOCIAL EXEMPLO LTDA"
        assert f.porte == "DEMAIS"
        assert f.natureza_juridica == "206-2 - SOCIEDADE EMPRESARIA LIMITADA"
        assert f.uf == "SP"
        assert f.situacao_cadastral == "baixada"
        assert f.data_situacao_cadastral == date(2021, 6, 10)
        assert f.motivo_situacao == "EXTINCAO POR ENCERRAMENTO LIQUIDACAO VOLUNTARIA"
        assert f.emitido_em == datetime(2026, 9, 20, 14, 33, 10)
        assert f.error is None

    def test_confiancas_and_rotulos(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        for campo in (
            "cnpj", "data_abertura", "razao_social", "porte",
            "natureza_juridica", "uf", "situacao_cadastral",
            "data_situacao_cadastral", "motivo_situacao", "emitido_em",
        ):
            assert f.confiancas[campo] is ExtractionConfidence.ALTA
        assert f.rotulos["cnpj"] == "NUMERO DE INSCRICAO"
        assert f.rotulos["situacao_cadastral"] == "SITUACAO CADASTRAL"
        assert f.rotulos["emitido_em"] == "EMITIDO NO DIA"

    def test_filial(self):
        f = parse_cartao_cnpj(_cartao(matriz_filial="FILIAL"), TextSource.TEXT_LAYER)
        assert f.matriz_filial == "FILIAL"


class TestMaskedFields:
    """`********` → `None`, never the literal asterisks — and the label
    still lands in `rotulos` so a human can see the box was present."""

    def test_a_masked_field_is_none_not_the_literal_asterisks(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        assert f.nome_fantasia is None
        assert "*" not in (f.nome_fantasia or "")

    def test_the_masked_label_still_registers(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        assert f.rotulos["nome_fantasia"] == "TITULO DO ESTABELECIMENTO (NOME DE FANTASIA)"
        assert f.confiancas["nome_fantasia"] is ExtractionConfidence.NENHUMA

    def test_an_unmasked_field_is_read_normally(self):
        f = parse_cartao_cnpj(
            _cartao(nome_fantasia="FANTASIA EXEMPLO"), TextSource.TEXT_LAYER
        )
        assert f.nome_fantasia == "FANTASIA EXEMPLO"


class TestSituacaoCadastralClosedVocabulary:
    """Migration 167's CHECK constraint: `ativa`/`baixada`/`inapta`/
    `suspensa`/`nula`, else `None` — with the raw text preserved."""

    @pytest.mark.parametrize(
        "impresso,esperado",
        [("ATIVA", "ativa"), ("BAIXADA", "baixada"), ("INAPTA", "inapta"),
         ("SUSPENSA", "suspensa"), ("NULA", "nula")],
    )
    def test_every_vocabulary_word_normalises(self, impresso, esperado):
        f = parse_cartao_cnpj(
            _cartao(situacao_cadastral=impresso), TextSource.TEXT_LAYER
        )
        assert f.situacao_cadastral == esperado

    def test_an_unrecognised_value_is_none_but_the_raw_text_survives(self):
        f = parse_cartao_cnpj(
            _cartao(situacao_cadastral="PENDENTE DE REGULARIZACAO"),
            TextSource.TEXT_LAYER,
        )
        assert f.situacao_cadastral is None
        assert f.rotulos["situacao_cadastral"] == "PENDENTE DE REGULARIZACAO"
        assert f.confiancas["situacao_cadastral"] is ExtractionConfidence.NENHUMA


class TestCheckDigitDiscipline:
    def test_an_invalid_cnpj_is_flagged_never_corrected(self):
        f = parse_cartao_cnpj(_cartao(cnpj=CNPJ_INVALIDO), TextSource.TEXT_LAYER)
        assert f.cnpj == CNPJ_INVALIDO
        assert f.cnpj_valido is False
        assert f.confiancas["cnpj"] is ExtractionConfidence.BAIXA
        assert f.aviso == "cnpj_digito_invalido"

    def test_a_valid_cnpj_never_carries_an_aviso(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        assert f.aviso is None


class TestOcrNeverAlta:
    def test_a_clean_ocr_read_still_caps_every_field_at_baixa(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.OCR)
        for campo, confianca in f.confiancas.items():
            assert confianca is not ExtractionConfidence.ALTA, campo

    def test_a_text_layer_read_reaches_alta(self):
        f = parse_cartao_cnpj(_cartao(), TextSource.TEXT_LAYER)
        assert f.confiancas["cnpj"] is ExtractionConfidence.ALTA


class TestFailuresAreReturnedNotRaised:
    @pytest.mark.asyncio
    async def test_empty_bytes_are_an_error_not_a_crash(self):
        got = await LadderCartaoCnpjExtractor(resolver=None).extract(b"")
        assert got.error == "empty_document"

    @pytest.mark.asyncio
    async def test_a_resolver_exception_becomes_a_recorded_error(self):
        class _Boom:
            async def resolve(self, media):
                raise RuntimeError("vision down")

        got = await LadderCartaoCnpjExtractor(resolver=_Boom()).extract(
            b"\xff\xd8", mimetype="image/jpeg"
        )
        assert got.error == "resolver_failed"

    @pytest.mark.asyncio
    async def test_legible_but_empty_is_not_an_error(self):
        class _Stub:
            async def resolve(self, media):
                class _R:
                    text, error, error_message = "   \n  ", None, None

                return _R()

        got = await LadderCartaoCnpjExtractor(resolver=_Stub()).extract(
            b"\xff\xd8", mimetype="image/jpeg"
        )
        assert got.error is None
        assert got.cnpj is None


class TestLadderReadsThroughTheProvidedProvider:
    """🔴 Never monkeypatch our own code — drive the Ladder through its own
    injectable `resolver` seam instead."""

    @pytest.mark.asyncio
    async def test_a_pdf_with_a_text_layer_never_reaches_vision(self, monkeypatch):
        from noctusai_lib.integrations.media import PdfPage, PdfTextLayer

        texto = _cartao()

        class _Resolver:
            calls = 0

            async def resolve(self, media):
                self.calls += 1
                raise AssertionError("should never reach vision")

        resolver = _Resolver()
        monkeypatch.setattr(
            "noctusai_lib.integrations.media.classify_pdf_text_layer",
            lambda content: PdfTextLayer(
                pages=(PdfPage(number=1, text=texto, is_substantive=True, reason="stub"),),
                tooling_available=True,
            ),
        )
        got = await LadderCartaoCnpjExtractor(resolver=resolver).extract(
            b"%PDF-1.7", mimetype="application/pdf"
        )
        assert resolver.calls == 0
        assert got.source is TextSource.TEXT_LAYER
        assert got.cnpj == CNPJ_VALIDO


class TestTheFake:
    @pytest.mark.asyncio
    async def test_it_returns_obviously_synthetic_but_valid_values(self):
        got = await FakeCartaoCnpjExtractor().extract(b"x", mimetype="application/pdf")
        assert got.cnpj == CNPJ_VALIDO
        assert got.cnpj_valido is True
        assert got.razao_social == "EMPRESA FAKE SINTETICA LTDA"
        assert got.situacao_cadastral == "ativa"

    @pytest.mark.asyncio
    async def test_it_still_refuses_empty_bytes(self):
        got = await FakeCartaoCnpjExtractor().extract(b"")
        assert got.error == "empty_document"
