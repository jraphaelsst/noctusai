"""SP Registro Civil standard certidão de casamento (deal 857, prod,
2026-10-21): the `NOMES:` label is REPEATED once per spouse, each carrying its
own name and CPF on the following line; the per-spouse qualification paragraph
opens with the gentílico ("..., brasileiro, natural de ..."); the RGs sit in
"ANOTAÇÕES DE CADASTRO: Conjuge1: RG ... Conjuge2: RG ...".

Before the fix the first spouse's same-line name was dropped (only the NEXT
lines were walked), the second spouse was read as the ONLY holder, and the
titular got the other spouse's name. Invented names, synthetic CPFs/RGs.
"""
from __future__ import annotations

import asyncio

from noctusai_lib.integrations.documents.conjuges import find_conjuges
from noctusai_lib.integrations.documents.name import find_name, find_name_conflitos
from noctusai_lib.integrations.documents.real import LadderIdentityExtractor
from noctusai_lib.integrations.documents.types import TitularEsperado

CERTIDAO_SP = (
    "REGISTRO CIVIL DAS PESSOAS NATURAIS\n\n"
    "CERTIDÃO DE CASAMENTO\n\n"
    "NOMES: Rafael Menezes do Prado\n"
    "CPF: 529.982.247-25\n"
    "NOMES: Beatriz Alencar Quintana\n"
    "CPF: 111.444.777-35\n\n"
    "MATRÍCULA: 000000 01 55 2020 2 00001 001 0000001 00\n\n"
    "NOMES COMPLETOS, DATAS DE NASCIMENTO, NATURALIDADE, NACIONALIDADE E "
    "FILIAÇÃO DOS CÔNJUGES: Rafael Menezes do Prado, brasileiro, natural de "
    "Campinas, Estado de São Paulo, nascido no dia dez de março de um mil e "
    "novecentos e oitenta e cinco (10/03/1985), filho de Aurelio Prado e de "
    "Marta Menezes.\n"
    "Beatriz Alencar Quintana, brasileira, natural de Santos, Estado de São "
    "Paulo, nascida no dia quatro de junho de um mil e novecentos e "
    "noventa (04/06/1990), filha de Hugo Quintana e de Lia Alencar.\n\n"
    "DATA DE REGISTRO DO CASAMENTO (POR EXTENSO): Doze de abril de dois mil e vinte\n"
    "DIA: 12\nMÊS: 04\nANO: 2020\n\n"
    "REGIME DE BENS DO CASAMENTO: comunhão parcial de bens\n\n"
    "NOME QUE CADA UM DOS CÔNJUGES PASSOU A UTILIZAR (QUANDO HOUVER ALTERAÇÃO): "
    "Rafael Menezes do Prado\nBeatriz Alencar Quintana\n\n"
    "AVERBAÇÕES/ANOTAÇÕES A ACRESCER: NADA CONSTA.\n\n"
    "ANOTAÇÕES DE CADASTRO: Conjuge1: RG 11.222.333-4/SSP/SP. "
    "Conjuge2: RG 55.666.777-X/SSP/SP. Nada mais me cumpria certificar.\n"
)


class TestRepeatedNomesLabel:
    def test_both_names_are_candidates_so_no_spouse_is_taken_for_the_only_holder(self):
        assert find_name_conflitos(CERTIDAO_SP) == [
            "BEATRIZ ALENCAR QUINTANA", "RAFAEL MENEZES DO PRADO",
        ]
        # Two equally-prominent holders: no single `nome` is guessed.
        assert find_name(CERTIDAO_SP)[0] is None

    def test_a_single_same_line_nomes_value_is_still_one_holder(self):
        assert find_name_conflitos("NOMES: Rafael Menezes do Prado\nCPF: 529.982.247-25\n") is None


    def test_a_column_header_starting_with_nomes_is_not_a_holder(self):
        cabecalho = (
            "NOMES COMPLETOS DE SOLTEIRO, DATAS DE NASCIMENTO, NATURALIDADE\n"
            "Rafael Menezes do Prado\nBeatriz Alencar Quintana\n"
        )
        assert "COMPLETOS DE SOLTEIRO" not in " ".join(find_name_conflitos(cabecalho) or [])


class TestEachSpouseCarriesWhatThePageSays:
    def setup_method(self):
        self.a, self.b = find_conjuges(CERTIDAO_SP)

    def test_names_and_cpfs(self):
        assert (self.a.nome, self.a.cpf) == ("RAFAEL MENEZES DO PRADO", "529.982.247-25")
        assert (self.b.nome, self.b.cpf) == ("BEATRIZ ALENCAR QUINTANA", "111.444.777-35")

    def test_birthdate_from_the_numeric_echo_in_the_own_clause(self):
        assert self.a.data_nascimento.isoformat() == "1985-03-10"
        assert self.b.data_nascimento.isoformat() == "1990-06-04"
        assert self.a.data_nascimento_confianca == "media"

    def test_nacionalidade_is_the_gentilico_that_opens_the_clause(self):
        assert self.a.nacionalidade == "brasileiro"
        assert self.b.nacionalidade == "brasileiro"

    def test_rg_and_issuer_from_the_cadastro_annotation_by_ordinal(self):
        assert (self.a.rg, self.a.rg_orgao) == ("11.222.333-4", "SSP/SP")
        assert (self.b.rg, self.b.rg_orgao) == ("55.666.777-X", "SSP/SP")
        assert self.a.rg_confianca == "media"  # positional, never alta

    def test_a_certidao_without_the_annotation_leaves_rg_empty(self):
        sem = CERTIDAO_SP.split("ANOTAÇÕES DE CADASTRO")[0]
        a, b = find_conjuges(sem)
        assert a.rg is None and b.rg_orgao is None


class _LadderFixo:
    """Hands the extractor a fixed OCR text (the vision rung's output)."""

    async def ler(self, content, mimetype, filename, **kw):
        from noctusai_lib.integrations.documents.ladder import LeituraTexto
        from noctusai_lib.integrations.documents.types import TextSource

        return LeituraTexto(CERTIDAO_SP, TextSource.OCR, None)


def test_the_titular_gets_their_own_facts_not_the_other_spouses():
    ex = LadderIdentityExtractor(ladder=_LadderFixo())
    r = asyncio.run(
        ex.extract(
            b"x", mimetype="application/pdf", filename="c.pdf",
            tipo_documento="certidao_casamento",
            titular=TitularEsperado(nome="Beatriz Alencar Quintana"),
        )
    )
    assert r.nome == "BEATRIZ ALENCAR QUINTANA"
    # Owner rule 2026-10-13 (`autoridade`): a certidão de casamento is not the
    # authoritative source of CPF/RG, so neither rides on the flat fields...
    assert r.cpf is None and r.rg is None and r.rg_orgao is None
    # ...but each spouse's entry records exactly what the page prints.
    eu = next(c for c in r.conjuges if c.titular)
    assert (eu.cpf, eu.rg, eu.rg_orgao) == ("111.444.777-35", "55.666.777-X", "SSP/SP")
    assert r.data_nascimento.isoformat() == "1990-06-04"
    assert r.nacionalidade == "brasileiro"
    assert r.estado_civil == "casado" and r.regime_bens == "comunhao_parcial"
    assert r.data_casamento.isoformat() == "2020-04-12"
    assert len(r.conjuges) == 2 and sum(c.titular for c in r.conjuges) == 1
