"""BR tax-parameter registry: load invariants, effective-dated lookup, staleness."""
from __future__ import annotations

from datetime import date
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


def test_shipped_yaml_loads_and_values():
    reg = load_registry(today=TODAY)
    assert param("simples.fator_r.limiar", on=TODAY, registry=reg).value == "0.28"
    assert param("obrigacoes.das.dia_vencimento", on=TODAY, scope={"regime": "mei"}, registry=reg).value == 20
    assert param("obrigacoes.das.dia_vencimento", on=TODAY, scope={"regime": "simples"}, registry=reg).value == 20
    assert param("nfse.nacional.obrigatoria_me_epp_desde", on=TODAY, registry=reg).unit == "date"
    assert param("mei.relatorio_mensal.dia_limite", on=TODAY, registry=reg).value == 20


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
    assert param("x.a", on=TODAY, scope={"regime": "mei"}, registry=reg).value == "0.2"


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
