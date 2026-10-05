"""Field-bleed validators (divergence-email study, 2026-10-05): shapes the
extractors let through that the resolver then had to fight. Synthetic values
only — each case fails on the pre-fix code."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.documents.address import (
    EnderecoLido,
    colapsar_tipo_logradouro_duplicado,
    find_endereco,
    normalizar_logradouro,
    separar_complemento_do_bairro,
)
from noctusai_lib.integrations.documents.name import looks_like_a_name
from noctusai_lib.integrations.documents.profession import find_profissao
from noctusai_lib.integrations.documents.rg import find_rg, parece_data, rg_shape_valido


class TestProfissaoFiliacao:
    @pytest.mark.parametrize(
        "texto",
        [
            "Profissão: de Maria Aparecida e",
            "PROFISSÃO: filho de JOSE SANTOS",
            "Profissão: filha de ANA LIMA",
        ],
    )
    def test_filiation_text_is_not_a_profissao(self, texto):
        assert find_profissao(texto)[0] is None

    def test_real_profissao_still_read(self):
        assert find_profissao("Profissão: gerente financeiro")[0] == "gerente financeiro"


class TestNomeEmpresaOuCargo:
    @pytest.mark.parametrize(
        "valor",
        ["DINATECNICA IND E COM LTDA", "ENCARREGADO PERECIVEL", "ACME SERVICOS ME", "JOAO SILVA EIRELI"],
    )
    def test_company_or_job_is_not_a_name(self, valor):
        assert looks_like_a_name(valor) is False

    @pytest.mark.parametrize("valor", ["JOAO DE SA", "MARIA APARECIDA ADACHI", "Renato Modina"])
    def test_real_names_survive(self, valor):
        assert looks_like_a_name(valor) is True


class TestTitularEPessoa:
    def test_utility_issuer_is_not_a_person(self):
        assert EnderecoLido(titular="ELETROPAULO METROPOLITANA ENERGIA SA").titular_e_pessoa is False

    def test_person_and_absent(self):
        assert EnderecoLido(titular="MARIA APARECIDA ADACHI").titular_e_pessoa is True
        assert EnderecoLido().titular_e_pessoa is None


class TestBairroComplemento:
    @pytest.mark.parametrize(
        "bairro,esperado_comp",
        [("TP A AP 157", "TP A AP 157"), ("(TIPO A) PAV 2 BL 1234", "(TIPO A) PAV 2 BL 1234")],
    )
    def test_whole_bairro_is_complemento(self, bairro, esperado_comp):
        b, c = separar_complemento_do_bairro(bairro, None)
        assert b is None and c == esperado_comp

    def test_real_prefix_stays_bairro_and_complemento_appended(self):
        assert separar_complemento_do_bairro("Jardim Esmeralda AP 12 BL B", "CS 3") == (
            "Jardim Esmeralda",
            "CS 3 AP 12 BL B",
        )

    def test_clean_bairro_untouched(self):
        assert separar_complemento_do_bairro("Vila Casa Verde", None) == ("Vila Casa Verde", None)

    def test_find_endereco_moves_bleed(self):
        lido = find_endereco(
            "Endereço: RUA DAS FLORES, 10 - TP A AP 157 - CEP 06429-240\n"
            "Bairro: TP A AP 157\nCEP: 06429-240\nCidade: Carapicuiba UF: SP"
        )
        assert lido.bairro is None
        assert lido.complemento == "TP A AP 157"


class TestRg:
    @pytest.mark.parametrize("valor", ["1995092808", "28091995", "2001123104"])
    def test_date_shaped_rejected(self, valor):
        assert parece_data(valor) and not rg_shape_valido(valor)

    def test_find_rg_skips_date_shaped(self):
        assert find_rg("RG: 1995092808")[0] is None

    @pytest.mark.parametrize("valor", ["52.179.965-X", "52179965", "13.032.360-3", "V123456-7", "X-123.456-X"])
    def test_real_shapes_accepted(self, valor):
        assert rg_shape_valido(valor)

    def test_real_rg_still_found(self):
        assert find_rg("RG: 52.179.965-X")[0] == "52.179.965-X"


class TestNormalizacaoLogradouro:
    @pytest.mark.parametrize(
        "bruto,esperado",
        [
            ("Estrada EST DO EMBU", "Estrada do Embu"),
            ("Est Prof Cândido Motta Filho", "Estrada Professor Cândido Motta Filho"),
            ("AL JAGUARUNA", "Alameda JAGUARUNA"),
            ("Estrada PRF CANDIDO MOTTA FILHO", "Estrada Professor CANDIDO MOTTA FILHO"),
        ],
    )
    def test_normalizar(self, bruto, esperado):
        got = normalizar_logradouro(bruto)
        if bruto == "Estrada EST DO EMBU":
            assert got.lower() == esperado.lower()
        else:
            assert got == esperado

    def test_collapse_only_same_type(self):
        assert colapsar_tipo_logradouro_duplicado("Rua Estrada Velha") == "Rua Estrada Velha"
