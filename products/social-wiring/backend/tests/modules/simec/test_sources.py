"""SIMEC metrics sources: the Real one reads OUR Instagram snapshots, picks
the snapshot that represents each configured window, converts units, keeps
gaps as gaps; the Fake shares the same builder; the factory never falls back
silently."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import UUID

import pytest

from noctusai_lib.domain.content_performance import (
    compute_readout,
    load_default_config,
    merge_overrides,
)

from app.modules.instagram.repository import IgInsightsRepository
from app.modules.instagram.sync_service import TZ_BR
from app.modules.simec.sources import (
    FakeInstagramSource,
    InstagramSnapshotSource,
    SimecMetricsSource,
    demo_instagram_rows,
    ig_format,
    make_metrics_source,
)
from tests.modules.instagram.fakes import FakeSupabase

ORG = "00000000-0000-4000-8000-00000000000a"
OTHER_ORG = "00000000-0000-4000-8000-00000000000b"
ACC = "00000000-0000-4000-8000-0000000000a1"
IG = load_default_config("instagram")


def _media(mid, pub: date, mpt="REELS", mt="VIDEO", org=ORG, hour=23):
    # 23:30 BRT = next day in UTC: the BRT calendar day must win.
    return {"id": f"row-{org[-1]}-{mid}", "org_id": org, "account_id": ACC, "ig_media_id": mid, "media_product_type": mpt,
            "media_type": mt, "caption": f"{mid} tema\nresto", "permalink": f"https://ig/{mid}",
            "published_at": datetime.combine(pub, time(hour, 30), tzinfo=TZ_BR).isoformat()}


def _snap(mid, day: date, org=ORG, **metrics):
    base = {"views": 1000, "reach": 800, "likes": 50, "comments": 5, "shares": 10, "saved": 12,
            "follows": None, "ig_reels_avg_watch_time": 12500, "extra_metrics": {"reels_skip_rate": 41.5},
            "unsupported_metrics": ["follows"]}
    base.update(metrics)
    return {"id": f"{mid}-{day}", "org_id": org, "account_id": ACC, "ig_media_id": mid,
            "snapshot_date": day.isoformat(), **base}


@pytest.fixture
def sb():
    s = FakeSupabase()
    pub = date(2026, 9, 1)
    s.tables["ig_media"] = [_media("R1", pub), _media("F1", pub, mpt="FEED", mt="IMAGE"),
                            _media("X", pub, org=OTHER_ORG)]
    snaps = []
    for d in (1, 2, 3, 5, 8, 9, 31, 33):
        snaps.append(_snap("R1", pub + timedelta(days=d), views=1000 + d))
    snaps.append(_snap("F1", pub + timedelta(days=7), follows=4, reach=None,
                       ig_reels_avg_watch_time=None, extra_metrics={}))
    snaps.append(_snap("X", pub + timedelta(days=8), org=OTHER_ORG))
    s.tables["ig_media_snapshots"] = snaps
    return s


def _collect(source, **kw):
    args = dict(org_id=UUID(ORG), account_id=UUID(ACC), published_from=date(2026, 8, 1),
                published_to=date(2026, 9, 30), observed_until=date(2026, 10, 19), config=IG)
    args.update(kw)
    return source.collect(**args)


class TestInstagramSnapshotSource:
    def test_is_a_metrics_source(self, sb):
        assert isinstance(InstagramSnapshotSource(IgInsightsRepository(sb)), SimecMetricsSource)

    def test_windows_pick_the_right_snapshot(self, sb):
        readings = _collect(InstagramSnapshotSource(IgInsightsRepository(sb)))
        r1 = {r.window: r for r in readings if r.content_id == "R1"}
        assert set(r1) == {"72h", "7d", "30d", "atual"}
        assert r1["72h"].collected_at == date(2026, 9, 4)   # earliest inside 3..4
        assert r1["7d"].collected_at == date(2026, 9, 9)    # earliest inside 7..10
        assert r1["30d"].collected_at == date(2026, 10, 2)  # earliest inside 30..35
        assert r1["atual"].collected_at == date(2026, 10, 4)  # latest
        assert r1["7d"].values["views"] == 1008
        assert r1["7d"].source_ref["snapshot_date"] == "2026-09-09"
        assert r1["7d"].published_at == date(2026, 9, 1)  # BRT day, not the UTC day

    def test_units_and_gaps(self, sb):
        readings = _collect(InstagramSnapshotSource(IgInsightsRepository(sb)))
        r = next(x for x in readings if x.content_id == "R1" and x.window == "7d")
        assert r.values["avg_watch_time_s"] == pytest.approx(12.5)
        assert r.values["skip_rate"] == pytest.approx(0.415)
        assert r.values["saves"] == 12
        assert r.values["follows"] is None  # unsupported for Reels: a gap, never 0
        assert r.format == "Reel" and r.topic == "R1 tema"
        f = next(x for x in readings if x.content_id == "F1" and x.window == "7d")
        assert f.format == "Foto" and f.values["reach"] is None and f.values["follows"] == 4

    def test_org_scoped_and_window_without_snapshot_is_absent(self, sb):
        readings = _collect(InstagramSnapshotSource(IgInsightsRepository(sb)))
        assert {r.content_id for r in readings} == {"R1", "F1"}
        assert {r.window for r in readings if r.content_id == "F1"} == {"7d", "atual"}

    def test_observed_until_bounds_snapshots(self, sb):
        readings = _collect(InstagramSnapshotSource(IgInsightsRepository(sb)),
                            observed_until=date(2026, 9, 6))
        assert {r.window for r in readings if r.content_id == "R1"} == {"72h", "atual"}

    def test_window_tolerance_comes_from_config(self, sb):
        narrow = merge_overrides(IG, {"windows": {"7d": {"min_days": 9}}}, "perfil.v1")
        readings = _collect(InstagramSnapshotSource(IgInsightsRepository(sb)), config=narrow)
        r = next(x for x in readings if x.content_id == "R1" and x.window == "7d")
        assert r.collected_at == date(2026, 9, 10)

    def test_no_media_short_circuits(self):
        assert _collect(InstagramSnapshotSource(IgInsightsRepository(FakeSupabase()))) == []


class TestFakeSource:
    def test_demo_catalog_feeds_a_real_readout(self):
        today = date(2026, 10, 19)
        src = FakeInstagramSource(default=demo_instagram_rows)
        readings = _collect(src, published_from=date(2026, 6, 1), published_to=today, observed_until=today)
        assert readings and all(r.source == "Fake (dados de demonstração)" for r in readings)
        ro = compute_readout(readings, IG, period_start=date(2026, 9, 20), period_end=today)
        assert ro.panel["7d"]["conteudos_validos"].value > 0
        assert ro.panel["7d"]["media_tempo_medio_duracao"].status.value == "nao_disponivel"
        assert any(b.sufficient for b in ro.baselines)

    def test_explicit_catalog_wins_and_unknown_account_is_empty(self):
        pub = date(2026, 9, 1)
        src = FakeInstagramSource({ACC: ([_media("R1", pub)], [_snap("R1", pub + timedelta(days=8))])})
        assert [r.window for r in _collect(src)] == ["7d", "atual"]
        assert _collect(src, account_id=UUID(int=9)) == []


def test_ig_format_vocabulary():
    assert ig_format("REELS", "VIDEO") == "Reel"
    assert ig_format(None, "VIDEO") == "Reel"
    assert ig_format("FEED", "CAROUSEL_ALBUM") == "Carrossel"
    assert ig_format("FEED", "IMAGE") == "Foto"
    assert ig_format("STORY", "IMAGE") == "Story"


class TestFactory:
    def test_kinds(self, sb):
        assert make_metrics_source("instagram", "instagram", ig_repo=IgInsightsRepository(sb)).name == "instagram_snapshots"
        assert make_metrics_source("instagram", "fake").name == "fake"

    @pytest.mark.parametrize("platform,kind", [("instagram", "metricool"), ("tiktok", "fake")])
    def test_unknown_fails_loud(self, platform, kind):
        with pytest.raises(ValueError):
            make_metrics_source(platform, kind)

    def test_real_without_repo_fails_loud(self):
        with pytest.raises(ValueError):
            make_metrics_source("instagram", "instagram")
