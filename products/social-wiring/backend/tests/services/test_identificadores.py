"""`app.services.identificadores` — the product policy over the canonical
identifier registry (owner rule 2026-10-01, `KB § PATTERNS/common/
canonical-identifiers.md`), pinned with the PROD examples that motivated it.

THE FOUR LEGS (`feedback_canonicalizing_a_value_breaks_search`):
storage (`para_gravar`), display (the FE seam, pinned in vitest), search
(`chaves_do_needle` + the round trip below) and fixtures (`documentos_chave*`
derive the trigger column in Python, because mocks have no triggers).
"""
from __future__ import annotations

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.services import clientes_service as svc
from app.services import identificadores as idf

ORG = "00000000-0000-4000-8000-000000000001"


class TestParaGravar:
    def test_a_cpf_is_stored_punctuated(self):
        g = idf.para_gravar("cpf", "41295423898")
        assert (g.valor, g.canonico, g.aceito) == ("412.954.238-98", True, True)

    def test_a_cnh_rg_without_dv_is_completed_arithmetically(self):
        g = idf.para_gravar("rg", "30128742")
        assert g.valor == "30.128.742-9" and g.motivo == "dv_completado"

    def test_a_value_that_does_not_fit_is_kept_as_read_never_rewritten(self):
        # DV-OCR `15.668.564-3`: stays visible exactly as read.
        g = idf.para_gravar("rg", "15.668.564-3")
        assert (g.valor, g.canonico, g.aceito, g.motivo) == (
            "15.668.564-3", False, True, "dv_invalido",
        )

    def test_a_cpf_in_the_rg_field_is_not_written_and_says_why(self):
        g = idf.para_gravar("rg", "297.556.088-50")
        assert g.valor is None and g.aceito is False
        assert g.rejeitado_por_tipo and g.tipo_detectado == "cpf"
        assert g.motivo == "cpf_no_campo_rg"

    def test_the_cin_exception_a_cpf_equal_to_the_holders_own_is_a_legit_rg(self):
        g = idf.para_gravar("rg", "29755608850", cpf_proprio="297.556.088-50")
        assert (g.valor, g.aceito, g.motivo) == ("297.556.088-50", True, "cin_igual_ao_cpf")

    def test_the_cin_exception_does_not_cover_someone_elses_cpf(self):
        g = idf.para_gravar("rg", "297.556.088-50", cpf_proprio="412.954.238-98")
        assert g.rejeitado_por_tipo

    def test_an_rg_from_another_state_is_never_forced_into_the_sp_mask(self):
        g = idf.para_gravar("rg", "301287429", uf="MG")
        assert g.valor == "301287429" and g.canonico is False

    def test_cotia_inscricao_gets_its_municipio_mask(self):
        g = idf.para_gravar("inscricao_municipal", "232314211037700000", municipio="Cotia")
        assert g.valor == "23231.42.11.0377.00.000"

    def test_an_unknown_orgao_is_kept_as_typed_not_upper_cased(self):
        g = idf.para_gravar("orgao_expedidor", "Secretaria de Segurança de São Paulo")
        assert g.valor == "Secretaria de Segurança de São Paulo" and g.canonico is False

    def test_iirgd_is_ssp_sp(self):
        assert idf.para_gravar("orgao_expedidor", "IIRGD").valor == "SSP/SP"

    def test_empty_is_nothing(self):
        assert idf.para_gravar("cpf", "  ").valor is None


class TestIguais:
    @pytest.mark.parametrize(
        "tipo,a,b",
        [
            ("cpf", "41295423898", "412.954.238-98"),
            ("rg", "30128742", "30.128.742-9"),        # CNH without DV vs full
            ("rg", "301287429", "30.128.742-9"),
            ("orgao_expedidor", "IIRGD", "SSP/SP"),
            ("orgao_expedidor", "SSP-SP", "SSP/SP"),
            ("inscricao_municipal", "23231.42.11.0377.00.000", "232314211037700000"),
        ],
    )
    def test_format_only_differences_are_the_same_identifier(self, tipo, a, b):
        ctx = {"municipio": "Cotia"} if tipo == "inscricao_municipal" else {}
        assert idf.iguais(tipo, a, b, **ctx) is True

    @pytest.mark.parametrize(
        "tipo,a,b",
        [
            ("rg", "15.668.564-3", "16.669.554-3"),    # DV-OCR swap: different
            ("rg", "30.128.742-9", "52.179.965-X"),
            ("orgao_expedidor", "SSP", "SSP/SP"),      # undecidable != same
            ("cpf", "412.954.238-98", "529.982.247-25"),
        ],
    )
    def test_not_proven_is_not_same(self, tipo, a, b):
        assert idf.iguais(tipo, a, b) is False

    def test_cotia_inscricao_with_and_without_dv_is_one_property_but_two_dvs_are_not(self):
        sem = "23231.42.11.0377.00.000"
        assert idf.iguais("inscricao_municipal", sem, sem + "-1", municipio="Cotia") is True
        assert idf.iguais("inscricao_municipal", sem + "-1", sem + "-2", municipio="Cotia") is False

    def test_cartorio_text_versus_cns(self):
        texto = "SERVENTIA DO REGISTRO DE IMÓVEIS de Cotia - CNS: 11991-7"
        assert idf.cartorios_iguais(texto, "11991-7") is True
        assert idf.cartorios_iguais(texto, "12345-6") is False
        assert idf.cartorios_iguais("Registro de Imóveis de Cotia", "11991-7") is None


class TestNeedle:
    def test_the_rendered_value_a_bare_one_and_a_fragment_all_key_to_the_haystack(self):
        haystack = idf.documentos_chave_cliente({"cpf": "412.954.238-98", "rg": "30.128.742-9"})
        assert haystack == "41295423898 301287429"
        for typed in ("412.954.238-98", "41295423898", "412954", "30.128.742-9", "30128742", "301287"):
            assert any(k in haystack for k in idf.chaves_do_needle(typed)), typed

    def test_a_name_fragment_never_scans_the_key_column(self):
        assert idf.chaves_do_needle("joao") == []
        assert idf.chaves_do_needle("fer") == []

    def test_the_floor(self):
        assert idf.chaves_do_needle("412") == []  # CHAVE_BUSCA_MIN
        assert idf.chaves_do_needle("4129") == ["4129"]

    def test_haystack_for_a_raw_stored_value_is_the_raw_alnum(self):
        assert idf.documentos_chave_cliente({"cpf": "412.954.238-99"}) == "41295423899"  # bad DV, raw


def _clientes_client(rows: list[dict]) -> MockSupabaseClient:
    client = MockSupabaseClient()
    client.set_table_data("clientes", rows)
    return client


def _row(id_, nome, **doc) -> dict:
    row = {
        "id": id_, "org_id": ORG, "nome": nome, "celular": None, "email": None,
        "ativo": True, "chave_canonica": None, "chave_tipo": None,
        "identidade_incerta": False, "ultimo_contato_em": "2026-09-01T00:00:00+00:00",
        **doc,
    }
    # Mocks have no triggers: derive the column the way migration 187 does.
    row["documentos_chave"] = idf.documentos_chave_cliente(row)
    return row


class TestClientesSearchRoundTrip:
    """The number a card RENDERS finds the card — storage, display, search."""

    @pytest.fixture
    def client(self):
        return _clientes_client([
            _row("c1", "Fernando Souza", cpf="412.954.238-98", rg="30.128.742-9",
                 rg_orgao_expedidor="SSP/SP"),
            _row("c2", "Mariana Costa", cpf="52998224725", rg="301287429"),  # raw-stored legacy
            _row("c3", "Outra Pessoa", cpf="111.444.777-35"),
        ])

    def _ids(self, client, q):
        return sorted(c["id"] for c in svc.list_clientes(client, ORG, q=q)["items"])

    def test_the_rendered_cpf_finds_the_cliente(self, client):
        assert self._ids(client, "412.954.238-98") == ["c1"]

    def test_a_bare_cpf_finds_a_punctuated_row_and_vice_versa(self, client):
        assert self._ids(client, "41295423898") == ["c1"]
        assert self._ids(client, "529.982.247-25") == ["c2"]  # stored bare

    def test_a_fragment_across_the_punctuation_finds_it(self, client):
        assert self._ids(client, "412954") == ["c1"]
        assert self._ids(client, "982.247") == ["c2"]

    def test_an_rg_without_its_dv_finds_the_full_rg(self, client):
        # the CNH's `30128742` — both rows' RG is 30.128.742-9 in any spelling
        assert self._ids(client, "30128742") == ["c1", "c2"]

    def test_it_is_strictly_additive_to_the_name_pass(self, client):
        assert self._ids(client, "fernand") == ["c1"]

    def test_a_short_numeric_needle_does_not_match_every_row(self, client):
        assert self._ids(client, "41") == []


class TestRefinamento:
    """`orgao_refinamento` / `cartorio_refinamento` (2026-10-03): one reading
    is the other plus the detail it lacked — a deterministic relation the
    resolvers use to keep the complete reading without a human."""

    def test_orgao_with_and_without_its_uf(self):
        assert idf.orgao_refinamento("SSP/SP", "SSP") == idf.MAIS_COMPLETO_A
        assert idf.orgao_refinamento("SSP", "SSP-SP") == idf.MAIS_COMPLETO_B

    def test_orgao_not_proven(self):
        assert idf.orgao_refinamento("SERRA/SP", "SSP") is None
        assert idf.orgao_refinamento("SSP/SP", "SSP/RJ") is None
        assert idf.orgao_refinamento("SSP/SP", "SSP/SP") is None
        assert idf.orgao_refinamento(None, "SSP") is None

    def test_cartorio_locality_suffix(self):
        base = "SERVENTIA DO REGISTRO DE IMÓVEIS"
        assert idf.cartorio_refinamento(base, f"{base} de Cotia") == idf.MAIS_COMPLETO_B
        assert idf.cartorio_refinamento(f"{base} de Cotia - CNS: 11991-7", base) == idf.MAIS_COMPLETO_A
        assert idf.cartorio_refinamento(
            f"LIVRO Nº 2 - REGISTRO GERAL {base}",
            f"LIVRO Nº 2 - REGISTRO GERAL | {base} de Cotia",
        ) == idf.MAIS_COMPLETO_B

    def test_cartorio_book_header_and_formatting_are_equivalent(self):
        base = "SERVENTIA DO REGISTRO DE IMÓVEIS"
        assert idf.cartorio_refinamento(base, f"LIVRO Nº 2 - REGISTRO GERAL {base}") == idf.EQUIVALENTE
        assert idf.cartorio_refinamento(base, "serventia do registro de imoveis") == idf.EQUIVALENTE

    def test_cartorio_not_proven(self):
        assert idf.cartorio_refinamento("1º RI de Barueri", "2º RI de Barueri") is None
        assert idf.cartorio_refinamento(
            "RI de Cotia - CNS: 11991-7", "RI de Cotia - CNS: 12000-1"
        ) is None
