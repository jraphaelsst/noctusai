"""The trust gate after the primary read (`confianca.avaliar`): one test per
rule, deterministic, no model call."""
from __future__ import annotations

from datetime import date

from noctusai_lib.integrations.documents import confianca
from noctusai_lib.integrations.documents.types import (
    ExtractionConfidence as C,
    IdentityFields,
    TextSource,
)

CPF_OK = "412.954.238-98"
CPF_DV_RUIM = "412.954.238-99"


def _f(**kw) -> IdentityFields:
    return IdentityFields(source=TextSource.OCR, **kw)


def _v(fields, tipo="cnh", **kw):
    return confianca.avaliar(fields, tipo, **kw)


class TestFieldRules:
    def test_cpf_with_verified_check_digit_and_alta_is_confiavel(self):
        v = _v(_f(cpf=CPF_OK, cpf_confianca=C.ALTA), medir_precisao=False)["cpf"]
        assert v.estado == confianca.CONFIAVEL and "dv_verificado" in v.motivos

    def test_cpf_check_digit_failure_is_duvidoso(self):
        v = _v(_f(cpf=CPF_DV_RUIM, cpf_confianca=C.ALTA), medir_precisao=False)["cpf"]
        assert v.duvidoso and "dv_invalido" in v.motivos

    def test_cpf_at_baixa_is_doubt_even_with_a_valid_dv(self):
        # The benchmark's DV-valid wrong CPF came at `baixa`. A verified DV
        # clears the SOFT doubt, so the read stays trusted only when nothing
        # harder is wrong.
        v = _v(_f(cpf=CPF_OK, cpf_confianca=C.BAIXA), medir_precisao=False)["cpf"]
        assert "confianca_parser_baixa" in v.motivos
        assert v.estado == confianca.CONFIAVEL  # dv_verificado clears the soft reason

    def test_rg_sp_check_digit_failure(self):
        v = _v(_f(rg="52.179.965-1", rg_orgao="SSP/SP", rg_confianca=C.BAIXA), "rg",
               medir_precisao=False)["rg"]
        assert v.duvidoso and "dv_invalido" in v.motivos

    def test_rne_mask(self):
        assert _v(_f(rne="W573678Z", rne_confianca=C.ALTA), "rne", medir_precisao=False)["rne"].estado == confianca.CONFIAVEL
        v = _v(_f(rne="573678", rne_confianca=C.ALTA), "rne", medir_precisao=False)["rne"]
        assert v.duvidoso and "mascara_invalida" in v.motivos

    def test_certidao_matricula_check_digit(self):
        # The seed's RCPN DV (`identificador._rcpn_dv`) verified 13/13 real
        # consensus matrículas in the 2026-10-13 benchmark.
        from noctusai_lib.primitives.identificador import _rcpn_dv

        base = "123456" + "01" + "55" + "2020" + "2" + "00012" + "123" + "1234567"
        boa = base + _rcpn_dv(base)
        ruim = base + ("00" if _rcpn_dv(base) != "00" else "11")
        ok = _v(_f(matricula_certidao=boa), "certidao_casamento", medir_precisao=False)
        nok = _v(_f(matricula_certidao=ruim), "certidao_casamento", medir_precisao=False)
        assert "dv_invalido" in nok["matricula_certidao"].motivos
        assert ok["matricula_certidao"].estado == confianca.CONFIAVEL

    def test_vocabularies(self):
        v = _v(_f(estado_civil="uniao_estavel", estado_civil_confianca=C.ALTA,
                  regime_bens="comunhao_qualquer", regime_bens_confianca=C.ALTA),
               "certidao_casamento", medir_precisao=False)
        assert "vocabulario_invalido" in v["estado_civil"].motivos
        assert "vocabulario_invalido" in v["regime_bens"].motivos
        p = _v(_f(profissao="XYZW QWERTY", profissao_confianca=C.ALTA), None, medir_precisao=False)
        assert "vocabulario_invalido" in p["profissao"].motivos

    def test_calibrated_baixa_on_estado_civil(self):
        v = _v(_f(estado_civil="casado", estado_civil_confianca=C.BAIXA),
               "certidao_casamento", medir_precisao=False)["estado_civil"]
        assert v.duvidoso and "confianca_parser_baixa" in v.motivos

    def test_nome_baixa_is_not_a_signal(self):
        # OCR names are capped at `baixa` by design — no doubt from that alone.
        v = _v(_f(nome="JOAO CARLOS PEREIRA", nome_confianca=C.BAIXA), medir_precisao=False)["nome"]
        assert v.estado == confianca.CONFIAVEL

    def test_nome_incompleto(self):
        assert "nome_incompleto" in _v(_f(nome="JOAO", nome_confianca=C.BAIXA), medir_precisao=False)["nome"].motivos

    def test_implausible_dates(self):
        v = _v(_f(data_nascimento=date(2990, 1, 1), data_nascimento_confianca=C.ALTA), medir_precisao=False)
        assert "data_implausivel" in v["data_nascimento"].motivos
        c = _v(_f(data_nascimento=date(1990, 1, 1), data_nascimento_confianca=C.ALTA,
                  data_casamento=date(1980, 1, 1), data_casamento_confianca=C.ALTA),
               "certidao_casamento", medir_precisao=False)
        assert "data_implausivel" in c["data_casamento"].motivos

    def test_absent_field_is_ausente(self):
        assert _v(_f(), medir_precisao=False)["cpf"].estado == confianca.AUSENTE

    def test_fields_outside_the_types_authority_are_not_judged(self):
        assert "cpf" not in _v(_f(cpf=CPF_OK), "certidao_nascimento", medir_precisao=False)


class TestDocumentLevelRules:
    def test_compromised_read_makes_every_field_duvidoso(self):
        f = _f(nome="JOAO CARLOS PEREIRA", nome_confianca=C.BAIXA, cpf=CPF_OK, cpf_confianca=C.ALTA,
               aviso="leitura_comprometida")
        v = _v(f, medir_precisao=False)
        assert v["nome"].duvidoso and "leitura_comprometida" in v["nome"].motivos
        assert v["cpf"].duvidoso  # HARD: a verified DV does not launder it

    def test_failed_anchor(self):
        f = _f(nome="JOAO CARLOS PEREIRA", nome_confianca=C.BAIXA, ancora_falhou=True)
        assert _v(f, medir_precisao=False)["nome"].duvidoso

    def test_reduced_resolution_is_soft(self):
        f = _f(nome="JOAO CARLOS PEREIRA", nome_confianca=C.BAIXA, cpf=CPF_OK, cpf_confianca=C.ALTA,
               aviso=confianca.AVISO_RESOLUCAO_REDUZIDA)
        v = _v(f, medir_precisao=False)
        assert v["nome"].duvidoso and confianca.AVISO_RESOLUCAO_REDUZIDA in v["nome"].motivos
        assert v["cpf"].estado == confianca.CONFIAVEL  # its own DV verifies


class TestMeasuredPrecisionAndCorroboration:
    def test_a_sufficient_cell_above_threshold_passes(self):
        v = _v(_f(nome="JOAO CARLOS PEREIRA", nome_confianca=C.BAIXA), "cnh", modelo="claude-sonnet-5")["nome"]
        assert v.estado == confianca.CONFIAVEL and "precisao_medida_baixa" not in v.motivos

    def test_a_thin_cell_is_informational_only(self):
        v = _v(_f(nome="JOAO CARLOS PEREIRA", nome_confianca=C.BAIXA), "rg", modelo="claude-sonnet-5")["nome"]
        assert "precisao_nao_medida" in v.motivos and v.estado == confianca.CONFIAVEL

    def test_corroboration_clears_soft_doubt(self):
        f = _f(nome="JOAO CARLOS PEREIRA", nome_confianca=C.BAIXA, aviso=confianca.AVISO_RESOLUCAO_REDUZIDA)
        v = _v(f, confirmados={"nome": "Joao Carlos Pereira"}, medir_precisao=False)["nome"]
        assert "corroborado_outro_documento" in v.motivos and v.estado == confianca.CONFIAVEL

    def test_contradicting_a_confirmed_value_is_doubt(self):
        v = _v(_f(cpf=CPF_OK, cpf_confianca=C.ALTA), confirmados={"cpf": "303.102.653-55"},
               medir_precisao=False)["cpf"]
        assert v.duvidoso and "diverge_de_valor_confirmado" in v.motivos

    def test_corroboration_never_launders_a_hard_failure(self):
        v = _v(_f(cpf=CPF_DV_RUIM, cpf_confianca=C.ALTA), confirmados={"cpf": CPF_DV_RUIM},
               medir_precisao=False)["cpf"]
        assert v.duvidoso


class TestFallbackTrigger:
    def test_only_doubtful_critical_fields_trigger(self):
        f = _f(nome="JOAO CARLOS PEREIRA", nome_confianca=C.BAIXA, cpf=CPF_DV_RUIM, cpf_confianca=C.ALTA)
        v = _v(f, medir_precisao=False)
        assert confianca.criticos_duvidosos(v, f, "cnh") == ("cpf",)

    def test_a_missing_core_field_alone_does_not_trigger(self):
        f = _f(nome="JOAO CARLOS PEREIRA", nome_confianca=C.BAIXA)
        assert confianca.criticos_duvidosos(_v(f, medir_precisao=False), f, "rg") == ()


class TestFingerprint:
    def test_same_fact_same_fingerprint_and_no_value(self):
        a = confianca.impressao("cpf", "412.954.238-98")
        assert a == confianca.impressao("cpf", "41295423898")
        assert len(a) == 6 and "412" not in a
        assert confianca.impressao("rg", "52.179.965") == confianca.impressao("rg", "52.179.965-X")
        assert confianca.impressao("nome", None) is None

    def test_different_values_differ(self):
        assert confianca.impressao("cpf", CPF_OK) != confianca.impressao("cpf", "303.102.653-55")



class TestCalibrar:
    """`confianca.calibrar` — a vision-capped `baixa` (nome/rg/rne) the gate
    cleared ON EVIDENCE becomes `media`; everything else keeps its flag.
    Shapes from the deal-876 reads that filled the legal review with
    correct-but-`baixa` rows (2026-10-19): an SP RG whose own check digit
    verifies, a CNH name with a measured 1.0 precision."""

    def _calibrado(self, f, tipo, **kw):
        return confianca.calibrar(f, _v(f, tipo, **kw))

    def test_an_sp_rg_whose_check_digit_verifies_is_raised_to_media(self):
        f = _f(rg="19.131.047-5", rg_orgao="SSP/SP", rg_confianca=C.BAIXA,
               rg_orgao_confianca=C.BAIXA)
        out = self._calibrado(f, "rg", medir_precisao=False)
        assert out.rg_confianca is C.MEDIA
        # The DV exists only for SP: it vouches for the SP issuer beside it.
        assert out.rg_orgao_confianca is C.MEDIA

    def test_a_verified_rg_never_vouches_for_a_non_sp_issuer(self):
        f = _f(rg="19.131.047-5", rg_orgao="SSP/RJ", rg_confianca=C.BAIXA,
               rg_orgao_confianca=C.BAIXA)
        out = self._calibrado(f, "rg", medir_precisao=False)
        assert out.rg_orgao_confianca is C.BAIXA

    def test_a_cnh_name_with_measured_precision_is_raised_to_media(self):
        f = _f(nome="FULANO DE TAL SOBRENOME", nome_confianca=C.BAIXA)
        out = self._calibrado(f, "cnh", modelo="claude-sonnet-5")
        assert out.nome_confianca is C.MEDIA

    def test_a_name_corroborated_by_another_document_is_raised(self):
        f = _f(nome="FULANO DE TAL SOBRENOME", nome_confianca=C.BAIXA)
        out = self._calibrado(f, "rg", medir_precisao=False,
                              confirmados={"nome": "Fulano de Tal Sobrenome"})
        assert out.nome_confianca is C.MEDIA

    def test_unmeasured_and_uncorroborated_stays_baixa(self):
        """`confiavel` only because nothing was measured is NOT evidence —
        a real low read must keep its flag."""
        f = _f(nome="FULANO DE TAL SOBRENOME", nome_confianca=C.BAIXA)
        assert self._calibrado(f, "rg", modelo="claude-sonnet-5").nome_confianca is C.BAIXA

    def test_an_rg_with_no_check_digit_and_no_corroboration_stays_baixa(self):
        f = _f(rg="18.568.536", rg_orgao="SSP/SP", rg_confianca=C.BAIXA)
        assert self._calibrado(f, "cnh", modelo="claude-sonnet-5").rg_confianca is C.BAIXA

    def test_a_doubtful_field_is_never_raised(self):
        f = _f(rg="52.179.965-1", rg_orgao="SSP/SP", rg_confianca=C.BAIXA)
        assert self._calibrado(f, "rg", medir_precisao=False).rg_confianca is C.BAIXA

    def test_a_contradicted_name_is_never_raised(self):
        f = _f(nome="FULANO DE TAL SOBRENOME", nome_confianca=C.BAIXA)
        out = self._calibrado(f, "cnh", modelo="claude-sonnet-5",
                              confirmados={"nome": "Beltrano Outro Nome"})
        assert out.nome_confianca is C.BAIXA

    def test_a_calibrated_parsers_baixa_is_the_signal_and_never_raised(self):
        """An unlabelled DV-valid CPF may be a parent's — its `baixa` IS
        the low-confidence signal (`_CONFIANCA_CALIBRADA`)."""
        f = _f(cpf=CPF_OK, cpf_confianca=C.BAIXA)
        assert self._calibrado(f, "cnh", medir_precisao=False).cpf_confianca is C.BAIXA

    def test_never_promotes_to_alta_nor_touches_alta_or_nenhuma(self):
        f = _f(rg="19.131.047-5", rg_orgao="SSP/SP", rg_confianca=C.ALTA)
        assert self._calibrado(f, "rg", medir_precisao=False).rg_confianca is C.ALTA

    def test_excluded_and_changed_fields_are_left_to_the_reconciliation(self):
        f = _f(rg="19.131.047-5", rg_orgao="SSP/SP", rg_confianca=C.BAIXA)
        v = _v(f, "rg", medir_precisao=False)
        assert confianca.calibrar(f, v, excluir=("rg",)).rg_confianca is C.BAIXA
        outro = _f(rg="19.131.048-3", rg_orgao="SSP/SP", rg_confianca=C.BAIXA)
        assert confianca.calibrar(outro, v, original=f).rg_confianca is C.BAIXA
