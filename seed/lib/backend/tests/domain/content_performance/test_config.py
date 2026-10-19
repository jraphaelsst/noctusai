"""PerformanceConfig: defaults are data, overrides layer per key, every
inconsistency is a ConfigError, and the fingerprint identifies the config."""
from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.content_performance import (
    ConfigError,
    config_from_dict,
    default_config_dict,
    load_default_config,
    merge_overrides,
)


@pytest.mark.parametrize("platform", ["instagram", "tiktok"])
def test_defaults_load_and_validate(platform):
    cfg = load_default_config(platform)
    assert cfg.platform == platform
    assert {w.key for w in cfg.active_windows} == {"72h", "7d", "30d", "atual"}
    assert cfg.window("7d").min_days == 7 and cfg.window("7d").max_days == 10
    assert cfg.window("30d").min_days == 30 and cfg.window("30d").max_days == 35
    assert cfg.window("atual").min_days is None and cfg.window("atual").max_days is None
    assert cfg.baseline.lookback_days == 90
    assert cfg.cadence.decision_validation_days == 28


def test_platform_denominators_are_data():
    ig = load_default_config("instagram")
    tt = load_default_config("tiktok")
    ig_rate = next(i for i in ig.indicators if i.key == "taxa_interacao")
    tt_rate = next(i for i in tt.indicators if i.key == "taxa_interacao")
    assert ig_rate.inputs[1] == "reach"
    assert tt_rate.inputs[1] == "views"


def test_unknown_platform_is_config_error():
    with pytest.raises(ConfigError, match="no default"):
        load_default_config("orkut")


def test_fingerprint_is_stable_and_changes_with_any_value():
    a = load_default_config("instagram")
    b = load_default_config("instagram")
    assert a.fingerprint == b.fingerprint and len(a.fingerprint) == 64
    c = merge_overrides(a, {"windows": {"7d": {"max_days": 11}}}, "org.v1")
    assert c.fingerprint != a.fingerprint


class TestOverrides:
    def test_per_key_merge_keeps_siblings(self):
        base = load_default_config("instagram")
        cfg = merge_overrides(base, {"windows": {"7d": {"max_days": 12}}}, "org.v3")
        assert cfg.window("7d").max_days == 12
        assert cfg.window("7d").min_days == 7
        assert cfg.window("30d").max_days == 35
        assert cfg.version == "instagram-defaults-1.0.0+org.v3"

    def test_layers_stack_in_the_version_label(self):
        base = load_default_config("instagram")
        org = merge_overrides(base, {"baseline": {"min_posts": 8}}, "org.v2")
        prof = merge_overrides(org, {"baseline": {"lookback_days": 60}}, "perfil.v1")
        assert prof.baseline.min_posts == 8 and prof.baseline.lookback_days == 60
        assert prof.version == "instagram-defaults-1.0.0+org.v2+perfil.v1"

    def test_add_and_disable_items(self):
        base = load_default_config("instagram")
        cfg = merge_overrides(base, {
            "windows": {"72h": {"enabled": False}, "14d": {"label": "14 dias", "min_days": 14, "max_days": 16}},
            "indicators": {"taxa_seguidores": {"enabled": False}},
            "panel": {"media_taxa_seguidores": {"enabled": False},
                      "amostra_taxa_seguidores": {"enabled": False}},
            "baseline": {"indicators": ["taxa_interacao"]},
            "alerts": {"compartilhamento_fora_do_padrao": {"enabled": False},
                       "salvamento_fora_do_padrao": {"enabled": False},
                       "alcance_fora_do_padrao": {"enabled": False}},
        }, "perfil.v1")
        assert cfg.window("72h") is None
        assert cfg.window("14d").max_days == 16
        assert "taxa_seguidores" not in {i.key for i in cfg.active_indicators}

    def test_metric_availability_is_overridable(self):
        base = load_default_config("instagram")
        assert "duration_s" in base.unavailable_keys()
        assert "tempo_medio_duracao" in base.unavailable_keys()
        cfg = merge_overrides(base, {"metrics": {"duration_s": {"available": True}}}, "x")
        assert "tempo_medio_duracao" not in cfg.unavailable_keys()

    def test_empty_override_returns_base(self):
        base = load_default_config("instagram")
        assert merge_overrides(base, {}, "org.v1") is base
        assert merge_overrides(base, None, "org.v1") is base

    @pytest.mark.parametrize("bad,match", [
        ({"platform": "tiktok"}, "cannot be overridden"),
        ({"version": "x"}, "cannot be overridden"),
        ({"windows": {"7d": {"min_days": 11}}}, "min_days 11 > max_days 10"),
        ({"windows": {"7d": {"tolerance": 2}}}, "unknown field"),
        ({"indicators": {"x": {"label": "X", "op": "median", "inputs": ["views"]}}}, "op"),
        ({"indicators": {"x": {"label": "X", "op": "ratio", "inputs": ["views"]}}}, "exactly 2"),
        ({"indicators": {"x": {"label": "X", "op": "ratio", "inputs": ["views", "nope"]}}}, "nope"),
        ({"panel": {"p": {"label": "P", "aggregate": "mean", "source": "nope"}}}, "nope"),
        ({"baseline": {"min_posts": 0}}, "min_posts"),
        ({"alerts": {"a": {"indicator": "likes", "method": "pct_from_median", "threshold": 0.2}}}, "no baseline"),
        ({"alerts": {"a": {"indicator": "reach", "method": "zscore", "threshold": 2}}}, "method"),
        ({"alerts": {"a": {"indicator": "reach", "method": "outside_iqr", "threshold": 0}}}, "threshold"),
        ({"metrics": {"views": {"available": False}}}, "required_metrics"),
        ({"windows": {k: {"enabled": False} for k in ("72h", "7d", "30d", "atual")}}, "at least one"),
        ({"cadence": {"decision_validation_days": 0}}, "decision_validation_days"),
        ({"mystery": 1}, "unknown field"),
    ])
    def test_invalid_overrides_raise(self, bad, match):
        with pytest.raises(ConfigError, match=match):
            merge_overrides(load_default_config("instagram"), bad, "bad")


def test_disabled_indicator_still_referenced_is_rejected():
    raw = default_config_dict("instagram")
    raw["indicators"]["total_interacoes"]["enabled"] = False
    with pytest.raises(ConfigError, match="total_interacoes"):
        config_from_dict(raw)


def test_cadence_ops():
    cfg = load_default_config("instagram")
    assert cfg.review_period("semanal", date(2026, 10, 19)) == (date(2026, 10, 13), date(2026, 10, 19))
    assert cfg.review_period("mensal", date(2026, 10, 30)) == (date(2026, 10, 1), date(2026, 10, 30))
    assert cfg.decision_review_date(date(2026, 10, 1)) == date(2026, 10, 29)
    with pytest.raises(ConfigError):
        cfg.review_period("diario", date(2026, 10, 19))


def test_to_dict_round_trips():
    cfg = load_default_config("tiktok")
    again = config_from_dict(cfg.to_dict())
    assert again.fingerprint == cfg.fingerprint
