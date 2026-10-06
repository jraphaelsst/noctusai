"""Module registration, metric catalog parity, scheduler walk, and the
Instagram-Login bridge behind ``/api/meta/instagram/*``."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from noctusai_lib.integrations.meta import (
    IG_MEDIA_METRICS_BY_PRODUCT_TYPE,
    FakeInstagramLoginAdapter,
    IgMediaItem,
    IgProfile,
    MetaGraphError,
)

from app.modules.instagram.metrics import (
    MEDIA_PRIORITY,
    METRIC_META,
    media_metric_descriptors,
)
from app.modules.instagram.repository import IgInsightsRepository
from tests.modules.instagram.fakes import FakeSupabase


class TestRegistration:
    def test_register_shape_and_job(self):
        from noctusai_lib.api import scheduler as seed_scheduler

        from app.main import ModuleRegistration
        from app.modules.instagram import register
        from app.modules.instagram.scheduler import JOB_NAME

        reg = register()
        assert isinstance(reg, ModuleRegistration)
        assert [r.prefix for r in reg.routers] == ["/api/instagram"]
        assert reg.standard_routers == ()
        assert seed_scheduler.scheduler.get_job(JOB_NAME) is not None


class TestMetricCatalog:
    @pytest.mark.parametrize("ptype", sorted(IG_MEDIA_METRICS_BY_PRODUCT_TYPE))
    def test_every_seed_metric_has_label_and_priority(self, ptype):
        seed_metrics = set(IG_MEDIA_METRICS_BY_PRODUCT_TYPE[ptype])
        assert seed_metrics <= set(METRIC_META), seed_metrics - set(METRIC_META)
        assert set(MEDIA_PRIORITY[ptype]) == seed_metrics

    @pytest.mark.parametrize("mpt,mt,first", [
        ("REELS", "VIDEO", ["views", "reach", "ig_reels_avg_watch_time"]),
        ("FEED", "IMAGE", ["views", "reach", "total_interactions"]),
        ("FEED", "CAROUSEL_ALBUM", ["views", "reach", "total_interactions"]),
        ("STORY", "IMAGE", ["views", "reach", "replies"]),
        (None, "VIDEO", ["views", "reach", "ig_reels_avg_watch_time"]),
    ])
    def test_priority_order(self, mpt, mt, first):
        d = media_metric_descriptors(mpt, mt)
        assert [x["key"] for x in d][:3] == first
        assert [x["priority"] for x in d] == list(range(1, len(d) + 1))


class TestScheduler:
    def test_walk_skips_missing_scope_and_isolates_failures(self):
        from app.modules.instagram.scheduler import run_daily_sync

        ok, bad, noscope = (
            "00000000-0000-4000-8000-0000000000a1",
            "00000000-0000-4000-8000-0000000000a2",
            "00000000-0000-4000-8000-0000000000a3",
        )
        org = "00000000-0000-4000-8000-000000000001"
        ins = {"scopes": ["instagram_business_manage_insights"]}
        sb = FakeSupabase()
        sb.tables["integration_accounts"] = [
            {"id": ok, "org_id": org, "provider": "instagram", "status": "validated", "metadata": ins},
            {"id": bad, "org_id": org, "provider": "instagram", "status": "validated", "metadata": ins},
            {"id": noscope, "org_id": org, "provider": "instagram", "status": "validated",
             "metadata": {"scopes": ["instagram_business_basic"]}},
            {"id": "x", "org_id": org, "provider": "youtube", "status": "validated", "metadata": {}},
            {"id": "y", "org_id": org, "provider": "instagram", "status": "error", "metadata": ins},
        ]
        good = FakeInstagramLoginAdapter().seed(
            profile=IgProfile(id="A", user_id="U", username="u"),
            media=[IgMediaItem(id="M", media_product_type="FEED",
                               timestamp=datetime.now(timezone.utc) - timedelta(days=1))],
        )
        broken = FakeInstagramLoginAdapter().seed(
            user_insights_error=MetaGraphError("expired", code=190))

        def builder(account_id, org_id):
            return good if str(account_id) == ok else broken

        tally = run_daily_sync(repo=IgInsightsRepository(sb), adapter_builder=builder)
        assert tally["accounts"] == 3
        assert tally["done"] == 1 and tally["failed"] == 1 and tally["missing_scope"] == 1
        assert {r["account_id"] for r in sb.tables["ig_media"]} == {ok}


class TestInstagramLoginBridge:
    def _bridge(self):
        from app.services.meta.ig_login_bridge import InstagramLoginInsightsBridge

        fake = FakeInstagramLoginAdapter().seed(
            profile=IgProfile(id="A", user_id="IGU", username="acme", followers_count=7),
            media=[IgMediaItem(id="R1", media_type="VIDEO", media_product_type="REELS")],
            media_insights={"R1": {"views": 9, "ig_reels_avg_watch_time": 1234}},
            user_insights={"reach": 3},
        )
        return InstagramLoginInsightsBridge(fake), fake

    def test_accounts_media_insights(self):
        bridge, fake = self._bridge()
        acct = bridge.list_instagram_accounts()[0]
        assert acct.id == "IGU" and acct.followers_count == 7 and acct.page_id is None
        media = bridge.list_instagram_media("IGU", 10)
        assert [m.id for m in media] == ["R1"]
        ins = bridge.get_instagram_media_insights("R1")
        # Unserved metrics are OMITTED (legacy int map), never 0.
        assert ins.metrics == {"views": 9, "ig_reels_avg_watch_time": 1234}
        asked = [c for c in fake.calls if c[0] == "get_media_insights"][0][1]
        assert asked["media_product_type"] == "REELS"
        acc_ins = bridge.get_instagram_account_insights("IGU", metrics=["reach", "profile_views"])
        assert acc_ins.metrics == {"reach": 3}
        assert acc_ins.raw == [{"unsupported": ["profile_views"]}]

    def test_unbridged_surface_fails_loud(self):
        from app.services.meta.ig_login_bridge import NotBridgedError

        bridge, _ = self._bridge()
        with pytest.raises(NotBridgedError):
            bridge.list_facebook_pages()
        assert not hasattr(bridge, "publish_facebook_post")

    def test_legacy_endpoint_served_from_instagram_login_account(self):
        """GET /api/meta/instagram/insights now works for a provider="instagram"
        account (previously 404) — exercised through the provider-aware seam."""
        from fastapi.testclient import TestClient

        from app.dependencies import get_current_user_org
        from app.main import app
        from app.routers._meta_common import get_ig_insights_adapter

        bridge, _ = self._bridge()
        app.dependency_overrides[get_ig_insights_adapter] = lambda: bridge
        app.dependency_overrides[get_current_user_org] = lambda: (object(), "t", "00000000-0000-4000-8000-000000000001")
        try:
            c = TestClient(app)
            r = c.get("/api/meta/instagram/insights?account_id=00000000-0000-4000-8000-0000000000a1")
            assert r.status_code == 200, r.text
            assert r.json()["object_id"] == "IGU"
            r = c.get("/api/meta/instagram/media?account_id=00000000-0000-4000-8000-0000000000a1")
            assert r.json()["media"][0]["insights"]["views"] == 9
        finally:
            app.dependency_overrides.clear()


class TestProviderDispatch:
    """``get_ig_insights_adapter_for_account`` routes by provider."""

    class _Svc:
        def __init__(self, provider, tokens=None):
            from types import SimpleNamespace
            self.acct = SimpleNamespace(
                id=UUID(int=1), org_id=UUID(int=2), provider=provider,
                created_at=None, updated_at=None, metadata={},
            )
            self.tokens = tokens or {}

        def get_account(self, a, o):
            return self.acct

        def decrypt_credential(self, a, o):
            return dict(self.tokens)

    def test_instagram_row_is_bridged_over_real_ig_login_adapter(self):
        from noctusai_lib.integrations.meta import InstagramLoginOAuthAdapter

        from app.services.meta import get_ig_insights_adapter_for_account
        from app.services.meta.ig_login_bridge import InstagramLoginInsightsBridge

        a = get_ig_insights_adapter_for_account(
            UUID(int=1), UUID(int=2), svc=self._Svc("instagram", {"access_token": "IGTOK"}))
        assert isinstance(a, InstagramLoginInsightsBridge)
        assert isinstance(a.ig_login_adapter, InstagramLoginOAuthAdapter)

    def test_instagram_row_without_token_fails_loud(self):
        from app.services.meta import get_ig_insights_adapter_for_account

        with pytest.raises(ValueError, match="reconnect"):
            get_ig_insights_adapter_for_account(UUID(int=1), UUID(int=2), svc=self._Svc("instagram"))

    def test_meta_row_keeps_facebook_login_path(self):
        from app.services.meta import MetaOAuthAdapter, get_ig_insights_adapter_for_account

        a = get_ig_insights_adapter_for_account(UUID(int=1), UUID(int=2), svc=self._Svc("meta"))
        assert isinstance(a, MetaOAuthAdapter)

    def test_unsupported_provider_raises_value_error(self):
        from app.services.meta import get_ig_insights_adapter_for_account

        with pytest.raises(ValueError):
            get_ig_insights_adapter_for_account(
                UUID(int=1), UUID(int=2), svc=self._Svc("youtube"))
