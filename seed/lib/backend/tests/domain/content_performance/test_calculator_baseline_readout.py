"""Calculator edge semantics beyond the workbook (datetimes, window picking,
unknown windows), baselines from the profile's own history, baseline-relative
alerts, and the readout's period/history split + config stamp."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.content_performance import (
    Reading,
    ReadingStatus,
    age_in_days,
    compute_baselines,
    compute_readout,
    evaluate_alerts,
    evaluate_readings,
    load_default_config,
    merge_overrides,
    percentile_inc,
    select_window_observation,
)

IG = load_default_config("instagram")
UTC = timezone.utc


def _r(cid, pub, coll, window="7d", fmt="Reel", **values):
    base = {"views": 1000, "reach": 800, "likes": 40, "comments": 4, "shares": 8, "saves": 8}
    base.update(values)
    return Reading(content_id=cid, published_at=pub, collected_at=coll, window=window,
                   format=fmt, values=base)


class TestAgeAndWindows:
    def test_datetime_ages_are_fractional(self):
        p = datetime(2026, 10, 1, 12, tzinfo=UTC)
        assert age_in_days(p, p + timedelta(hours=84)) == 3.5

    def test_mixed_naive_and_aware_is_an_error(self):
        with pytest.raises(ValueError):
            age_in_days(datetime(2026, 10, 1), datetime(2026, 10, 2, tzinfo=UTC))

    def test_date_and_datetime_compare_as_dates(self):
        assert age_in_days(date(2026, 10, 1), datetime(2026, 10, 8, 23, tzinfo=UTC)) == 7

    def test_72h_window_tolerance_is_config(self):
        p = datetime(2026, 10, 1, 9, tzinfo=UTC)
        res = evaluate_readings([_r("A", p, p + timedelta(hours=100), window="72h")], IG)
        assert res[0].status is ReadingStatus.FORA_DA_JANELA
        wider = merge_overrides(IG, {"windows": {"72h": {"max_days": 4.5}}}, "perfil.v1")
        res = evaluate_readings([_r("A", p, p + timedelta(hours=100), window="72h")], wider)
        assert res[0].status is ReadingStatus.OK

    def test_unknown_or_disabled_window_is_reported(self):
        off = merge_overrides(IG, {"windows": {"72h": {"enabled": False}}}, "x")
        res = evaluate_readings([_r("A", date(2026, 10, 1), date(2026, 10, 4), window="72h")], off)
        assert res[0].status is ReadingStatus.JANELA_DESCONHECIDA

    def test_select_window_observation(self):
        pub = date(2026, 9, 1)
        obs = [(pub + timedelta(days=d), f"day{d}") for d in (1, 2, 6, 8, 9, 31, 40)]
        assert select_window_observation(pub, obs, "7d", IG) == (date(2026, 9, 9), "day8")
        assert select_window_observation(pub, obs, "30d", IG) == (date(2026, 10, 2), "day31")
        assert select_window_observation(pub, obs, "atual", IG) == (date(2026, 10, 11), "day40")
        assert select_window_observation(pub, obs, "72h", IG) is None
        with pytest.raises(ValueError):
            select_window_observation(pub, obs, "1y", IG)

    def test_non_numeric_metric_fails_loud(self):
        with pytest.raises(TypeError):
            evaluate_readings([_r("A", date(2026, 10, 1), date(2026, 10, 9), views="1000")], IG)


class TestBaselines:
    def test_percentile_inc_matches_excel(self):
        vals = [1.0, 2.0, 3.0, 4.0]
        assert percentile_inc(vals, 0.25) == 1.75
        assert percentile_inc(vals, 0.5) == 2.5
        assert percentile_inc(vals, 0.75) == 3.25
        assert percentile_inc([5.0], 0.5) == 5.0

    def _history(self, n, fmt="Reel", start=date(2026, 7, 1)):
        out = []
        for i in range(n):
            p = start + timedelta(days=i)
            out.append(_r(f"H{fmt}{i}", p, p + timedelta(days=8), fmt=fmt,
                          reach=1000, likes=40 + i, comments=5, shares=5, saves=10))
        return out

    def test_grouped_by_format_and_window_with_min_sample(self):
        res = evaluate_readings(self._history(5) + self._history(2, fmt="Foto"), IG)
        stats = {(b.window, dict(b.group)["format"], b.indicator): b for b in compute_baselines(res, IG)}
        reel = stats[("7d", "Reel", "taxa_interacao")]
        assert reel.n == 5 and reel.sufficient
        assert reel.median == pytest.approx((42 + 20) / 1000)
        foto = stats[("7d", "Foto", "taxa_interacao")]
        assert foto.n == 2 and not foto.sufficient

    def test_unavailable_indicator_has_no_baseline(self):
        cfg = merge_overrides(IG, {"baseline": {"indicators": ["tempo_medio_duracao", *IG.baseline.indicators]}}, "x")
        stats = compute_baselines(evaluate_readings(self._history(5), cfg), cfg)
        assert "tempo_medio_duracao" not in {b.indicator for b in stats}
        assert "taxa_interacao" in {b.indicator for b in stats}

    def test_alert_fires_relative_to_own_median_and_is_reported_insufficient_otherwise(self):
        hist = evaluate_readings(self._history(6) + self._history(2, fmt="Foto"), IG)
        baselines = compute_baselines(hist, IG)
        now = date(2026, 10, 1)
        period = evaluate_readings([
            _r("HIGH", now, now + timedelta(days=8), reach=1000, likes=150, comments=5, shares=5, saves=10),
            _r("NORMAL", now, now + timedelta(days=8), reach=1000, likes=42, comments=5, shares=5, saves=10),
            _r("FOTO", now, now + timedelta(days=8), fmt="Foto", reach=1000, likes=1, comments=0, shares=0, saves=0),
        ], IG)
        ev = evaluate_alerts(period, baselines, IG)
        fired = {(a.content_id, a.rule) for a in ev.fired}
        assert ("HIGH", "interacao_fora_do_padrao") in fired
        assert not any(cid == "NORMAL" for cid, _ in fired)
        assert not any(cid == "FOTO" for cid, _ in fired)
        reasons = {(n.rule, dict(n.group)["format"], n.reason) for n in ev.not_evaluated}
        assert ("interacao_fora_do_padrao", "Foto", "baseline_insuficiente") in reasons
        high = next(a for a in ev.fired if a.content_id == "HIGH" and a.rule == "interacao_fora_do_padrao")
        assert high.direction == "above" and high.deviation > 0.5

    def test_threshold_is_config(self):
        hist = evaluate_readings(self._history(6), IG)
        now = date(2026, 10, 1)
        period = evaluate_readings(
            [_r("X", now, now + timedelta(days=8), reach=1000, likes=60, comments=5, shares=5, saves=10)], IG)
        strict = merge_overrides(IG, {"alerts": {"interacao_fora_do_padrao": {"threshold": 0.2}}}, "x")
        assert not [a for a in evaluate_alerts(period, compute_baselines(hist, IG), IG).fired
                    if a.rule == "interacao_fora_do_padrao"]
        assert [a for a in evaluate_alerts(period, compute_baselines(hist, strict), strict).fired
                if a.rule == "interacao_fora_do_padrao"]


class TestReadout:
    def test_split_panel_baselines_and_config_stamp(self):
        cfg = merge_overrides(IG, {"baseline": {"min_posts": 3}}, "org.v1")
        old = [_r(f"O{i}", date(2026, 8, 1) + timedelta(days=i), date(2026, 8, 9) + timedelta(days=i))
               for i in range(4)]
        too_old = [_r("ANCIENT", date(2026, 1, 1), date(2026, 1, 9))]
        new = [_r("N1", date(2026, 10, 1), date(2026, 10, 9)),
               _r("N2", date(2026, 10, 2), date(2026, 10, 30))]  # 28 days: out of 7d
        ro = compute_readout(old + too_old + new, cfg,
                             period_start=date(2026, 10, 1), period_end=date(2026, 10, 7))
        assert ro.config_version == "instagram-defaults-1.0.0+org.v1"
        assert ro.config_fingerprint == cfg.fingerprint
        assert ro.history_start == date(2026, 7, 3)
        assert [r.reading.content_id for r in ro.readings] == ["N1", "N2"]
        assert ro.status_counts["ok"] == 1 and ro.status_counts["fora_da_janela"] == 1
        assert ro.panel["7d"]["conteudos_validos"].value == 1
        b = next(b for b in ro.baselines if b.indicator == "taxa_interacao")
        assert b.n == 4 and b.sufficient
        d = ro.to_dict()
        assert d["panel"]["7d"]["media_views_3s"]["status"] == "nao_disponivel"
        assert d["readings"][0]["indicators"]["tempo_medio_duracao"]["status"] == "nao_disponivel"

    def test_empty_input_is_an_honest_empty_readout(self):
        ro = compute_readout([], IG, period_start=date(2026, 10, 1), period_end=date(2026, 10, 7))
        assert ro.readings == ()
        assert ro.panel["7d"]["conteudos_validos"].value == 0
        assert ro.panel["7d"]["media_visualizacoes"].status.value == "sem_dados"
        assert ro.alerts.fired == ()

    def test_inverted_period_rejected(self):
        with pytest.raises(ValueError):
            compute_readout([], IG, period_start=date(2026, 10, 7), period_end=date(2026, 10, 1))
