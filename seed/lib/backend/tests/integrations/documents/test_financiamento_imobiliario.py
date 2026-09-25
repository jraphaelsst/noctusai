"""`financiamento_imobiliario` — ONE parser, TWO readers (contrato +
proposta), sharing ONE Quadro Resumo vocabulary. All names, CPFs and
values in this file are invented; the 25-page contract fixtures use a
synthetic in-memory PDF built with PyMuPDF (no real document).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from noctusai_lib.integrations.documents import (
    ContaCreditoVendedor,
    ExtractionConfidence,
    FakeContratoFinanciamentoExtractor,
    FakePropostaFinanciamentoExtractor,
    FinanciamentoImobiliarioExtractor,
    FinanciamentoImobiliarioFields,
    TextSource,
    make_contrato_financiamento_extractor,
    make_proposta_financiamento_extractor,
    parse_financiamento_imobiliario,
)
from noctusai_lib.integrations.documents.financiamento_imobiliario import (
    LadderContratoFinanciamentoExtractor,
    LadderPropostaFinanciamentoExtractor,
)
from noctusai_lib.integrations.documents.transcription import (
    TranscribedPage,
    Transcription,
)

CPF_VALIDO = "412.954.238-98"
CPF_INVALIDO = "412.954.238-99"


def _quadro(
    *,
    compra_venda: str = "VALOR DE COMPRA E VENDA: R$ 500.000,00",
    financiado: str = "VALOR FINANCIADO: R$ 400.000,00",
    fgts: str = "RECURSOS DO FGTS: R$ 20.000,00",
    recursos_proprios: str = "RECURSOS PROPRIOS: R$ 80.000,00",
    prazo: str = "PRAZO: 360 meses",
    conta: str = (
        "CONTA DE CREDITO DO VENDEDOR: BANCO: ITAU; AGENCIA: 0001; "
        f"CONTA: 99999-9; CPF DO TITULAR: {CPF_VALIDO}"
    ),
    vendedor_cpf: str = CPF_VALIDO,
) -> str:
    """A full, well-formed synthetic Quadro Resumo — the `RÓTULO: valor`
    shape `DOCUMENT_PROMPT_FINANCIAMENTO` asks for."""
    return (
        "QUADRO RESUMO\n"
        "BANCO: ITAU UNIBANCO\n"
        "NUMERO DO CONTRATO: 12345-6\n"
        f"{compra_venda}\n"
        "VALOR DE AVALIACAO: R$ 520.000,00\n"
        f"{financiado}\n"
        f"{fgts}\n"
        f"{recursos_proprios}\n"
        f"{prazo}\n"
        "TAXA NOMINAL: 9,5%\n"
        "TAXA EFETIVA: 9,9%\n"
        "SISTEMA DE AMORTIZACAO: SAC\n"
        f"COMPRADOR: Fulano de Tal - CPF: {CPF_VALIDO}\n"
        f"VENDEDOR: Ciclano da Silva - CPF: {vendedor_cpf}\n"
        f"{conta}\n"
    )


class TestFactoryAndProtocol:
    def test_contrato_default_is_the_fake(self):
        assert isinstance(
            make_contrato_financiamento_extractor(), FakeContratoFinanciamentoExtractor
        )

    def test_proposta_default_is_the_fake(self):
        assert isinstance(
            make_proposta_financiamento_extractor(), FakePropostaFinanciamentoExtractor
        )

    def test_contrato_real_selects_the_ladder(self):
        assert isinstance(
            make_contrato_financiamento_extractor(real=True),
            LadderContratoFinanciamentoExtractor,
        )

    def test_proposta_real_selects_the_ladder(self):
        assert isinstance(
            make_proposta_financiamento_extractor(real=True),
            LadderPropostaFinanciamentoExtractor,
        )

    def test_every_adapter_satisfies_the_protocol(self):
        assert isinstance(FakeContratoFinanciamentoExtractor(), FinanciamentoImobiliarioExtractor)
        assert isinstance(FakePropostaFinanciamentoExtractor(), FinanciamentoImobiliarioExtractor)
        assert isinstance(LadderContratoFinanciamentoExtractor(), FinanciamentoImobiliarioExtractor)
        assert isinstance(LadderPropostaFinanciamentoExtractor(), FinanciamentoImobiliarioExtractor)


class TestFullParse:
    def test_every_field(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.TEXT_LAYER, "contrato")
        assert f.documento == "contrato"
        assert f.banco_nome == "Itaú Unibanco S.A."
        assert f.banco_codigo == "341"
        assert f.numero_contrato == "12345-6"
        assert f.valor_compra_venda == Decimal("500000.00")
        assert f.valor_avaliacao == Decimal("520000.00")
        assert f.valor_financiado == Decimal("400000.00")
        assert f.valor_fgts == Decimal("20000.00")
        assert f.valor_recursos_proprios == Decimal("80000.00")
        assert f.prazo_meses == 360
        assert f.taxa_nominal_aa == Decimal("9.5")
        assert f.taxa_efetiva_aa == Decimal("9.9")
        assert f.sistema_amortizacao == "SAC"
        assert len(f.compradores) == 1 and f.compradores[0].cpf_valido is True
        assert len(f.vendedores) == 1 and f.vendedores[0].cpf_valido is True
        assert f.quadro_encontrado is True
        assert f.error is None

    def test_conta_credito_vendedor_is_structured(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.TEXT_LAYER, "contrato")
        conta = f.conta_credito_vendedor
        assert conta is not None
        assert conta.banco_nome == "Itaú Unibanco S.A."
        assert conta.banco_codigo == "341"
        assert conta.agencia == "0001"
        assert conta.conta == "99999-9"
        assert conta.titular_cpf == CPF_VALIDO
        assert conta.titular_cpf_valido is True

    def test_conta_credito_vendedor_absent_is_none(self):
        f = parse_financiamento_imobiliario(
            _quadro(conta="").replace("\n\n", "\n"), TextSource.TEXT_LAYER, "contrato"
        )
        assert f.conta_credito_vendedor is None


class TestQuadroEncontrado:
    def test_anchor_missing_is_not_found(self):
        texto = _quadro().replace("QUADRO RESUMO\n", "")
        f = parse_financiamento_imobiliario(texto, TextSource.TEXT_LAYER, "contrato")
        assert f.quadro_encontrado is False

    def test_anchor_alone_with_fewer_than_three_fields_is_not_found(self):
        texto = (
            "QUADRO RESUMO\n"
            "VALOR DE COMPRA E VENDA: R$ 500.000,00\n"
        )
        f = parse_financiamento_imobiliario(texto, TextSource.TEXT_LAYER, "contrato")
        assert f.quadro_encontrado is False

    def test_exactly_three_of_four_is_found(self):
        # compra_venda + financiado + prazo present; fgts/recursos_proprios
        # both absent — still 3 of 4.
        texto = (
            "QUADRO RESUMO\n"
            "VALOR DE COMPRA E VENDA: R$ 500.000,00\n"
            "VALOR FINANCIADO: R$ 400.000,00\n"
            "PRAZO: 360 meses\n"
        )
        f = parse_financiamento_imobiliario(texto, TextSource.TEXT_LAYER, "contrato")
        assert f.quadro_encontrado is True

    def test_resumo_do_financiamento_is_also_an_anchor(self):
        texto = _quadro().replace("QUADRO RESUMO", "RESUMO DO FINANCIAMENTO")
        f = parse_financiamento_imobiliario(texto, TextSource.TEXT_LAYER, "contrato")
        assert f.quadro_encontrado is True


class TestDpsTripwire:
    def test_dps_marker_short_circuits_with_no_fields(self):
        texto = "DECLARACAO PESSOAL DE SAUDE\nO proponente declara que..."
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.error == "documento_sensivel_dps"
        assert f.valor_compra_venda is None
        assert f.compradores == ()
        assert f.confiancas == {}
        assert f.rotulos == {}

    def test_dps_marker_wins_even_inside_a_full_quadro(self):
        texto = "DECLARACAO PESSOAL DE SAUDE\n" + _quadro()
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.error == "documento_sensivel_dps"
        assert f.quadro_encontrado is False

    def test_dps_variant_questionario_de_saude(self):
        texto = "QUESTIONARIO DE SAUDE\nPergunta 1: ..."
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.error == "documento_sensivel_dps"


class TestFabricationGuards:
    def test_vision_never_alta_on_money_fields(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.OCR, "contrato")
        for campo in (
            "valor_compra_venda", "valor_financiado", "valor_fgts",
            "valor_recursos_proprios",
        ):
            assert f.confiancas[campo] is not ExtractionConfidence.ALTA

    def test_quadro_sum_agreeing_promotes_to_media_even_without_extenso(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.OCR, "contrato")
        # None of this fixture's money lines carry a parenthetical extenso,
        # yet the Quadro's own arithmetic agrees (400k + 20k + 80k = 500k).
        assert f.confiancas["valor_financiado"] is ExtractionConfidence.MEDIA

    def test_quadro_sum_mismatch_caps_every_money_field_at_baixa_no_nulling(self):
        f = parse_financiamento_imobiliario(
            _quadro(recursos_proprios="RECURSOS PROPRIOS: R$ 50.000,00"),
            TextSource.OCR,
            "contrato",
        )
        assert "quadro_resumo_soma_divergente" in (f.aviso or "")
        assert f.valor_financiado == Decimal("400000.00")  # NOT nulled
        assert f.confiancas["valor_financiado"] is ExtractionConfidence.BAIXA
        assert f.confiancas["valor_recursos_proprios"] is ExtractionConfidence.BAIXA

    def test_financiado_over_compra_venda_is_nulled(self):
        f = parse_financiamento_imobiliario(
            _quadro(financiado="VALOR FINANCIADO: R$ 900.000,00"),
            TextSource.OCR,
            "contrato",
        )
        assert f.valor_financiado is None
        assert "valor_financiado_maior_que_compra_venda" in (f.aviso or "")
        assert f.confiancas["valor_financiado"] is ExtractionConfidence.NENHUMA

    def test_financiado_over_avaliacao_is_nulled(self):
        texto = _quadro().replace(
            "VALOR DE AVALIACAO: R$ 520.000,00", "VALOR DE AVALIACAO: R$ 350.000,00"
        )
        f = parse_financiamento_imobiliario(texto, TextSource.OCR, "contrato")
        assert f.valor_financiado is None
        assert "valor_financiado_maior_que_avaliacao" in (f.aviso or "")

    def test_bad_cpf_check_digit_is_never_corrected(self):
        f = parse_financiamento_imobiliario(
            _quadro(vendedor_cpf=CPF_INVALIDO), TextSource.OCR, "contrato"
        )
        assert f.vendedores[0].cpf == CPF_INVALIDO
        assert f.vendedores[0].cpf_valido is False
        assert "vendedores_cpf_digito_invalido" in (f.aviso or "")

    def test_text_layer_reaches_alta_on_money_fields(self):
        f = parse_financiamento_imobiliario(_quadro(), TextSource.TEXT_LAYER, "contrato")
        assert f.confiancas["valor_compra_venda"] is ExtractionConfidence.ALTA


class TestContratoTwoPassPageWindow:
    """The deterministic two-pass window over `DocumentTranscriber` — a
    fake, injected transcriber stands in for `documents.transcription`'s
    real ladder; the page-targeting itself is covered end-to-end in
    `test_transcription_paginas.py`."""

    class _FakeTranscriber:
        def __init__(self, respostas: dict[tuple[int, ...], Transcription]):
            self._respostas = respostas
            self.chamadas: list[list[int]] = []

        async def transcribe(self, content, *, mimetype=None, filename=None, force_vision=False, paginas=None):
            janela = list(paginas)
            self.chamadas.append(janela)
            return self._respostas[tuple(janela)]

    @pytest.mark.asyncio
    async def test_found_in_pass_one_never_reads_pass_two(self):
        t = self._FakeTranscriber(
            {
                (1, 2, 3, 4): Transcription(
                    pages=(TranscribedPage(number=1, text=_quadro(), source=TextSource.OCR),),
                    num_paginas=25,
                ),
            }
        )
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert t.chamadas == [[1, 2, 3, 4]]
        assert r.quadro_encontrado is True
        assert r.paginas_lidas == (1,)
        assert r.error is None

    @pytest.mark.asyncio
    async def test_falls_through_to_pass_two_when_not_found_in_pass_one(self):
        t = self._FakeTranscriber(
            {
                (1, 2, 3, 4): Transcription(
                    pages=tuple(
                        TranscribedPage(number=n, text="nada aqui", source=TextSource.OCR)
                        for n in (1, 2, 3, 4)
                    ),
                    num_paginas=25,
                ),
                (5, 6, 7, 8): Transcription(
                    pages=(TranscribedPage(number=5, text=_quadro(), source=TextSource.OCR),),
                    num_paginas=25,
                ),
            }
        )
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert t.chamadas == [[1, 2, 3, 4], [5, 6, 7, 8]]
        assert r.quadro_encontrado is True
        assert r.paginas_lidas == (1, 2, 3, 4, 5)

    @pytest.mark.asyncio
    async def test_not_found_in_either_pass_is_the_named_error(self):
        t = self._FakeTranscriber(
            {
                (1, 2, 3, 4): Transcription(
                    pages=tuple(
                        TranscribedPage(number=n, text="nada aqui", source=TextSource.OCR)
                        for n in (1, 2, 3, 4)
                    ),
                    num_paginas=25,
                ),
                (5, 6, 7, 8): Transcription(
                    pages=tuple(
                        TranscribedPage(number=n, text="nada aqui tambem", source=TextSource.OCR)
                        for n in (5, 6, 7, 8)
                    ),
                    num_paginas=25,
                ),
            }
        )
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert r.error == "quadro_resumo_nao_encontrado"
        assert r.paginas_lidas == (1, 2, 3, 4, 5, 6, 7, 8)

    @pytest.mark.asyncio
    async def test_never_exceeds_the_eight_page_hard_cap(self):
        """`janela_paginas=4, max_paginas_visao=8` (the defaults) never
        requests a third window."""
        t = self._FakeTranscriber(
            {
                (1, 2, 3, 4): Transcription(
                    pages=tuple(
                        TranscribedPage(number=n, text="nada", source=TextSource.OCR)
                        for n in (1, 2, 3, 4)
                    ),
                    num_paginas=25,
                ),
                (5, 6, 7, 8): Transcription(
                    pages=tuple(
                        TranscribedPage(number=n, text="nada", source=TextSource.OCR)
                        for n in (5, 6, 7, 8)
                    ),
                    num_paginas=25,
                ),
            }
        )
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        await ext.extract(b"fake-bytes", mimetype="application/pdf")
        total_paginas = sum(len(c) for c in t.chamadas)
        assert total_paginas <= 8
        assert len(t.chamadas) == 2

    @pytest.mark.asyncio
    async def test_short_document_skips_pass_two(self):
        """A document with fewer pages than the pass-2 window start never
        triggers a second call."""
        t = self._FakeTranscriber(
            {
                (1, 2, 3, 4): Transcription(
                    pages=tuple(
                        TranscribedPage(number=n, text="nada", source=TextSource.OCR)
                        for n in (1, 2, 3)
                    ),
                    num_paginas=3,
                ),
            }
        )
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert t.chamadas == [[1, 2, 3, 4]]
        assert r.error == "quadro_resumo_nao_encontrado"

    @pytest.mark.asyncio
    async def test_transcriber_failure_is_surfaced_not_swallowed(self):
        class _FailingTranscriber:
            async def transcribe(self, *a, **kw):
                return Transcription(error="missing_credentials", error_message="no key")

        ext = LadderContratoFinanciamentoExtractor(transcriber=_FailingTranscriber())
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert r.error == "missing_credentials"
        assert r.quadro_encontrado is False

    @pytest.mark.asyncio
    async def test_dps_short_circuits_before_pass_two(self):
        t = self._FakeTranscriber(
            {
                (1, 2, 3, 4): Transcription(
                    pages=(
                        TranscribedPage(
                            number=1,
                            text="DECLARACAO PESSOAL DE SAUDE\n...",
                            source=TextSource.OCR,
                        ),
                    ),
                    num_paginas=25,
                ),
            }
        )
        ext = LadderContratoFinanciamentoExtractor(transcriber=t)
        r = await ext.extract(b"fake-bytes", mimetype="application/pdf")
        assert t.chamadas == [[1, 2, 3, 4]]  # pass 2 never called
        assert r.error == "documento_sensivel_dps"


class TestEmptyAndErrors:
    @pytest.mark.asyncio
    async def test_fake_contrato_empty_document_errors(self):
        result = await FakeContratoFinanciamentoExtractor().extract(b"")
        assert result.error == "empty_document"

    @pytest.mark.asyncio
    async def test_fake_proposta_empty_document_errors(self):
        result = await FakePropostaFinanciamentoExtractor().extract(b"")
        assert result.error == "empty_document"

    @pytest.mark.asyncio
    async def test_ladder_contrato_empty_document_errors(self):
        result = await LadderContratoFinanciamentoExtractor().extract(b"")
        assert result.error == "empty_document"

    @pytest.mark.asyncio
    async def test_fake_contrato_default_reading_is_synthetic_and_consistent(self):
        result = await FakeContratoFinanciamentoExtractor().extract(b"bytes")
        assert result.error is None
        assert result.documento == "contrato"
        assert (
            result.valor_financiado + result.valor_fgts + result.valor_recursos_proprios
            == result.valor_compra_venda
        )

    @pytest.mark.asyncio
    async def test_fake_proposta_default_reading_is_synthetic(self):
        result = await FakePropostaFinanciamentoExtractor().extract(b"bytes")
        assert result.error is None
        assert result.documento == "proposta"

    def test_no_labels_found_is_all_nenhuma(self):
        f = parse_financiamento_imobiliario("nada reconhecivel aqui", TextSource.OCR, "contrato")
        assert f.valor_compra_venda is None
        assert f.error is None
        assert all(c is ExtractionConfidence.NENHUMA for c in f.confiancas.values())
