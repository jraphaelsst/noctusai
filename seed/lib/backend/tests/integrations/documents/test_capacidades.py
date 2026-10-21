"""`CAPACIDADES` — the per-document-type extraction capability catalog."""
from __future__ import annotations

from noctusai_lib.integrations.documents.capacidades import CAPACIDADES
from noctusai_lib.integrations.documents.types import CAMPOS as IDENTITY_CAMPOS


class TestShape:
    def test_every_key_maps_to_a_non_empty_frozenset(self):
        assert CAPACIDADES
        for tipo, campos in CAPACIDADES.items():
            assert isinstance(tipo, str) and tipo
            assert isinstance(campos, frozenset)
            assert campos, f"{tipo} claims zero capability"

    def test_known_document_types_are_present(self):
        for tipo in (
            "rg", "cnh", "cin", "cpf", "certidao_casamento", "certidao_nascimento",
            "comprovante_endereco", "matricula", "serasa_crednet", "cartao_cnpj",
        ):
            assert tipo in CAPACIDADES


class TestIdentityDocuments:
    """RG/CNH/CIN/certidões — DERIVED from `autoridade.AUTORIDADE` (closes
    NOC-REMEDIATE[autoridade-capacidades-sync], 2026-10-21): what a type may
    claim is exactly what the extractor may emit."""

    def test_identity_docs_claim_exactly_their_authority_set(self):
        from noctusai_lib.integrations.documents.autoridade import AUTORIDADE, capacidades_de

        for tipo, aut in (
            ("rg", "RG"), ("cnh", "CNH"), ("cin", "CIN"),
            ("certidao_casamento", "CERTIDAO_CASAMENTO"),
            ("certidao_nascimento", "CERTIDAO_NASCIMENTO"),
        ):
            assert CAPACIDADES[tipo] == capacidades_de(aut)
            assert (set(AUTORIDADE[aut]) - {"conjuges"}) <= CAPACIDADES[tipo]
            assert set(IDENTITY_CAMPOS) >= {"nome_mae", "nome_pai", "naturalidade"}

    def test_a_type_never_claims_a_field_it_may_not_emit(self):
        assert "profissao" not in CAPACIDADES["rg"]
        assert "estado_civil" not in CAPACIDADES["cnh"]
        assert "cpf" not in CAPACIDADES["certidao_nascimento"]
        assert {"cpf", "rg", "rg_orgao"} <= CAPACIDADES["certidao_casamento"]

    def test_identity_docs_also_claim_dependent_fields(self):
        # `rg_orgao` travels with `rg`; `data_emissao` is every type's own.
        for tipo in ("rg", "cnh", "certidao_casamento"):
            assert "rg_orgao" in CAPACIDADES[tipo]
        for tipo in ("rg", "cnh", "cin", "certidao_casamento", "certidao_nascimento"):
            assert "data_emissao" in CAPACIDADES[tipo]

    def test_certidao_casamento_alone_claims_conjuge(self):
        assert "conjuge" in CAPACIDADES["certidao_casamento"]
        assert "conjuge" not in CAPACIDADES["certidao_nascimento"]
        assert "conjuge" not in CAPACIDADES["rg"]

    def test_cpf_card_is_narrower_than_a_full_identity_document(self):
        assert CAPACIDADES["cpf"] == frozenset({"nome", "cpf"})
        assert "data_nascimento" not in CAPACIDADES["cpf"]
        assert "estado_civil" not in CAPACIDADES["cpf"]


class TestAddressAndMatricula:
    def test_comprovante_endereco_is_address_only(self):
        assert CAPACIDADES["comprovante_endereco"] == frozenset({"endereco"})

    def test_matricula_claims_its_own_number(self):
        assert "numero_matricula" in CAPACIDADES["matricula"]


class TestSerasaCrednetAndCartaoCnpj:
    """P0c contract §B's two new seed extractors."""

    def test_serasa_crednet_claims_the_identity_and_compound_facts(self):
        campos = CAPACIDADES["serasa_crednet"]
        for campo in (
            "nome", "cpf", "data_nascimento", "nome_mae", "protocolo",
            "consulta_em", "participacoes", "ocorrencias",
        ):
            assert campo in campos

    def test_serasa_crednet_does_not_claim_cartao_cnpj_fields(self):
        assert "cnpj" not in CAPACIDADES["serasa_crednet"]
        assert "situacao_cadastral" not in CAPACIDADES["serasa_crednet"]

    def test_cartao_cnpj_claims_the_empresa_facts(self):
        campos = CAPACIDADES["cartao_cnpj"]
        for campo in (
            "cnpj", "razao_social", "situacao_cadastral",
            "data_situacao_cadastral", "uf",
        ):
            assert campo in campos

    def test_cartao_cnpj_does_not_claim_crednet_fields(self):
        assert "protocolo" not in CAPACIDADES["cartao_cnpj"]
        assert "participacoes" not in CAPACIDADES["cartao_cnpj"]
