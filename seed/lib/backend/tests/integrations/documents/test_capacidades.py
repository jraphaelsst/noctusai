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
            "rg", "cnh", "cpf", "certidao_casamento", "certidao_nascimento",
            "comprovante_endereco", "matricula",
        ):
            assert tipo in CAPACIDADES


class TestIdentityDocuments:
    """RG/CNH/certidões — the full `IdentityFields` vocabulary."""

    def test_full_identity_docs_claim_every_seed_campo(self):
        for tipo in ("rg", "cnh", "certidao_casamento", "certidao_nascimento"):
            assert set(IDENTITY_CAMPOS) <= CAPACIDADES[tipo]

    def test_full_identity_docs_also_claim_dependent_fields(self):
        # `rg_orgao` / `data_emissao` are real, readable fields — just not
        # independently-persistable `IdentityFields.CAMPOS` members.
        for tipo in ("rg", "cnh", "certidao_casamento", "certidao_nascimento"):
            assert "rg_orgao" in CAPACIDADES[tipo]
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
