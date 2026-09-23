"""`classificar_tipo_provavel` — the content-based misfile signal.

Real, measured 2026-09-23: at least two CNHs uploaded typed `tipo_
documento='rg'`, a real-estate "roteiro" visit sheet uploaded typed `rg`,
and another uploaded typed `matricula` on the imóvel side. This module
never retypes anything — it only answers "what do THIS text's own markers
say", for a consumer (the product layer) to compare against what a
document was DECLARED to be.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.misfile import classificar_tipo_provavel


class TestCnh:
    def test_carteira_nacional_de_habilitacao_is_cnh(self):
        assert classificar_tipo_provavel(
            "CARTEIRA NACIONAL DE HABILITACAO / DRIVER LICENSE"
        ) == "cnh"

    def test_cnh_digital_disclaimer_page_is_cnh(self):
        # The Detran/Serpro "CNH Digital" PDF's SELECTABLE text is only the
        # provenance disclaimer — no field table at all — yet it still
        # names itself unambiguously.
        assert classificar_tipo_provavel(
            "CNH Digital\nDepartamento Nacional de Transito\n"
            "Documento assinado com certificado digital"
        ) == "cnh"

    def test_cnh_wins_over_the_shared_republica_federativa_boilerplate(self):
        texto = (
            "REPUBLICA FEDERATIVA DO BRASIL\n"
            "CARTEIRA NACIONAL DE HABILITACAO\n"
        )
        assert classificar_tipo_provavel(texto) == "cnh"


class TestRg:
    def test_carteira_de_identidade_is_rg(self):
        assert classificar_tipo_provavel(
            "REPUBLICA FEDERATIVA DO BRASIL\nCARTEIRA DE IDENTIDADE\n"
            "SECRETARIA DE SEGURANCA PUBLICA"
        ) == "rg"

    def test_registro_geral_is_rg(self):
        assert classificar_tipo_provavel("REGISTRO GERAL 52.179.965-X") == "rg"


class TestCpf:
    def test_cadastro_de_pessoas_fisicas_alone_is_cpf(self):
        assert classificar_tipo_provavel(
            "MINISTERIO DA FAZENDA\nCADASTRO DE PESSOAS FISICAS"
        ) == "cpf"


class TestCertidoes:
    def test_certidao_de_casamento_is_certidao_casamento(self):
        assert classificar_tipo_provavel(
            "REGISTRO CIVIL DAS PESSOAS NATURAIS\nCERTIDAO DE CASAMENTO"
        ) == "certidao_casamento"

    def test_certidao_de_nascimento_is_certidao_nascimento(self):
        assert classificar_tipo_provavel(
            "REGISTRO CIVIL DAS PESSOAS NATURAIS\nCERTIDAO DE NASCIMENTO"
        ) == "certidao_nascimento"


class TestNoMarkers:
    def test_a_real_estate_route_sheet_has_no_identity_markers(self):
        # Real, measured: "roteiro-2dd8b95b.pdf" uploaded typed `rg`.
        texto = (
            "Roteiro de 27/08/2026 . Ana Lima\nImovel 1 de 2\n"
            "Casa com 4 dormitorios - Granja Viana - Cotia - SP\n"
            "CONDOMINIO\nVillage Los Angeles\nENDERECO\n"
            "do Embu 2153 . Cotia/SP . 06713-100\n"
        )
        assert classificar_tipo_provavel(texto) is None

    def test_empty_text_returns_none(self):
        assert classificar_tipo_provavel("") is None
        assert classificar_tipo_provavel(None) is None  # type: ignore[arg-type]

    def test_a_comprovante_de_endereco_has_no_positive_marker(self):
        # Deliberate scope gap — see the module docstring: an address
        # document has no single boilerplate phrase this module recognises
        # positively, so it correctly returns `None` rather than guessing.
        assert classificar_tipo_provavel(
            "Endereco: R PROF ARTUR RAMOS, 123\nCEP: 01454-011\n"
            "Cidade: SAO PAULO - SP"
        ) is None
