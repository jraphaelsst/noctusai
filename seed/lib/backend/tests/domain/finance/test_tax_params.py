"""BR tax-parameter registry: load invariants, effective-dated lookup, staleness."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from noctusai_lib.domain.finance.params import (
    ParamAmbiguous, ParamNotDefined, ParamRegistryError, load_registry, param, params_for, stale_params, staleness_warning,
)

TODAY = date(2026, 11, 7)
POLICY = {"max_age_dias": {"norma": 365, "orgao_oficial": 180, "publicacao_tecnica": 90, "especialista": 90},
          "horizonte_vigencia_dias": 45}


def row(**o):
    r = {"key": "x.a", "value": "0.1", "unit": "ratio", "scope": {"regime": ["simples"]}, "vigencia_de": date(2020, 1, 1),
         "vigencia_ate": None, "norma": "N", "fonte_url": ["https://a"], "tier": "norma", "verificado_em": date(2026, 1, 1),
         "verificado_por": "t", "revalidar_em": None}
    r.update(o)
    return r


def mk(tmp_path: Path, rows, fam="simples"):
    (tmp_path / "_policy.yaml").write_text(yaml.safe_dump(POLICY))
    (tmp_path / f"{fam}.yaml").write_text(yaml.safe_dump({"rows": rows}))
    return load_registry(tmp_path, today=TODAY)


def test_whole_shipped_registry_loads_and_counts():
    reg = load_registry(today=TODAY)
    assert len(reg.rows) == 297


def test_shipped_yaml_values():
    reg = load_registry(today=TODAY)
    p = lambda k, on=TODAY, **sc: param(k, on=on, scope=sc or None, registry=reg)  # noqa: E731
    assert p("simples.fator_r.limiar").value == Decimal("0.28")
    assert p("simples.anexo_iii.faixa_1.aliquota_nominal", anexo="III").value == Decimal("0.06")
    assert p("simples.anexo_v.faixa_6.aliquota_nominal", on=date(2027, 6, 1), anexo="V").value == Decimal("0.304")
    assert p("simples.anexo_v.faixa_6.aliquota_nominal", on=date(2026, 6, 1), anexo="V").value == Decimal("0.305")
    assert p("obrigacoes.das.vencimento_dia").value == 20
    assert p("nfse.padrao_nacional.obrigatorio_me_epp_simples.inicio").unit == "date"
    cbs = p("mei.das.cbs.valor_mensal", on=date(2027, 3, 1))
    assert cbs.unit == "brl" and cbs.value == Decimal("0.994")
    assert p("mei.relatorio_mensal_receitas.obrigacao").value == "manter_e_apresentar_quando_solicitado"
    with pytest.raises(ParamNotDefined):  # unsourced "dia 20" must not exist
        p("mei.relatorio_mensal.dia_limite")
    with pytest.raises(ParamNotDefined):  # DAS-MEI due date still open: mei is NOT in the simples row's scope
        p("obrigacoes.das.vencimento_dia", regime="mei")


def test_scope_extensions_and_regime_vocabulary(tmp_path):
    reg = mk(tmp_path, [row(scope={"regime": ["presumido", "real"], "anexo": ["III", "V"], "porte": ["me"], "cnae": "6201-5/01"})])
    sc = reg.rows[0].scope
    assert sc.regime == ["lucro_presumido", "lucro_real"]
    assert param("x.a", on=TODAY, scope={"regime": "lucro_real", "anexo": "V", "porte": "me"}, registry=reg)
    with pytest.raises(ParamNotDefined):
        param("x.a", on=TODAY, scope={"anexo": "I"}, registry=reg)
    with pytest.raises(ParamRegistryError):
        mk(tmp_path, [row(scope={"regime": ["bogus"]})])
    assert mk(tmp_path, [row(scope={})]).rows[0].scope.regime == ["*"]


def test_distinct_scope_dims_do_not_overlap_but_same_do(tmp_path):
    mk(tmp_path, [row(scope={"regime": ["simples"], "anexo": "III"}), row(scope={"regime": ["simples"], "anexo": "V"}, value="0.2")])
    with pytest.raises(ParamRegistryError, match="overlapping"):
        mk(tmp_path, [row(scope={"regime": ["simples"], "anexo": ["III", "V"]}), row(scope={"regime": ["simples"], "anexo": "V"})])


def test_value_coercion_per_unit(tmp_path):
    reg = mk(tmp_path, [row(key="k.int", unit="brl_centavos", value="480000000"), row(key="k.dia", unit="dia_do_mes", value="20"),
                        row(key="k.brl", unit="brl", value="0.994"), row(key="k.pct", unit="pct", value="6.5")])
    g = lambda k: param(k, on=TODAY, registry=reg).value  # noqa: E731
    assert g("k.int") == 480000000 and isinstance(g("k.int"), int)
    assert g("k.dia") == 20 and isinstance(g("k.dia"), int)
    assert g("k.brl") == Decimal("0.994") and g("k.pct") == Decimal("6.5")
    for bad in ({"unit": "brl_centavos", "value": "1.5"}, {"unit": "ratio", "value": "abc"}, {"unit": "dia_do_mes", "value": "x"}):
        with pytest.raises(ParamRegistryError):
            mk(tmp_path, [row(**bad)])


def test_overlap_refused(tmp_path):
    with pytest.raises(ParamRegistryError, match="x.a.*overlapping"):
        mk(tmp_path, [row(vigencia_ate=date(2022, 1, 1)), row(vigencia_de=date(2022, 1, 1))])


def test_float_refused(tmp_path):
    with pytest.raises(ParamRegistryError, match="float"):
        mk(tmp_path, [row(value=0.28)])


def test_especialista_needs_two_urls(tmp_path):
    with pytest.raises(ParamRegistryError, match="especialista"):
        mk(tmp_path, [row(tier="especialista")])
    mk(tmp_path, [row(tier="especialista", fonte_url=["https://a", "https://b"])])


def test_future_verificado_refused(tmp_path):
    with pytest.raises(ParamRegistryError, match="future"):
        mk(tmp_path, [row(verificado_em=date(2026, 11, 8))])


def test_unknown_field_refused(tmp_path):
    with pytest.raises(ParamRegistryError):
        mk(tmp_path, [row(extra="x")])


def test_boundaries_inclusive_and_before_first_row(tmp_path):
    reg = mk(tmp_path, [row(vigencia_de=date(2024, 1, 1), vigencia_ate=date(2024, 12, 31))])
    assert param("x.a", on=date(2024, 1, 1), registry=reg)
    assert param("x.a", on=date(2024, 12, 31), registry=reg)
    with pytest.raises(ParamNotDefined):
        param("x.a", on=date(2023, 12, 31), registry=reg)
    with pytest.raises(ParamNotDefined):
        param("x.a", on=date(2025, 1, 1), registry=reg)


def test_pratica_never_returned(tmp_path):
    reg = mk(tmp_path, [row(tier="pratica")])
    with pytest.raises(ParamNotDefined):
        param("x.a", on=TODAY, registry=reg)
    assert params_for("x.", on=TODAY, registry=reg) == {}


def test_ambiguous_without_scope(tmp_path):
    reg = mk(tmp_path, [row(scope={"regime": ["simples"]}), row(scope={"regime": ["mei"]}, value="0.2")])
    with pytest.raises(ParamAmbiguous):
        param("x.a", on=TODAY, registry=reg)
    assert param("x.a", on=TODAY, scope={"regime": "mei"}, registry=reg).value == Decimal("0.2")


def test_stale_verificacao_and_revalidar_override(tmp_path):
    reg = mk(tmp_path, [row(verificado_em=date(2025, 10, 1))])  # norma 365d -> due 2026-10-01
    s = stale_params(TODAY, registry=reg)
    assert [(r.reason, r.dias) for r in s] == [("verificacao_vencida", 37)]
    reg = mk(tmp_path, [row(verificado_em=date(2025, 10, 1), revalidar_em=date(2027, 1, 1))])
    assert stale_params(TODAY, registry=reg) == []
    reg = mk(tmp_path, [row(verificado_em=date(2026, 10, 1), revalidar_em=date(2026, 11, 1))])
    assert stale_params(TODAY, registry=reg)[0].reason == "verificacao_vencida"


def test_stale_horizon_and_successor(tmp_path):
    reg = mk(tmp_path, [row(vigencia_ate=date(2026, 12, 1))])
    s = stale_params(TODAY, registry=reg)
    assert [(r.reason, r.dias) for r in s] == [("vigencia_terminando", 24)]
    reg = mk(tmp_path, [row(vigencia_ate=date(2026, 12, 1)), row(vigencia_de=date(2026, 12, 2))])
    assert stale_params(TODAY, registry=reg) == []
    reg = mk(tmp_path, [row(vigencia_ate=date(2026, 10, 1))])
    assert stale_params(TODAY, registry=reg)[0].reason == "vigencia_encerrada_sem_sucessor"
    reg = mk(tmp_path, [row(vigencia_ate=date(2027, 6, 1))])
    assert stale_params(TODAY, registry=reg) == []


def test_staleness_warning(tmp_path):
    reg = mk(tmp_path, [row(verificado_em=date(2025, 10, 1))])
    w = staleness_warning(param("x.a", on=TODAY, registry=reg), TODAY, registry=reg)
    assert w and w["code"] == "parametro_desatualizado" and w["details"]["dias"] == 402
    reg = mk(tmp_path, [row()])
    assert staleness_warning(param("x.a", on=TODAY, registry=reg), TODAY, registry=reg) is None


# --- real registry: S12 corrections (2026-11-07) ---------------------------------------------------------------------
def _real(key, on, scope=None):
    return param(key, on=on, scope=scope, registry=load_registry())


def test_anexo_i_faixa_6_2029_follows_lc214_not_cgsn_print():
    k = "simples.anexo_i.faixa_6.aliquota_nominal"
    assert _real(k, date(2028, 6, 1), {"regime": "simples", "anexo": "I"}).value == Decimal("0.189")
    assert _real(k, date(2029, 6, 1), {"regime": "simples", "anexo": "I"}).value == Decimal("0.19")


def test_das_vencimento_mei_row_resolves():
    assert _real("obrigacoes.das.vencimento_dia", date(2026, 11, 7), {"regime": "mei"}).value == 20


@pytest.mark.parametrize("key", [
    "simples.opcao.janela_anual",
    "simples.ibs_cbs.regime_regular.janela_semestre_jan",
    "simples.ibs_cbs.regime_regular.cancelamento_ate_semestre_jan",
])
def test_window_keys_unambiguous_2026_and_2027(key):
    for on in (date(2026, 10, 1), date(2027, 3, 1)):
        assert _real(key, on, {"regime": "simples"}).value


def test_window_2026_values_follow_res_186_194():
    sc = {"regime": "simples"}
    assert _real("simples.opcao.janela_anual", date(2026, 10, 1), sc).value == "09-01..10-15"
    assert _real("simples.opcao.janela_anual", date(2026, 9, 1), sc).value == "09-01..09-30"
    assert _real("simples.ibs_cbs.regime_regular.cancelamento_ate_semestre_jan", date(2026, 10, 1), sc).value == "12-20"
    assert _real("simples.ibs_cbs.regime_regular.cancelamento_ate_semestre_jan", date(2027, 3, 1), sc).value == "11-30"


def test_fs12_window_shifts_at_2027():
    sc = {"regime": "simples"}
    assert _real("simples.fs12.janela", date(2026, 12, 31), sc).value == "12_meses_anteriores_ao_PA"
    assert _real("simples.fs12.janela", date(2027, 1, 1), sc).value == "12_meses_antecedentes_ao_mes_anterior_ao_PA"
