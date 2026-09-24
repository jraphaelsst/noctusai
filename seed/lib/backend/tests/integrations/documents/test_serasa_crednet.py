"""`serasa_crednet` — a Serasa Crednet consulta (table-shaped web printout)
→ typed fields.

All names, CPFs and CNPJs in this file are invented. `VALIDO`/`INVALIDO`
mirror `test_cpf.py`/`test_cnpj.py`'s own synthetic fixtures — reused, not
reinvented, per this package's N=2 recurrence rule.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from noctusai_lib.integrations.documents import (
    CrednetExtractor,
    ExtractionConfidence,
    FakeCrednetExtractor,
    OcorrenciaCrednet,
    TextSource,
    make_crednet_extractor,
    parse_crednet,
)
from noctusai_lib.integrations.documents.serasa_crednet import LadderCrednetExtractor

#: The classic synthetic test CPF/CNPJ — checksum-valid, not a real
#: registration (same fixtures `test_cpf.py`/`test_cnpj.py` use).
CPF_VALIDO = "412.954.238-98"
CPF_INVALIDO = "412.954.238-99"
CNPJ_VALIDO = "11.222.333/0001-81"
CNPJ_INVALIDO = "11.222.333/0001-82"


def _consulta(
    *,
    cpf: str = CPF_VALIDO,
    protocolo: str = "112566",
    ocorrencias: str = (
        "| Pendencias Internas | NAO CONSTAM OCORRENCIAS |\n"
        "| Pendencias Financeiras | NAO CONSTAM OCORRENCIAS |\n"
        "| Protesto Estadual | UF nao informada na consulta | "
        "NAO CONSTAM OCORRENCIAS |\n"
        "| Cheques Sem Fundo BACEN | NAO CONSTAM OCORRENCIAS |\n"
    ),
    participacoes: str = (
        "Participacao Societaria\n"
        "| Empresa | CNPJ | Participacao (%) | UF |\n"
        f"| RAZAO SOCIAL EXEMPLO UM LTDA | {CNPJ_VALIDO} | 100,0 % | RJ |\n"
        "SITUACAO DO CNPJ EM 15/05/2025: BAIXADA | Desde: mai/2025 | "
        "Ultima Atualizacao: dez/2025\n"
        "| Empresa | CNPJ | Participacao (%) | UF |\n"
        f"| RAZAO SOCIAL EXEMPLO DOIS LTDA | {CNPJ_VALIDO} | 50,0 % | SP |\n"
        "SITUACAO DO CNPJ EM 20/06/2024: ATIVA | Desde: jan/2010 | "
        "Ultima Atualizacao: jan/2026\n"
    ),
) -> str:
    """A full, well-formed synthetic Crednet transcription — the pipe-table
    shape `DOCUMENT_PROMPT_CREDNET` asks the vision rung for."""
    return (
        "25 de Agosto de 2026 15:28:22\n"
        f"PROTOCOLO DA CONSULTA : {protocolo}\n"
        "Resumo da consulta\n"
        "| CPF | NOME | NOME DA MAE | DATA NASCIMENTO |\n"
        f"| {cpf} | FULANO DE TAL SILVA | CICLANA DE TAL SILVA | 01/01/1980 |\n"
        "Ocorrencias\n"
        f"{ocorrencias}"
        "Detalhes do documento\n"
        "Situacao do CPF/CNPJ em 01/09/2026: REGULAR\n"
        f"{participacoes}"
    )


class TestFactoryAndProtocol:
    def test_default_is_the_fake(self):
        assert isinstance(make_crednet_extractor(), FakeCrednetExtractor)

    def test_real_selects_the_ladder(self):
        assert isinstance(make_crednet_extractor(real=True), LadderCrednetExtractor)

    def test_both_adapters_satisfy_the_protocol(self):
        assert isinstance(FakeCrednetExtractor(), CrednetExtractor)
        assert isinstance(LadderCrednetExtractor(), CrednetExtractor)


class TestFullParse:
    """The whole document, cleanly read."""

    def test_scalar_fields(self):
        f = parse_crednet(_consulta(), TextSource.TEXT_LAYER)
        assert f.protocolo == "112566"
        assert f.consulta_em == datetime(2026, 8, 25, 15, 28, 22)
        assert f.cpf == CPF_VALIDO
        assert f.cpf_valido is True
        assert f.nome == "FULANO DE TAL SILVA"
        assert f.nome_mae == "CICLANA DE TAL SILVA"
        assert f.data_nascimento == date(1980, 1, 1)
        assert f.cpf_situacao == "REGULAR"
        assert f.cpf_situacao_em == date(2026, 9, 1)
        assert f.error is None

    def test_confiancas_and_rotulos_are_populated_for_every_scalar_field(self):
        f = parse_crednet(_consulta(), TextSource.TEXT_LAYER)
        for campo in (
            "protocolo", "cpf", "nome", "nome_mae", "data_nascimento",
            "cpf_situacao", "consulta_em",
        ):
            assert f.confiancas[campo] is ExtractionConfidence.ALTA
        assert f.rotulos["protocolo"] == "PROTOCOLO DA CONSULTA"
        assert f.rotulos["cpf"] == "CPF"
        assert f.rotulos["nome_mae"] == "NOME DA MAE"


class TestMultipleParticipacoes:
    def test_both_entries_are_read_independently(self):
        f = parse_crednet(_consulta(), TextSource.TEXT_LAYER)
        assert len(f.participacoes) == 2

        um, dois = f.participacoes
        assert um.razao_social == "RAZAO SOCIAL EXEMPLO UM LTDA"
        assert um.participacao_pct == Decimal("100.0")
        assert um.uf == "RJ"
        assert um.situacao_texto == "BAIXADA"
        assert um.situacao_em == date(2025, 5, 15)
        assert um.desde == "MAI/2025"

        assert dois.razao_social == "RAZAO SOCIAL EXEMPLO DOIS LTDA"
        assert dois.participacao_pct == Decimal("50.0")
        assert dois.uf == "SP"
        assert dois.situacao_texto == "ATIVA"
        assert dois.situacao_em == date(2024, 6, 20)

    def test_both_cnpjs_verify_and_are_alta(self):
        f = parse_crednet(_consulta(), TextSource.TEXT_LAYER)
        for p in f.participacoes:
            assert p.cnpj_valido is True
            assert p.confianca is ExtractionConfidence.ALTA

    def test_situacao_em_never_leaks_into_any_other_field(self):
        """🔴 E2 — the Crednet-cached Receita date is per-participação only.

        It must never end up on `cpf_situacao_em` (a different section of
        the document entirely) nor bleed from one participação into the
        other's own `situacao_em`."""
        f = parse_crednet(_consulta(), TextSource.TEXT_LAYER)
        um, dois = f.participacoes
        assert f.cpf_situacao_em == date(2026, 9, 1)
        assert um.situacao_em != f.cpf_situacao_em
        assert um.situacao_em != dois.situacao_em
        assert dois.situacao_em == date(2024, 6, 20)


class TestOcorrenciasTristate:
    """`NAO CONSTAM` ⇒ False · a count ⇒ True · unreadable ⇒ None."""

    def test_nao_constam_is_false_on_every_row(self):
        f = parse_crednet(_consulta(), TextSource.TEXT_LAYER)
        for o in (
            f.pendencias_internas, f.pendencias_financeiras,
            f.protesto_estadual, f.cheques_sem_fundo,
        ):
            assert o.constam is False
        assert f.ocorrencias_constam() is False

    def test_a_count_row_is_true_and_carries_its_own_values(self):
        texto = _consulta(
            ocorrencias=(
                "| Pendencias Internas | NAO CONSTAM OCORRENCIAS |\n"
                "| Pendencias Financeiras | NAO CONSTAM OCORRENCIAS |\n"
                "| Protesto Estadual | NAO CONSTAM OCORRENCIAS |\n"
                "| Cheques Sem Fundo BACEN | 2 | R$ 1.234,56 | 20/01/2024 |\n"
            )
        )
        f = parse_crednet(texto, TextSource.TEXT_LAYER)
        assert f.cheques_sem_fundo.constam is True
        assert f.cheques_sem_fundo.quantidade == 2
        assert f.cheques_sem_fundo.valor == Decimal("1234.56")
        assert f.cheques_sem_fundo.ultimo_registro == date(2024, 1, 20)
        assert f.ocorrencias_constam() is True

    def test_a_missing_row_is_unreadable_not_a_clean_negative(self):
        texto = _consulta(ocorrencias="")
        f = parse_crednet(texto, TextSource.TEXT_LAYER)
        assert f.pendencias_internas == OcorrenciaCrednet()
        assert f.pendencias_internas.constam is None
        assert f.ocorrencias_constam() is None

    def test_any_true_wins_over_an_unreadable_sibling_row(self):
        texto = _consulta(
            ocorrencias=(
                "| Pendencias Internas | NAO CONSTAM OCORRENCIAS |\n"
                "| Cheques Sem Fundo BACEN | 1 | R$ 10,00 | 01/01/2020 |\n"
            )
        )
        f = parse_crednet(texto, TextSource.TEXT_LAYER)
        # `pendencias_financeiras`/`protesto_estadual` are unreadable here
        # (their row was never printed), yet a confirmed hit elsewhere must
        # still surface — a suspect record is never masked by noise.
        assert f.pendencias_financeiras.constam is None
        assert f.ocorrencias_constam() is True


class TestCheckDigitDiscipline:
    """A failed check digit demotes and warns, and NEVER corrects the value."""

    def test_an_invalid_cpf_is_flagged_never_corrected(self):
        f = parse_crednet(_consulta(cpf=CPF_INVALIDO), TextSource.TEXT_LAYER)
        assert f.cpf == CPF_INVALIDO
        assert f.cpf_valido is False
        assert f.confiancas["cpf"] is ExtractionConfidence.BAIXA
        assert f.aviso is not None and "cpf_digito_invalido" in f.aviso

    def test_an_invalid_participacao_cnpj_is_flagged_never_corrected(self):
        texto = _consulta(
            participacoes=(
                "Participacao Societaria\n"
                "| Empresa | CNPJ | Participacao (%) | UF |\n"
                f"| RAZAO SOCIAL EXEMPLO LTDA | {CNPJ_INVALIDO} | 100,0 % | RJ |\n"
                "SITUACAO DO CNPJ EM 15/05/2025: BAIXADA\n"
            )
        )
        f = parse_crednet(texto, TextSource.TEXT_LAYER)
        (p,) = f.participacoes
        assert p.cnpj == CNPJ_INVALIDO
        assert p.cnpj_valido is False
        assert p.confianca is ExtractionConfidence.BAIXA
        assert f.aviso is not None and "cnpj_digito_invalido" in f.aviso

    def test_both_avisos_combine_when_both_fail(self):
        texto = _consulta(
            cpf=CPF_INVALIDO,
            participacoes=(
                "Participacao Societaria\n"
                "| Empresa | CNPJ | Participacao (%) | UF |\n"
                f"| RAZAO SOCIAL EXEMPLO LTDA | {CNPJ_INVALIDO} | 100,0 % | RJ |\n"
                "SITUACAO DO CNPJ EM 15/05/2025: BAIXADA\n"
            ),
        )
        f = parse_crednet(texto, TextSource.TEXT_LAYER)
        assert "cpf_digito_invalido" in f.aviso
        assert "cnpj_digito_invalido" in f.aviso

    def test_a_valid_cpf_never_carries_an_aviso(self):
        f = parse_crednet(_consulta(), TextSource.TEXT_LAYER)
        assert f.aviso is None


class TestOcrNeverAlta:
    """🔴 Vision-read identifiers are capped at `baixa` — the OCR rung
    always runs against a real Crednet PDF (image-only), so this is the
    rule that actually applies to production, not the exception."""

    def test_a_clean_ocr_read_still_caps_every_field_at_baixa(self):
        f = parse_crednet(_consulta(), TextSource.OCR)
        for campo, confianca in f.confiancas.items():
            assert confianca is not ExtractionConfidence.ALTA, campo

    def test_a_text_layer_read_reaches_alta(self):
        """Tempering only demotes off a non-text-layer source — a real
        text layer is untouched."""
        f = parse_crednet(_consulta(), TextSource.TEXT_LAYER)
        assert f.confiancas["cpf"] is ExtractionConfidence.ALTA

    def test_participacao_confianca_is_also_capped_off_ocr(self):
        f = parse_crednet(_consulta(), TextSource.OCR)
        for p in f.participacoes:
            assert p.confianca is not ExtractionConfidence.ALTA


class TestFailuresAreReturnedNotRaised:
    @pytest.mark.asyncio
    async def test_empty_bytes_are_an_error_not_a_crash(self):
        got = await LadderCrednetExtractor(resolver=None).extract(b"")
        assert got.error == "empty_document"

    @pytest.mark.asyncio
    async def test_a_resolver_exception_becomes_a_recorded_error(self):
        class _Boom:
            async def resolve(self, media):
                raise RuntimeError("vision down")

        got = await LadderCrednetExtractor(resolver=_Boom()).extract(
            b"\xff\xd8", mimetype="image/jpeg"
        )
        assert got.error == "resolver_failed"
        assert "vision down" in (got.error_message or "")

    @pytest.mark.asyncio
    async def test_legible_but_empty_is_not_an_error(self):
        class _Stub:
            async def resolve(self, media):
                class _R:
                    text, error, error_message = "   \n  ", None, None

                return _R()

        got = await LadderCrednetExtractor(resolver=_Stub()).extract(
            b"\xff\xd8", mimetype="image/jpeg"
        )
        assert got.error is None
        assert got.protocolo is None


class TestLadderReadsThroughTheProvidedProvider:
    """🔴 Never monkeypatch our own code — drive the Ladder through its own
    injectable `resolver` seam instead."""

    @pytest.mark.asyncio
    async def test_a_pdf_with_a_text_layer_never_reaches_vision(self, monkeypatch):
        from noctusai_lib.integrations.media import PdfPage, PdfTextLayer

        texto = _consulta()

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
        got = await LadderCrednetExtractor(resolver=resolver).extract(
            b"%PDF-1.7", mimetype="application/pdf"
        )
        assert resolver.calls == 0
        assert got.source is TextSource.TEXT_LAYER
        assert got.protocolo == "112566"

    @pytest.mark.asyncio
    async def test_max_pages_none_is_forwarded_so_page_two_is_never_dropped(self):
        """`make_crednet_extractor`'s own contract: `max_pages=None` reads
        every page, because participações can sit on page 2."""
        extractor = make_crednet_extractor(real=True)
        assert isinstance(extractor, LadderCrednetExtractor)
        assert extractor._ladder._max_pages is None


class TestTheFake:
    @pytest.mark.asyncio
    async def test_it_returns_obviously_synthetic_but_valid_values(self):
        got = await FakeCrednetExtractor().extract(b"x", mimetype="application/pdf")
        assert got.cpf == CPF_VALIDO
        assert got.cpf_valido is True
        assert got.nome == "FULANO DE TAL SILVA"
        assert len(got.participacoes) == 1
        assert got.participacoes[0].cnpj_valido is True
        assert got.ocorrencias_constam() is False

    @pytest.mark.asyncio
    async def test_it_still_refuses_empty_bytes(self):
        got = await FakeCrednetExtractor().extract(b"")
        assert got.error == "empty_document"
