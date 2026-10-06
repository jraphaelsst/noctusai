"""IgSyncService — daily catalog + snapshot capture for one Instagram-Login
account, against the seed ``FakeInstagramLoginAdapter`` (DI seam) and an
in-memory PostgREST double (``fakes.FakeSupabase``)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

from noctusai_lib.integrations.meta import (
    FakeInstagramLoginAdapter,
    IgMediaItem,
    IgProfile,
    MetaGraphError,
)

from app.modules.instagram.repository import IgInsightsRepository
from app.modules.instagram.sync_service import (
    IgSyncError,
    IgSyncService,
    INSIGHTS_WINDOW_DAYS,
    granted_scopes,
    missing_insights_scope,
    previous_day_window,
)
from tests.modules.instagram.fakes import FakeSupabase

ORG = UUID("00000000-0000-4000-8000-000000000001")
ACC = UUID("00000000-0000-4000-8000-0000000000a1")
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
DAY = date(2026, 10, 6)


def _media(i: int, *, mpt="FEED", mt="IMAGE", ts=None) -> IgMediaItem:
    return IgMediaItem(
        id=f"M{i}",
        media_type=mt,
        media_product_type=mpt,
        caption=f"post {i}",
        permalink=f"https://instagram.com/p/{i}",
        timestamp=ts if ts is not None else NOW - timedelta(days=i),
        like_count=i,
        comments_count=1,
    )


def _adapter(**seed) -> FakeInstagramLoginAdapter:
    base = dict(
        profile=IgProfile(id="APP", user_id="IGU", username="acme", followers_count=1200,
                          follows_count=10, media_count=3),
        media=[_media(1, mpt="REELS", mt="VIDEO"), _media(2), _media(3, mpt="FEED", mt="CAROUSEL_ALBUM")],
        media_insights={
            "M1": {"views": 500, "reach": 300, "ig_reels_avg_watch_time": 4200, "reels_skip_rate": 12.5},
            "M2": {"views": 50, "reach": 40, "likes": 2},
            "M3": {"views": 70},
        },
        user_insights={"reach": 900, "views": 2000, "accounts_engaged": 80},
    )
    base.update(seed)
    return FakeInstagramLoginAdapter().seed(**base)


def _svc(adapter, sb=None):
    sb = sb or FakeSupabase()
    repo = IgInsightsRepository(sb)
    svc = IgSyncService(repo=repo, adapter_builder=lambda a, o: adapter, now=lambda: NOW)
    return svc, sb


class TestHappyPath:
    def test_catalog_snapshots_profile_written(self):
        adapter = _adapter()
        svc, sb = _svc(adapter)
        out = svc.run_for_account(org_id=ORG, account_id=ACC)
        assert out.status == "done" and out.snapshot_date == DAY
        assert out.media_synced == 3 and out.snapshots_written == 3
        assert out.profile_snapshot_written

        catalog = {r["ig_media_id"]: r for r in sb.tables["ig_media"]}
        assert set(catalog) == {"M1", "M2", "M3"}
        assert catalog["M1"]["latest_metrics"]["views"] == 500
        assert catalog["M1"]["latest_snapshot_date"] == "2026-10-06"
        assert catalog["M1"]["org_id"] == str(ORG)

        snaps = {r["ig_media_id"]: r for r in sb.tables["ig_media_snapshots"]}
        reel = snaps["M1"]
        assert reel["views"] == 500 and reel["ig_reels_avg_watch_time"] == 4200
        assert reel["extra_metrics"]["reels_skip_rate"] == 12.5  # non-typed → jsonb
        # A metric Meta did not serve is NULL + named — never 0.
        assert reel["likes"] is None and "likes" in reel["unsupported_metrics"]

        prof = sb.tables["ig_profile_snapshots"][0]
        assert prof["followers_count"] == 1200 and prof["reach"] == 900
        assert prof["saves"] is None and "saves" in prof["unsupported_metrics"]
        assert prof["snapshot_date"] == "2026-10-06"

    def test_metric_set_follows_media_product_type(self):
        adapter = _adapter()
        svc, _ = _svc(adapter)
        svc.run_for_account(org_id=ORG, account_id=ACC)
        asked = {c[1]["media_id"]: c[1]["metrics"] for c in adapter.calls if c[0] == "get_media_insights"}
        assert "ig_reels_avg_watch_time" in asked["M1"]
        assert "ig_reels_avg_watch_time" not in asked["M2"]
        assert "profile_visits" in asked["M3"]  # carousel parent = FEED set

    def test_user_insights_window_is_previous_brt_day(self):
        adapter = _adapter()
        svc, sb = _svc(adapter)
        svc.run_for_account(org_id=ORG, account_id=ACC)
        call = next(c[1] for c in adapter.calls if c[0] == "get_user_insights")
        since, until = previous_day_window(DAY)
        assert call["since"] == int(since.timestamp()) and call["until"] == int(until.timestamp())
        assert until - since == timedelta(days=1)
        assert call["ig_user_id"] == "IGU" and call["metric_type"] == "total_value"

    def test_paginates_all_media(self):
        adapter = _adapter(media=[_media(i) for i in range(1, 121)], media_insights={})
        svc, sb = _svc(adapter)
        out = svc.run_for_account(org_id=ORG, account_id=ACC)
        assert out.media_synced == 120
        assert len([c for c in adapter.calls if c[0] == "list_media"]) == 3  # 50+50+20

    def test_account_channel_info_updated(self):
        adapter = _adapter()
        sb = FakeSupabase()
        sb.tables["integration_accounts"] = [{"id": str(ACC), "org_id": str(ORG), "provider": "instagram"}]
        svc, _ = _svc(adapter, sb)
        svc.run_for_account(org_id=ORG, account_id=ACC)
        row = sb.tables["integration_accounts"][0]
        assert row["channel_info"]["followers_count"] == 1200
        assert row["channel_info"]["username"] == "acme"
        assert row["last_synced_at"].startswith("2026-10-06T12:00")


class TestIdempotency:
    def test_second_run_same_day_is_skipped(self):
        adapter = _adapter()
        svc, sb = _svc(adapter)
        svc.run_for_account(org_id=ORG, account_id=ACC)
        out2 = svc.run_for_account(org_id=ORG, account_id=ACC)
        assert out2.status == "skipped"
        assert len(sb.tables["ig_media_snapshots"]) == 3

    def test_force_rerun_updates_rows_never_duplicates(self):
        adapter = _adapter()
        svc, sb = _svc(adapter)
        svc.run_for_account(org_id=ORG, account_id=ACC)
        adapter.seed(media_insights={"M1": {"views": 999}})
        out = svc.run_for_account(org_id=ORG, account_id=ACC, force=True)
        assert out.status == "done"
        assert len(sb.tables["ig_media_snapshots"]) == 3
        assert len(sb.tables["ig_media"]) == 3
        assert len(sb.tables["ig_profile_snapshots"]) == 1
        m1 = next(r for r in sb.tables["ig_media_snapshots"] if r["ig_media_id"] == "M1")
        assert m1["views"] == 999

    def test_next_day_adds_a_row(self):
        adapter = _adapter()
        svc, sb = _svc(adapter)
        svc.run_for_account(org_id=ORG, account_id=ACC)
        svc.run_for_account(org_id=ORG, account_id=ACC, snapshot_date=DAY + timedelta(days=1))
        assert len(sb.tables["ig_media_snapshots"]) == 6
        assert len(sb.tables["ig_media"]) == 3

    def test_fresh_running_claim_blocks_concurrent_run(self):
        adapter = _adapter()
        sb = FakeSupabase()
        sb.tables["snapshot_runs"] = [{
            "account_id": str(ACC), "snapshot_date": DAY.isoformat(), "status": "running",
            "started_at": (NOW - timedelta(minutes=10)).isoformat(),
        }]
        svc, _ = _svc(adapter, sb)
        assert svc.run_for_account(org_id=ORG, account_id=ACC).status == "skipped"

    def test_stale_running_claim_is_reclaimed(self):
        adapter = _adapter()
        sb = FakeSupabase()
        sb.tables["snapshot_runs"] = [{
            "account_id": str(ACC), "snapshot_date": DAY.isoformat(), "status": "running",
            "started_at": (NOW - timedelta(hours=3)).isoformat(),
        }]
        svc, _ = _svc(adapter, sb)
        assert svc.run_for_account(org_id=ORG, account_id=ACC).status == "done"
        assert sb.tables["snapshot_runs"][0]["status"] == "done"


class TestErrors:
    def test_per_media_failure_is_partial_and_keeps_previous_latest(self):
        adapter = _adapter()
        svc, sb = _svc(adapter)
        svc.run_for_account(org_id=ORG, account_id=ACC)
        adapter.seed(media_errors={"M2": MetaGraphError("media gone", code=100)})
        out = svc.run_for_account(org_id=ORG, account_id=ACC, snapshot_date=DAY + timedelta(days=1))
        assert out.status == "partial" and out.media_failed == 1
        assert out.errors and "M2" in out.errors[0]
        m2 = next(r for r in sb.tables["ig_media"] if r["ig_media_id"] == "M2")
        assert m2["latest_snapshot_date"] == DAY.isoformat()  # previous kept
        run = next(r for r in sb.tables["snapshot_runs"] if r["snapshot_date"] == (DAY + timedelta(days=1)).isoformat())
        assert run["status"] == "done" and "M2" in run["note"]

    def test_story_under_5_viewers_is_partial_not_fatal(self):
        story = IgMediaItem(id="S1", media_type="IMAGE", media_product_type="STORY",
                            timestamp=NOW - timedelta(hours=2))
        adapter = _adapter(stories=[story], media_errors={"S1": MetaGraphError("Not enough viewers", code=10)})
        svc, sb = _svc(adapter)
        out = svc.run_for_account(org_id=ORG, account_id=ACC)
        assert out.status == "partial" and out.stories_synced == 1
        assert any(r["ig_media_id"] == "S1" for r in sb.tables["ig_media"])

    def test_expired_story_is_not_queried(self):
        old = IgMediaItem(id="S0", media_product_type="STORY", timestamp=NOW - timedelta(hours=30))
        adapter = _adapter(stories=[old])
        svc, _ = _svc(adapter)
        out = svc.run_for_account(org_id=ORG, account_id=ACC)
        assert out.stories_synced == 0
        assert not any(c[1].get("media_id") == "S0" for c in adapter.calls)

    def test_auth_error_mid_walk_fails_the_run(self):
        adapter = _adapter(media_errors={"M2": MetaGraphError("expired", code=190)})
        svc, sb = _svc(adapter)
        with pytest.raises(IgSyncError) as ei:
            svc.run_for_account(org_id=ORG, account_id=ACC)
        assert isinstance(ei.value.__cause__, MetaGraphError)
        assert sb.tables["snapshot_runs"][0]["status"] == "error"

    def test_account_insights_permission_error_fails_the_run(self):
        adapter = _adapter(user_insights_error=MetaGraphError("missing scope", code=10))
        svc, sb = _svc(adapter)
        with pytest.raises(IgSyncError):
            svc.run_for_account(org_id=ORG, account_id=ACC)
        assert "ig_media" not in sb.tables

    def test_item_without_timestamp_is_skipped_and_counted(self):
        bad = IgMediaItem(id="X", media_type="IMAGE", media_product_type="FEED", timestamp=None)
        adapter = _adapter(media=[_media(1), bad])
        svc, sb = _svc(adapter)
        out = svc.run_for_account(org_id=ORG, account_id=ACC)
        assert out.media_skipped == 1 and out.media_synced == 1


class TestScopes:
    @pytest.mark.parametrize("meta,expected", [
        ({"scopes": ["instagram_business_basic", "instagram_business_manage_messages"]}, True),
        ({"scopes": ["instagram_business_basic", "instagram_business_manage_insights"]}, False),
        ({"scopes": ["instagram_business_manage_insights"], "granted_scopes": ["instagram_business_basic"]}, True),
        ({"scopes": ["instagram_business_manage_insights"], "granted_scopes": None}, False),
        ({"scope": "manual"}, False),  # unknown → let Graph decide
        ({}, False),
    ])
    def test_missing_insights_scope(self, meta, expected):
        assert missing_insights_scope({"metadata": meta}) is expected

    def test_granted_scopes_parses_csv(self):
        assert granted_scopes({"metadata": {"granted_scopes": "a, b"}}) == {"a", "b"}


class TestInsightsWindow:
    """Owner decision 2026-10-06: insights only for posts <= 90 BRT days old."""

    @staticmethod
    def _aged(days: int, i: int) -> IgMediaItem:
        return _media(i, ts=NOW - timedelta(days=days))

    def _run(self, ages):
        media = [self._aged(d, i + 10) for i, d in enumerate(ages)]
        ins = {m.id: {"views": 7, "reach": 5} for m in media}
        adapter = _adapter(media=media, media_insights=ins)
        calls = []
        orig = adapter.get_media_insights

        def spy(mid, *a, **k):
            calls.append(mid)
            return orig(mid, *a, **k)

        adapter.get_media_insights = spy
        svc, sb = _svc(adapter)
        return svc.run_for_account(org_id=ORG, account_id=ACC), sb, calls, media

    def test_boundary_89_90_in_91_out(self):
        out, sb, calls, media = self._run([89, 90, 91])
        assert INSIGHTS_WINDOW_DAYS == 90
        assert calls == [media[0].id, media[1].id]
        assert out.media_synced == 3 and out.snapshots_written == 2
        assert out.media_outside_window == 1 and out.insights_window_days == 90
        assert {r["ig_media_id"] for r in sb.tables["ig_media_snapshots"]} == {media[0].id, media[1].id}

    def test_old_post_cataloged_refreshed_and_keeps_latest_metrics(self):
        old = self._aged(200, 50)
        adapter = _adapter(media=[old], media_insights={old.id: {"views": 9}})
        sb = FakeSupabase()
        sb.tables["ig_media"] = [{
            "account_id": str(ACC), "ig_media_id": old.id, "like_count": 0,
            "latest_metrics": {"views": 1}, "latest_snapshot_date": "2026-07-01",
        }]
        svc, _ = _svc(adapter, sb)
        out = svc.run_for_account(org_id=ORG, account_id=ACC)
        row = next(r for r in sb.tables["ig_media"] if r["ig_media_id"] == old.id)
        assert row["like_count"] == old.like_count  # catalog refreshed
        assert row["latest_metrics"] == {"views": 1}
        assert row["latest_snapshot_date"] == "2026-07-01"
        assert out.snapshots_written == 0 and out.media_outside_window == 1
        assert out.status == "done"
