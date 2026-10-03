"""Pacto antenupcial reader — `noctusai_lib.integrations.documents.pacto_antenupcial`.

Every identifier is SYNTHETIC: `123.456.789-09` / `412.954.238-98` are
checksum-valid documentation CPFs that belong to nobody; names, offices and
numbers are invented. The two layouts mirror the measured real shapes
(escritura itself; its Livro 3 registro citing the escritura, with the
marriage sentence broken across a page) — never a real document's text.
"""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.integrations.documents import (
    FakePactoAntenupcialExtractor,
    PactoAntenupcialExtractor,
    make_pacto_antenupcial_extractor,
    parse_pacto_antenupcial,
)
from noctusai_lib.integrations.documents.capacidades import CAPACIDADES
from noctusai_lib.integrations.documents.pacto_antenupcial import (
    LadderPactoAntenupcialExtractor,
)
from noctusai_lib.integrations.documents.types import ExtractionConfidence, TextSource

REGISTRO = """[documento PDF digitalizado] VIGÉSIMO PRIMEIRO
OFICIAL DE REGISTRO DE IMÓVEIS
LIVRO Nº 3 - REGISTRO AUXILIAR
Registro
4.321
R.4.321 em 15 de março de 2019
Prenotação 99.999 de 01 de março de 2019.
PACTO ANTENUPCIAL
Nos termos da Escritura Pública de Pacto Antenupcial lavrada em 10 de janeiro de 2019, no 7º Tabelião de Notas desta Capital (Livro 1234, folhas 056), as partes contratantes, de um lado, JOAO DA SILVA EXEMPLO, RG nº 11.111.111-1-SSP/SP, CPF nº 123.456.789-09, brasileiro, solteiro, engenheiro, e, de outro, MARIA SOUZA FICTICIA, RG nº 22.222.222-2-SSP/SP, CPF nº 412.954.238-98, brasileira, solteira, médica, CONVENCIONARAM que o regime de bens a vigorar entre eles após a realização do casamento será o da SEPARAÇÃO TOTAL DE BENS, nos termos do artigo 1.687 do Código Civil. O casamento foi

(continua no verso)

LIVRO Nº 3 - REGISTRO AUXILIAR
realizado por dito regime em 02/02/2019, continuando os contraentes a usar o mesmo nome.
"""

ESCRITURA = """REPÚBLICA FEDERATIVA DO BRASIL
3º TABELIÃO DE NOTAS DE CAMPINAS
LIVRO 0987 - FOLHAS 123/124
ESCRITURA PÚBLICA DE PACTO ANTENUPCIAL
Aos cinco dias do mês de maio de dois mil e vinte, nesta cidade, perante mim, compareceram como outorgantes e reciprocamente outorgados, de um lado, JOAO DA SILVA EXEMPLO, CPF 123.456.789-09, e de outro, MARIA SOUZA FICTICIA, CPF 412.954.238-98, que adotarão o regime da COMUNHÃO UNIVERSAL DE BENS.
"""


class TestRegistro:
    def test_le_os_fatos_da_escritura_citada(self):
        r = parse_pacto_antenupcial(REGISTRO, TextSource.OCR)
        assert r.regime_bens == "separacao_total"
        assert r.data_escritura == date(2019, 1, 10)
        assert r.tabelionato == "7º Tabelião de Notas desta Capital"
        assert (r.livro, r.folhas) == ("1234", "056")

    def test_livro_3_do_registro_nao_e_o_livro_da_escritura(self):
        r = parse_pacto_antenupcial(REGISTRO, TextSource.OCR)
        assert r.livro != "3"
        assert r.registro is not None
        assert r.registro.livro == "3 - Registro Auxiliar"
        assert r.registro.numero == "4.321"
        assert r.registro.data == date(2019, 3, 15)
        assert r.registro.cartorio == "VIGÉSIMO PRIMEIRO\nOFICIAL DE REGISTRO DE IMÓVEIS".replace("\n", " ")

    def test_data_do_casamento_atravessa_a_quebra_de_pagina(self):
        assert parse_pacto_antenupcial(REGISTRO).data_casamento == date(2019, 2, 2)

    def test_conjuges_pelo_cpf_valido(self):
        r = parse_pacto_antenupcial(REGISTRO)
        assert [(c.nome, c.cpf) for c in r.conjuges] == [
            ("JOAO DA SILVA EXEMPLO", "12345678909"),
            ("MARIA SOUZA FICTICIA", "41295423898"),
        ]

    def test_cpf_com_digito_verificador_invalido_nao_vira_conjuge(self):
        r = parse_pacto_antenupcial(REGISTRO.replace("412.954.238-98", "412.954.238-00"))
        assert [c.cpf for c in r.conjuges] == ["12345678909"]

    def test_mais_de_dois_cpfs_e_ambiguo(self):
        extra = REGISTRO + "\nProcurador: PEDRO TERCEIRO NOME, CPF 529.982.247-25.\n"
        assert parse_pacto_antenupcial(extra).conjuges == ()

    def test_confianca_do_regime_segue_a_fonte(self):
        assert parse_pacto_antenupcial(REGISTRO, TextSource.OCR).regime_bens_confianca is ExtractionConfidence.MEDIA
        assert parse_pacto_antenupcial(REGISTRO, TextSource.TEXT_LAYER).regime_bens_confianca is ExtractionConfidence.ALTA


class TestEscritura:
    def test_escritura_propria(self):
        r = parse_pacto_antenupcial(ESCRITURA, TextSource.TEXT_LAYER)
        assert r.regime_bens == "comunhao_universal"
        assert r.data_escritura == date(2020, 5, 5)
        assert r.tabelionato == "3º TABELIÃO DE NOTAS DE CAMPINAS"
        assert (r.livro, r.folhas) == ("0987", "123/124")
        assert r.registro is None
        assert len(r.conjuges) == 2


class TestNadaInventado:
    def test_texto_vazio(self):
        r = parse_pacto_antenupcial("")
        assert not r.achou_algo and r.regime_bens is None

    def test_texto_sem_pacto_nao_inventa_campos(self):
        r = parse_pacto_antenupcial("Certidão de nascimento de FULANO, nascido em 01/01/2000.")
        assert (r.regime_bens, r.data_escritura, r.tabelionato, r.registro, r.conjuges) == (
            None, None, None, None, (),
        )


class _Ladder:
    def __init__(self, texto, source=TextSource.TEXT_LAYER, err=None):
        self.texto, self.source, self.err = texto, source, err

    async def to_text(self, content, mimetype=None, filename=None, **_):
        return self.texto, self.source, self.err


class TestAdaptadores:
    @pytest.mark.asyncio
    async def test_real_le_pelo_ladder(self):
        r = await LadderPactoAntenupcialExtractor(ladder=_Ladder(REGISTRO)).extract(b"%PDF")
        assert r.regime_bens == "separacao_total" and r.source is TextSource.TEXT_LAYER

    @pytest.mark.asyncio
    async def test_real_nao_levanta_em_erro_do_ladder(self):
        r = await LadderPactoAntenupcialExtractor(
            ladder=_Ladder("", TextSource.OCR, ("vision_failed", "x"))
        ).extract(b"%PDF")
        assert r.error == "vision_failed"

    @pytest.mark.asyncio
    async def test_bytes_vazios(self):
        assert (await LadderPactoAntenupcialExtractor(ladder=_Ladder("")).extract(b"")).error == "empty_document"

    @pytest.mark.asyncio
    async def test_fake_e_o_padrao_e_tem_cpfs_validos(self):
        from noctusai_lib.integrations.documents.cpf import is_valid

        ex = make_pacto_antenupcial_extractor()
        assert isinstance(ex, FakePactoAntenupcialExtractor)
        assert isinstance(ex, PactoAntenupcialExtractor)
        r = await ex.extract(b"x")
        assert r.regime_bens and all(is_valid(c.cpf) for c in r.conjuges)

    def test_factory_real(self):
        assert isinstance(make_pacto_antenupcial_extractor(real=True), LadderPactoAntenupcialExtractor)

    def test_capacidades_declara_o_tipo(self):
        assert {"regime_bens", "conjuge"} <= CAPACIDADES["pacto_antenupcial"]
