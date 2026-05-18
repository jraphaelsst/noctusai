"""Mocked test suite for the additive Meta **ads-management** surface
(`noctusai_lib.integrations.meta`).

Built ON the META-WRITE-LIB foundation (FB-post / IG-publish / ads
*read*). Covers the campaign→adset→ad→creative create-graph plus the
two update methods, on both concrete adapters:

- Fake: deterministic in-memory CRUD with id generation + create-graph
  linkage (`adset.campaign_id` resolves, `ad.adset_id` resolves);
  NEVER raises the App-Review gate (the Fake is the
  "scope-already-approved" path).
- Real: live Marketing-API POST via the existing `graph_post`; a
  scope-absent (`ads_management` not granted) response surfaces a
  typed `MetaGraphError(requires_app_review=True)` — never faked.

External boundary only is mocked: `httpx.get` / `httpx.post` are
patched (the real external Graph endpoint — sanctioned per CLAUDE.md
"external integrations OK"). No `noctusai_lib` code is monkey-patched;
the adapter, mappers and factory run for real against canned bodies.

Regression sentinels confirm the META-WRITE-LIB posting + ads-read
surface is unbroken by this additive extension. The pre-existing
`TestRouter` Starlette `on_startup`-drift failures
(`test_meta_integration.py`) are a SEPARATE fleet-wide seed-lib
version-reconcile and are explicitly out of scope here.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from noctusai_lib.integrations.meta import (
    FakeMetaAdapter,
    MetaGraphError,
    get_meta_adapter,
)
from noctusai_lib.integrations.meta.oauth_adapter import MetaOAuthAdapter
from noctusai_lib.integrations.meta.types import (
    Ad,
    AdCampaign,
    AdCreative,
    AdCreativeSpec,
    AdSet,
    AdSetSpec,
    AdSpec,
    CampaignSpec,
)


# ─── Test transport helper (mirrors test_meta_integration.py) ─────────────


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200, *, is_text=False):
        self._payload = payload
        self.status_code = status_code
        self._is_text = is_text

    def json(self):
        if self._is_text:
            raise ValueError("not json")
        return self._payload

    @property
    def text(self):
        return self._payload if self._is_text else str(self._payload)


_PERM_ERR = {
    "error": {
        "message": "(#200) ads_management permission required",
        "code": 200,
        "type": "OAuthException",
    }
}


# ─── TestAdsManagementTypes ───────────────────────────────────────────────


class TestAdsManagementTypes:
    """The new value objects + input specs (safety defaults)."""

    def test_specs_default_to_paused(self):
        # No-accidental-spend / no-accidental-delivery safety default.
        assert CampaignSpec(name="c", objective="OUTCOME_TRAFFIC").status == (
            "PAUSED"
        )
        assert (
            AdSetSpec(
                name="s",
                campaign_id="c1",
                daily_budget=500,
                billing_event="IMPRESSIONS",
                optimization_goal="REACH",
            ).status
            == "PAUSED"
        )
        assert (
            AdSpec(name="a", adset_id="s1", creative_id="cr1").status
            == "PAUSED"
        )

    def test_campaign_spec_special_categories_default_empty_list(self):
        # Graph requires the field explicitly — empty list is the
        # mandatory "no special category" answer, not omission.
        assert (
            CampaignSpec(
                name="c", objective="OUTCOME_TRAFFIC"
            ).special_ad_categories
            == []
        )

    def test_value_objects_are_frozen(self):
        for obj in (
            AdSet(id="s1"),
            Ad(id="a1"),
            AdCreative(id="cr1"),
            AdCampaign(id="camp1"),
        ):
            with pytest.raises(Exception):
                obj.id = "mutated"  # frozen dataclass


# ─── TestFakeAdsManagementGraph ───────────────────────────────────────────


class TestFakeAdsManagementGraph:
    """Deterministic in-memory create-graph — the 'scope approved'
    path that lets MCP/consumer tests exercise the real handler with
    no network."""

    def test_create_graph_end_to_end_with_linkage(self):
        fake = FakeMetaAdapter()
        camp = fake.create_ad_campaign(
            "act_1", CampaignSpec(name="Camp", objective="OUTCOME_TRAFFIC")
        )
        ad_set = fake.create_ad_set(
            "act_1",
            AdSetSpec(
                name="Set",
                campaign_id=camp.id,
                daily_budget=1000,
                billing_event="IMPRESSIONS",
                optimization_goal="REACH",
                targeting={"geo_locations": {"countries": ["BR"]}},
            ),
        )
        creative = fake.create_ad_creative(
            "act_1",
            AdCreativeSpec(
                name="Cr", object_story_spec={"page_id": "P1"}
            ),
        )
        ad = fake.create_ad(
            "act_1",
            AdSpec(name="Ad", adset_id=ad_set.id, creative_id=creative.id),
        )
        # Deterministic id generation.
        assert camp.id == "camp_1"
        assert ad_set.id == "adset_1"
        assert creative.id == "creative_1"
        assert ad.id == "ad_1"
        # Create-graph linkage resolves.
        assert ad_set.campaign_id == camp.id
        assert ad.adset_id == ad_set.id
        assert ad.creative_id == creative.id
        # Targeting + object-story passthrough preserved.
        assert ad_set.targeting == {"geo_locations": {"countries": ["BR"]}}
        assert creative.object_story_spec == {"page_id": "P1"}
        # Recorders captured every create, in order.
        assert [c.id for c in fake.created_campaigns] == ["camp_1"]
        assert [s.id for s in fake.created_ad_sets] == ["adset_1"]
        assert [c.id for c in fake.created_ad_creatives] == ["creative_1"]
        assert [a.id for a in fake.created_ads] == ["ad_1"]

    def test_ids_increment_per_kind(self):
        fake = FakeMetaAdapter()
        c1 = fake.create_ad_campaign(
            "act_1", CampaignSpec(name="A", objective="OUTCOME_AWARENESS")
        )
        c2 = fake.create_ad_campaign(
            "act_1", CampaignSpec(name="B", objective="OUTCOME_TRAFFIC")
        )
        assert (c1.id, c2.id) == ("camp_1", "camp_2")
        assert len(fake.created_campaigns) == 2

    def test_update_campaign_status_reflects_prior_fields(self):
        fake = FakeMetaAdapter()
        camp = fake.create_ad_campaign(
            "act_1", CampaignSpec(name="Camp", objective="OUTCOME_TRAFFIC")
        )
        updated = fake.update_campaign_status(camp.id, "ACTIVE")
        assert updated.id == camp.id
        assert updated.status == "ACTIVE"
        assert updated.effective_status == "ACTIVE"
        # Prior immutable fields carried forward.
        assert updated.name == "Camp"
        assert updated.objective == "OUTCOME_TRAFFIC"

    def test_update_ad_set_budget_reflects_prior_fields(self):
        fake = FakeMetaAdapter()
        camp = fake.create_ad_campaign(
            "act_1", CampaignSpec(name="Camp", objective="OUTCOME_TRAFFIC")
        )
        ad_set = fake.create_ad_set(
            "act_1",
            AdSetSpec(
                name="Set",
                campaign_id=camp.id,
                daily_budget=500,
                billing_event="IMPRESSIONS",
                optimization_goal="REACH",
            ),
        )
        updated = fake.update_ad_set_budget(ad_set.id, 2500)
        assert updated.id == ad_set.id
        assert updated.daily_budget == 2500
        # Prior fields carried forward (campaign linkage preserved).
        assert updated.campaign_id == camp.id
        assert updated.billing_event == "IMPRESSIONS"
        assert updated.optimization_goal == "REACH"

    def test_fake_never_raises_app_review_gate(self):
        # The App-Review honesty gate lives on the LIVE adapter only —
        # the Fake is the scope-already-approved path.
        fake = FakeMetaAdapter()
        camp = fake.create_ad_campaign(
            "act_1", CampaignSpec(name="C", objective="OUTCOME_TRAFFIC")
        )
        assert isinstance(camp, AdCampaign)  # no MetaGraphError raised


# ─── TestRealAdsManagementGraph ───────────────────────────────────────────


class TestRealAdsManagementGraph:
    """The live adapter ads-management paths — external Graph boundary
    mocked (`httpx.post` / `httpx.get` patched; no `noctusai_lib` code
    monkey-patched)."""

    def _adapter(self):
        return MetaOAuthAdapter(system_user_token="SYSTOK")

    def test_create_ad_campaign_real(self):
        a = self._adapter()
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "1201"})
        ):
            camp = a.create_ad_campaign(
                "123",
                CampaignSpec(name="Camp", objective="OUTCOME_TRAFFIC"),
            )
        assert camp.id == "1201"
        assert camp.name == "Camp"
        assert camp.objective == "OUTCOME_TRAFFIC"
        assert camp.status == "PAUSED"

    def test_create_ad_set_real(self):
        a = self._adapter()
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "9901"})
        ):
            ad_set = a.create_ad_set(
                "act_123",
                AdSetSpec(
                    name="Set",
                    campaign_id="1201",
                    daily_budget=1500,
                    billing_event="IMPRESSIONS",
                    optimization_goal="REACH",
                ),
            )
        assert ad_set.id == "9901"
        assert ad_set.campaign_id == "1201"
        assert ad_set.daily_budget == 1500

    def test_create_ad_creative_and_ad_real(self):
        a = self._adapter()
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "CR55"})
        ):
            cr = a.create_ad_creative(
                "123",
                AdCreativeSpec(
                    name="Cr", object_story_spec={"page_id": "P1"}
                ),
            )
        assert cr.id == "CR55"
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"id": "AD77"})
        ):
            ad = a.create_ad(
                "123",
                AdSpec(name="Ad", adset_id="9901", creative_id="CR55"),
            )
        assert ad.id == "AD77"
        assert ad.adset_id == "9901"
        assert ad.creative_id == "CR55"

    def test_update_campaign_status_reads_back(self):
        a = self._adapter()
        readback = {
            "id": "1201",
            "name": "Camp",
            "objective": "OUTCOME_TRAFFIC",
            "status": "ACTIVE",
            "effective_status": "ACTIVE",
        }
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"success": True})
        ), patch.object(
            httpx, "get", return_value=_FakeResponse(readback)
        ):
            camp = a.update_campaign_status("1201", "ACTIVE")
        # The update endpoint returns {"success": true} only — the
        # post-update state MUST be the read-back, never assumed.
        assert camp.status == "ACTIVE"
        assert camp.effective_status == "ACTIVE"
        assert camp.name == "Camp"

    def test_update_ad_set_budget_reads_back(self):
        a = self._adapter()
        readback = {
            "id": "9901",
            "name": "Set",
            "status": "PAUSED",
            "campaign_id": "1201",
            "daily_budget": 3000,
            "billing_event": "IMPRESSIONS",
            "optimization_goal": "REACH",
        }
        with patch.object(
            httpx, "post", return_value=_FakeResponse({"success": True})
        ), patch.object(
            httpx, "get", return_value=_FakeResponse(readback)
        ):
            ad_set = a.update_ad_set_budget("9901", 3000)
        assert ad_set.daily_budget == 3000
        assert ad_set.campaign_id == "1201"

    # ── The App-Review honesty gate — scope absent → never faked ──────

    def test_create_ad_campaign_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(
            httpx, "post", return_value=_FakeResponse(_PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.create_ad_campaign(
                    "123", CampaignSpec(name="C", objective="OUTCOME_TRAFFIC")
                )
        assert exc.value.requires_app_review is True
        assert exc.value.is_permission is True
        # Distinct from the token-expired classifier.
        assert exc.value.is_auth_error is False

    def test_create_ad_set_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(
            httpx, "post", return_value=_FakeResponse(_PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.create_ad_set(
                    "123",
                    AdSetSpec(
                        name="S",
                        campaign_id="c1",
                        daily_budget=500,
                        billing_event="IMPRESSIONS",
                        optimization_goal="REACH",
                    ),
                )
        assert exc.value.requires_app_review is True

    def test_create_ad_creative_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(
            httpx, "post", return_value=_FakeResponse(_PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.create_ad_creative("123", AdCreativeSpec(name="Cr"))
        assert exc.value.requires_app_review is True

    def test_create_ad_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(
            httpx, "post", return_value=_FakeResponse(_PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.create_ad(
                    "123",
                    AdSpec(name="A", adset_id="s1", creative_id="cr1"),
                )
        assert exc.value.requires_app_review is True

    def test_update_campaign_status_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(
            httpx, "post", return_value=_FakeResponse(_PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.update_campaign_status("1201", "ACTIVE")
        assert exc.value.requires_app_review is True

    def test_update_ad_set_budget_scope_absent_raises_app_review(self):
        a = self._adapter()
        with patch.object(
            httpx, "post", return_value=_FakeResponse(_PERM_ERR)
        ):
            with pytest.raises(MetaGraphError) as exc:
                a.update_ad_set_budget("9901", 3000)
        assert exc.value.requires_app_review is True


# ─── TestPriorSurfaceRegression ───────────────────────────────────────────


class TestPriorSurfaceRegression:
    """Sentinel: the additive ads-management extension must NOT alter
    the META-WRITE-LIB posting + ads-*read* surface. Re-exercises
    those methods end-to-end through the (now further-extended) Fake +
    Real adapters. `TestRouter` (pre-existing Starlette-drift, separate
    fleet reconcile) is intentionally excluded."""

    def test_meta_write_lib_posting_surface_unbroken(self):
        fake = FakeMetaAdapter()
        post = fake.publish_facebook_post("P1", "hello")
        media = fake.publish_instagram_media("IG1", "https://img/a.jpg", "c")
        assert post.id == "P1_1"
        assert media.id == "IG1_media_1"
        assert fake.published_posts == [post]
        assert fake.published_media == [media]
        # The new ads recorders are independent — no cross-contamination.
        assert fake.created_campaigns == []
        assert fake.created_ads == []

    def test_meta_write_lib_ads_read_surface_unbroken(self):
        a = MetaOAuthAdapter(system_user_token="SYSTOK")
        campaigns_body = {
            "data": [{"id": "c1", "name": "Camp1", "status": "ACTIVE"}],
            "paging": {},
        }
        with patch.object(
            httpx, "get", return_value=_FakeResponse(campaigns_body)
        ):
            camps = a.list_ad_campaigns("123")
        assert [c.id for c in camps] == ["c1"]
        insights_body = {"data": [{"impressions": "1000", "spend": "12.50"}]}
        with patch.object(
            httpx, "get", return_value=_FakeResponse(insights_body)
        ):
            ins = a.ad_insights("c1", "campaign")
        assert ins.metrics["impressions"] == 1000.0
        assert ins.metrics["spend"] == 12.5

    def test_factory_default_fake_carries_full_contract(self):
        # The factory still resolves to the Fake when no creds — and
        # the Fake now satisfies the read + posting + ads-read +
        # ads-management surface.
        impl = get_meta_adapter()
        assert isinstance(impl, FakeMetaAdapter)
        surface = (
            # read
            "status",
            "list_facebook_pages",
            "list_instagram_accounts",
            # posting (META-WRITE-LIB)
            "publish_facebook_post",
            "publish_instagram_media",
            # ads read (META-WRITE-LIB)
            "list_ad_campaigns",
            "ad_insights",
            # ads management (this wave)
            "create_ad_campaign",
            "create_ad_set",
            "create_ad_creative",
            "create_ad",
            "update_campaign_status",
            "update_ad_set_budget",
        )
        for name in surface:
            assert callable(getattr(impl, name)), f"Fake missing {name}"

    def test_both_adapters_carry_ads_management_contract(self):
        surface = (
            "create_ad_campaign",
            "create_ad_set",
            "create_ad_creative",
            "create_ad",
            "update_campaign_status",
            "update_ad_set_budget",
        )
        for impl in (
            FakeMetaAdapter(),
            MetaOAuthAdapter(system_user_token="X"),
        ):
            for name in surface:
                assert callable(getattr(impl, name)), (
                    f"{type(impl).__name__} missing {name}"
                )
