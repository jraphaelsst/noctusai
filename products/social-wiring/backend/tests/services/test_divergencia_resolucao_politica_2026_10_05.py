"""Divergence-email study (2026-10-05): confidence, policy coverage,
attestation, plausibility and normalisation. Invented values only."""
from __future__ import annotations

from datetime import date

from app.services import divergencia_resolucao as dr


def _mesmo(campo, a, b):
    return a is not None and b is not None and str(a).strip().upper() == str(b).strip().upper()


def _r(campo, atual, prop, oa="cnh", op="ficha_cadastral", **kw):
    return dr.resolver_divergencia(
        campo, valor_atual=atual, origem_atual=oa, valor_proposto=prop,
        origem_proposto=op, mesmo_valor=_mesmo, **kw,
    )


class TestConfianca:
    def test_low_confidence_never_contests_filled_value(self):
        for c in ("baixa", "nenhuma", "desconhecida"):
            d = _r("nome_oficial", "Maria Teste Silva", "Mariana Teste", confianca_proposta=c)
            assert (d.vencedor, d.regra, d.requer_humano) == ("atual", "confianca_baixa", False)

    def test_high_confidence_still_reaches_policy(self):
        d = _r("nome_oficial", "Maria Teste Silva", "Mariana Teste", oa="cnh", op="matricula",
               confianca_proposta="alta")
        assert d.regra == "tier" and d.vencedor == "atual"

    def test_value_changing_between_reads_is_low_confidence(self):
        d = _r("data_nascimento", "1980-03-10", "1980-07-10", confianca_proposta="alta",
               leituras_mesmo_documento=["1980-05-10", "1980-07-10"])
        assert d.regra == "confianca_baixa" and d.vencedor == "atual"


class TestCobertura:
    def test_endereco_has_tiers_for_ficha_and_comprovante(self):
        assert dr.precisao_de("endereco", "ficha_cadastral") is not None
        assert dr.precisao_de("endereco", "comprovante_endereco") is not None
        d = _r("endereco", "Rua Um 10", "Rua Dois 20", oa="comprovante_endereco", op="ficha_cadastral")
        assert d.regra == "tier" and d.vencedor == "proposto"

    def test_cin_has_identity_tiers(self):
        assert dr.precisao_de("rg", "cin") is not None
        assert dr.precisao_de("cpf", "cin") is not None


class TestAtestacao:
    def test_cin_does_not_attest_estado_civil(self):
        d = _r("estado_civil", "casado", "solteiro", oa="matricula", op="cin")
        assert d.regra == "fonte_nao_atesta" and d.vencedor == "atual"

    def test_inferred_solteiro_never_contests(self):
        d = _r("estado_civil", "casado", "solteiro", oa="matricula", op="certidao_nascimento",
               proposto_inferido=True)
        assert d.regra == "fonte_nao_atesta"

    def test_cnh_does_not_attest_nacionalidade(self):
        assert _r("nacionalidade", "brasileira", "estrangeira", oa="matricula", op="cnh").regra == "fonte_nao_atesta"

    def test_matricula_old_cadastro_does_not_contest_municipal(self):
        d = _r("prefeitura_cadastro_imobiliario", "111.222.3333-4", "99-88", oa="cnd_iptu", op="matricula")
        assert d.regra == "fonte_nao_atesta" and d.vencedor == "atual"


class TestPlausibilidade:
    def test_stored_minor_birth_preselects_proposed_without_applying(self):
        d = _r("data_nascimento", "2015-01-01", "1980-02-02", data_negocio=date(2026, 1, 1))
        assert d.vencedor is None and d.requer_humano and d.sugerido == "proposto"

    def test_implausible_proposed_orgao_keeps_stored(self):
        d = _r("rg_orgao_expedidor", "SSP/SP", "SERRA/SP")
        assert (d.vencedor, d.regra) == ("atual", "plausibilidade")

    def test_stored_unknown_orgao_preselects_proposed(self):
        d = _r("rg_orgao_expedidor", "SERRA/SP", "SSP/SP")
        assert d.sugerido == "proposto" and d.requer_humano

    def test_razao_social_glyph_and_truncation(self):
        d = _r("razao_social", "ACME ⚠ LTDA", "ACME COMERCIO LTDA")
        assert d.sugerido == "proposto"
        d = _r("razao_social", "ACME COMER", "ACME COMERCIO LTDA")
        assert d.sugerido == "proposto"

    def test_check_digit_failure_still_auto(self):
        d = _r("cpf", "111.111.111-11", "412.954.238-98")
        assert d.regra == "validador" and d.vencedor == "proposto"


class TestNormalizacao:
    def test_doubled_type_collapses(self):
        assert dr.normalizar_logradouro("Estrada EST do Embu") == dr.normalizar_logradouro("Estrada do Embu")

    def test_prof_prf_and_av(self):
        assert dr.normalizar_logradouro("Av Prof Teste") == dr.normalizar_logradouro("Avenida PRF Teste")

    def test_type_free_compare_and_connectors(self):
        assert dr.logradouros_equivalentes("Estrada Nova Vista", "Rua Nova Vista")
        assert dr.logradouros_equivalentes("Rua do Embu", "Rua Embu")
        assert not dr.logradouros_equivalentes("Rua Um", "Rua Dois")

    def test_resolver_treats_them_as_equal(self):
        d = _r("endereco", "Estrada EST do Embu", "Rua Embu", oa="comprovante_endereco")
        assert d.regra == "equivalencia" and not d.requer_humano

    def test_rne_rg_shape(self):
        assert dr.rg_rne_equivalente("W-123.456-X", "123456")
        assert _r("rg", "W-123.456-X", "123456").regra == "equivalencia"

    def test_name_particles(self):
        assert _r("nome_oficial", "Maria da Silva", "MARIA SILVA").regra == "equivalencia"
