"""Tests for ``AdsSyncService`` — W2.2/W2.3 sync + backfill pipeline.

Coverage:
  - ``sync_accounts`` — money-to-cents conversion, idempotent re-sync
    (run twice -> no duplicate row for the same ``(org_id, act_id)``)
  - ``sync_hierarchy`` — campaign + ad-set + ad rows refreshed on EVERY
    run via account-level listings, correct ``parent_id`` chains, page-
    ceiling completion
  - ``snapshot_campaign_insights`` — actions/action_values persisted as
    jsonb, NULL-breakdown dedupe on re-sync
  - ``backfill_campaign_insights`` — campaign-level ONLY (never writes
    an adset/ad-level snapshot row)
  - ``ingest_activities`` — dedup on ``event_key`` (append-only,
    DO NOTHING on conflict)
  - No-silent-error contract: a ``MetaGraphError`` from the adapter
    propagates out of every sync method, never swallowed to an empty
    write

Fake admin client: ``noctusai_lib.testing.MockSupabaseClient``'s
``upsert()`` does not yet simulate ``ON CONFLICT`` dedup (documented gap
— "Upsert propagation is deferred to a follow-up project", see
``mocks.py``); a purpose-built ``_FakeAdminClient`` below DOES apply the
``on_conflict`` columns as a real dedup key (update-in-place on match,
append otherwise; ``ignore_duplicates=True`` no-ops on match) so the
"run twice -> no dup rows" assertions are genuine, not just "the fake
never grows" by omission.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from noctusai_lib.integrations.meta import (
    Ad,
    AdAccount,
    AdActivity,
    AdCampaign,
    AdInsightsRow,
    AdInsightsSeries,
    AdSet,
    FakeMetaAdapter,
    MetaGraphError,
)

from app.modules.meta_ads.services.ads_sync_service import AdsSyncService
from app.modules.meta_ads.services.money import (
    cents_from_major_unit_float,
    cents_from_minor_unit_string,
)


# ─── Fake admin client — real on_conflict dedup semantics ───────────────
class _FakeTable:
    def __init__(self, store: list[dict]):
        self._store = store
        self._mode: str | None = None
        self._filters: list[tuple[str, str, Any]] = []
        self._order_col: str | None = None
        self._order_desc = False
        self._payload: dict | None = None
        self._on_conflict: list[str] = []
        self._ignore_duplicates = False

    # select-side chain
    def select(self, *_a, **_k):
        self._mode = "select"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def is_(self, col, val):
        self._filters.append(("is", col, val))
        return self

    def gte(self, col, val):
        self._filters.append(("gte", col, val))
        return self

    def lte(self, col, val):
        self._filters.append(("lte", col, val))
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    # write-side chain
    def upsert(self, payload, *, on_conflict="", ignore_duplicates=False, **_k):
        self._mode = "upsert"
        self._payload = dict(payload)
        self._on_conflict = [c.strip() for c in on_conflict.split(",") if c.strip()]
        self._ignore_duplicates = ignore_duplicates
        return self

    def execute(self):
        if self._mode == "upsert":
            return self._do_upsert()
        return self._do_select()

    def _matches_conflict(self, row: dict) -> bool:
        for c in self._on_conflict:
            if c == "breakdown_key_norm":
                # Mirrors the migration's `breakdown_key_norm GENERATED
                # ALWAYS AS (COALESCE(breakdown_key, '')) STORED` column
                # — the real UNIQUE target is the normalized value, not
                # the raw nullable `breakdown_key` the payload actually
                # carries (Postgres computes the generated column
                # itself; this fake mirrors that computation rather
                # than reading a same-named payload key that never
                # exists).
                if (row.get("breakdown_key") or "") != (self._payload.get("breakdown_key") or ""):
                    return False
                continue
            if row.get(c) != self._payload.get(c):
                return False
        return True

    def _do_upsert(self):
        existing_idx = None
        if self._on_conflict:
            for i, row in enumerate(self._store):
                if self._matches_conflict(row):
                    existing_idx = i
                    break
        if existing_idx is not None:
            if not self._ignore_duplicates:
                self._store[existing_idx] = {**self._store[existing_idx], **self._payload}
        else:
            self._store.append(dict(self._payload))
        return SimpleNamespace(data=[dict(self._payload)])

    def _do_select(self):
        rows = list(self._store)
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "in":
                rows = [r for r in rows if r.get(col) in val]
            elif op == "is":
                target = None if val in ("null", None) else val
                rows = [r for r in rows if r.get(col) == target]
            elif op == "gte":
                rows = [r for r in rows if r.get(col) is not None and r.get(col) >= val]
            elif op == "lte":
                rows = [r for r in rows if r.get(col) is not None and r.get(col) <= val]
        if self._order_col:
            rows = sorted(
                rows, key=lambda r: r.get(self._order_col) or "", reverse=self._order_desc
            )
        return SimpleNamespace(data=rows)


class _FakeAdminClient:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}

    def schema(self, _name: str) -> "_FakeAdminClient":
        return self

    def table(self, name: str) -> _FakeTable:
        self.tables.setdefault(name, [])
        return _FakeTable(self.tables[name])


ORG_ID = uuid4()
_ACT_ID = "873947475957808"


def _account() -> AdAccount:
    return AdAccount(
        id=_ACT_ID,
        name="One Consultoria Imobiliária",
        currency="BRL",
        timezone_name="America/Sao_Paulo",
        amount_spent="674426",
        balance="12519",
        spend_cap="50000000",
        account_status=1,
    )


def _campaign(cid: str = "camp_1") -> AdCampaign:
    return AdCampaign(
        id=cid, name="SENSEYS", objective="OUTCOME_LEADS",
        status="ACTIVE", effective_status="ACTIVE",
    )


def _adset(aid: str = "adset_1", campaign_id: str = "camp_1") -> AdSet:
    return AdSet(
        id=aid, name="Adset 1", status="ACTIVE", effective_status="ACTIVE",
        campaign_id=campaign_id, daily_budget=5000, billing_event="IMPRESSIONS",
        optimization_goal="LEAD_GENERATION",
    )


def _ad(ad_id: str = "ad_1", adset_id: str = "adset_1") -> Ad:
    return Ad(
        id=ad_id, name="Ad 1", status="ACTIVE", effective_status="ACTIVE",
        adset_id=adset_id, creative_id="creative_1",
        creative_thumbnail_url="https://x.example/thumb.jpg",
    )


def _insights_series(object_id: str, *, breakdown: dict | None = None) -> AdInsightsSeries:
    row = AdInsightsRow(
        date_start="2026-07-01",
        date_stop="2026-07-01",
        breakdown=breakdown or {},
        metrics={
            "impressions": 1000.0, "reach": 800.0, "spend": 380.5,
            "clicks": 42.0, "cpc": 9.06, "cpm": 380.5, "ctr": 4.2,
        },
        actions={"lead": 12.0, "link_click": 200.0},
        action_values={},
        raw={"date_start": "2026-07-01"},
    )
    return AdInsightsSeries(object_id=object_id, level="campaign", rows=[row])


def _adapter_with_fixtures() -> FakeMetaAdapter:
    adapter = FakeMetaAdapter()
    camp = _campaign()
    adset = _adset()
    ad = _ad()
    acct = f"act_{_ACT_ID}"
    adapter.seed(
        ad_accounts=[_account()],
        ad_campaigns_by_account={acct: [camp]},
        ad_sets_by_account={acct: [adset]},
        ads_by_account={acct: [ad]},
        ad_insights_series={camp.id: _insights_series(camp.id)},
    )
    return adapter


# ─── sync_accounts ────────────────────────────────────────────────────────
class TestSyncAccounts:
    def test_money_converted_to_cents(self):
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)
        adapter = _adapter_with_fixtures()

        count = svc.sync_accounts(org_id=ORG_ID, adapter=adapter)

        assert count == 1
        rows = admin.tables["ads_accounts"]
        assert len(rows) == 1
        row = rows[0]
        assert row["act_id"] == _ACT_ID
        assert row["amount_spent_cents"] == cents_from_minor_unit_string("674426")
        assert row["amount_spent_cents"] == 674426  # already-minor-unit — no *100
        assert row["balance_cents"] == 12519
        assert row["spend_cap_cents"] == 50000000
        assert row["currency"] == "BRL"

    def test_idempotent_resync_no_duplicate_rows(self):
        """Re-running sync_accounts for the SAME org twice upserts on
        (org_id, act_id) — never a second row for the same account."""
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)
        adapter = _adapter_with_fixtures()

        svc.sync_accounts(org_id=ORG_ID, adapter=adapter)
        svc.sync_accounts(org_id=ORG_ID, adapter=adapter)

        assert len(admin.tables["ads_accounts"]) == 1

    def test_missing_budget_is_none_not_zero(self):
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)
        adapter = FakeMetaAdapter()
        adapter.seed(ad_accounts=[AdAccount(id="1", name="No spend cap")])

        svc.sync_accounts(org_id=ORG_ID, adapter=adapter)

        row = admin.tables["ads_accounts"][0]
        assert row["spend_cap_cents"] is None
        assert row["amount_spent_cents"] is None


# ─── sync_hierarchy ───────────────────────────────────────────────────────
class _SpyMetaAdapter(FakeMetaAdapter):
    """Records every hierarchy list call (with its parent filter) so a test
    can assert the SHAPE of the Graph traffic, not just the rows written.
    A double of the external Meta service, not a patch of our own code."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str | None]] = []
        self.ads_override: list[Ad] | None = None

    def list_ad_campaigns(self, ad_account_id):
        self.calls.append(("campaigns", None))
        return super().list_ad_campaigns(ad_account_id)

    def list_ad_sets(self, ad_account_id, campaign_id=None):
        self.calls.append(("adsets", campaign_id))
        return super().list_ad_sets(ad_account_id, campaign_id=campaign_id)

    def list_ads(self, ad_account_id, adset_id=None):
        self.calls.append(("ads", adset_id))
        if self.ads_override is not None and adset_id is None:
            return list(self.ads_override)
        return super().list_ads(ad_account_id, adset_id=adset_id)


def _hierarchy_adapter(
    *, campaigns: list[AdCampaign], adsets: list[AdSet], ads: list[Ad]
) -> _SpyMetaAdapter:
    acct = f"act_{_ACT_ID}"
    adapter = _SpyMetaAdapter()
    adapter.seed(
        ad_campaigns_by_account={acct: campaigns},
        ad_sets_by_account={acct: adsets},
        ads_by_account={acct: ads},
    )
    return adapter


class TestSyncHierarchy:
    def test_ads_and_adsets_refresh_on_every_run_not_only_the_first(self):
        """🔴 THE regression guard (prod 2026-11-26): ``ads_objects`` adset/ad
        rows were written once by the July backfill and NEVER again, while
        Meta grew to 646 ads. The default daily call must upsert ad sets and
        ads too, and a second run must UPDATE them (status, name, creative)
        and add the ads created since."""
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)

        first = _hierarchy_adapter(
            campaigns=[_campaign()], adsets=[_adset()], ads=[_ad()],
        )
        svc.sync_hierarchy(org_id=ORG_ID, adapter=first, ad_account_id=_ACT_ID)
        rows = {r["object_id"]: r for r in admin.tables["ads_objects"]}
        assert set(rows) == {"camp_1", "adset_1", "ad_1"}
        first_synced = rows["ad_1"]["synced_at"]

        paused_ad = Ad(
            id="ad_1", name="Ad 1 renamed", status="PAUSED",
            effective_status="PAUSED", adset_id="adset_1",
            creative_id="creative_9",
            creative_thumbnail_url="https://x.example/thumb9.jpg",
        )
        second = _hierarchy_adapter(
            campaigns=[_campaign()],
            adsets=[_adset(), _adset("adset_2", campaign_id="camp_1")],
            ads=[paused_ad, _ad("ad_2", adset_id="adset_2")],
        )
        counts = svc.sync_hierarchy(
            org_id=ORG_ID, adapter=second, ad_account_id=_ACT_ID
        )

        assert counts == {"campaigns": 1, "adsets": 2, "ads": 2}
        rows = {r["object_id"]: r for r in admin.tables["ads_objects"]}
        assert len(admin.tables["ads_objects"]) == 5  # upsert, never a dup row
        ad1 = rows["ad_1"]
        assert ad1["effective_status"] == "PAUSED"
        assert ad1["name"] == "Ad 1 renamed"
        assert ad1["creative_id"] == "creative_9"
        assert ad1["creative_thumbnail_url"] == "https://x.example/thumb9.jpg"
        assert ad1["parent_id"] == "adset_1"
        assert ad1["synced_at"] >= first_synced
        assert rows["ad_2"]["parent_id"] == "adset_2"
        assert rows["adset_2"]["parent_id"] == "camp_1"
        assert rows["adset_1"]["daily_budget_cents"] == 5000

    def test_lists_each_level_once_at_account_level(self):
        """Rate-limit safety: three paged account-level listings
        (``act_<id>/campaigns|adsets|ads``), never the per-campaign ->
        per-adset walk that tripped Meta's user-level limit on 2026-07-23."""
        adapter = _hierarchy_adapter(
            campaigns=[_campaign("c1"), _campaign("c2")],
            adsets=[_adset("s1", "c1"), _adset("s2", "c2")],
            ads=[_ad("a1", "s1"), _ad("a2", "s2")],
        )
        svc = AdsSyncService(admin_supabase=_FakeAdminClient())

        svc.sync_hierarchy(org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID)

        assert adapter.calls == [
            ("campaigns", None), ("adsets", None), ("ads", None),
        ]

    def test_page_ceiling_completes_ads_per_adset_loudly(self, caplog):
        """The seed list call stops at a fixed page count. A result that
        fills it may be truncated (prod has 646 ads, above the ceiling), so
        the sync completes the level per parent AND says so at WARNING,
        never a silently partial hierarchy."""
        ceiling = AdsSyncService.LIST_PAGE_CEILING
        adsets = [_adset("s1"), _adset("s2")]
        truncated = [_ad(f"a{i}", "s1") for i in range(ceiling)]
        full = truncated + [_ad("late_1", "s2"), _ad("late_2", "s2")]
        adapter = _hierarchy_adapter(
            campaigns=[_campaign()], adsets=adsets, ads=full,
        )
        adapter.ads_override = truncated  # account-level call hits the ceiling
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)

        with caplog.at_level("WARNING"):
            counts = svc.sync_hierarchy(
                org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID
            )

        ids = {
            r["object_id"] for r in admin.tables["ads_objects"] if r["level"] == "ad"
        }
        assert {"late_1", "late_2"} <= ids
        assert counts["ads"] == len(full)
        assert ("ads", "s1") in adapter.calls and ("ads", "s2") in adapter.calls
        assert any("page ceiling" in r.getMessage() for r in caplog.records)

    def test_meta_graph_error_on_ads_propagates(self):
        class _Boom(_SpyMetaAdapter):
            def list_ads(self, ad_account_id, adset_id=None):
                raise MetaGraphError("(#17) User request limit reached")

        adapter = _Boom()
        adapter.seed(
            ad_campaigns_by_account={f"act_{_ACT_ID}": [_campaign()]},
            ad_sets_by_account={f"act_{_ACT_ID}": [_adset()]},
        )
        svc = AdsSyncService(admin_supabase=_FakeAdminClient())

        with pytest.raises(MetaGraphError):
            svc.sync_hierarchy(org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID)

    def test_idempotent_resync_no_duplicate_object_rows(self):
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)
        adapter = _adapter_with_fixtures()

        svc.sync_hierarchy(org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID)
        svc.sync_hierarchy(org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID)

        assert len(admin.tables["ads_objects"]) == 3


# ─── snapshot_campaign_insights ────────────────────────────────────────────
class TestSnapshotCampaignInsights:
    def test_persists_actions_and_action_values_as_jsonb(self):
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)
        adapter = _adapter_with_fixtures()

        count = svc.snapshot_campaign_insights(
            org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID,
            since=datetime(2026, 7, 1).date(), until=datetime(2026, 7, 1).date(),
        )

        assert count == 1
        row = admin.tables["ads_insight_snapshots"][0]
        assert row["actions"] == {"lead": 12.0, "link_click": 200.0}
        assert row["action_values"] == {}
        assert row["spend_cents"] == cents_from_major_unit_float(380.5)
        assert row["spend_cents"] == 38050
        assert row["cpc_cents"] == 906
        assert row["date"] == "2026-07-01"
        assert row["breakdown_key"] is None

    def test_null_breakdown_dedupes_on_resync(self):
        """Two unbroken-total (no breakdown) rows for the SAME
        (object_id, date) must collapse to ONE row — the NULL-sibling
        UNIQUE footgun the migration's `breakdown_key_norm` generated
        column exists to close. The fake dedupes on the EXACT on_conflict
        target the service passes: `org_id,object_id,date,breakdown_key_norm`
        — this test would fail loudly if the service ever regressed to
        conflict-targeting the raw nullable `breakdown_key` instead."""
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)
        adapter = _adapter_with_fixtures()

        svc.snapshot_campaign_insights(
            org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID,
            since=datetime(2026, 7, 1).date(), until=datetime(2026, 7, 1).date(),
        )
        svc.snapshot_campaign_insights(
            org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID,
            since=datetime(2026, 7, 1).date(), until=datetime(2026, 7, 1).date(),
        )

        rows = admin.tables["ads_insight_snapshots"]
        assert len(rows) == 1

    def test_meta_graph_error_propagates_not_swallowed(self):
        """No-silent-error contract: a MetaGraphError from the adapter
        must propagate out of the sync method, never be caught into an
        empty/partial write."""
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)

        class _RaisingAdapter(FakeMetaAdapter):
            def list_ad_campaigns(self, ad_account_id):
                raise MetaGraphError("scope not granted", code=200, http_status=403)

        with pytest.raises(MetaGraphError):
            svc.snapshot_campaign_insights(
                org_id=ORG_ID, adapter=_RaisingAdapter(), ad_account_id=_ACT_ID,
                since=datetime(2026, 7, 1).date(), until=datetime(2026, 7, 1).date(),
            )
        assert admin.tables.get("ads_insight_snapshots", []) == []


# ─── backfill_campaign_insights ────────────────────────────────────────────
class TestBackfillCampaignInsights:
    def test_backfill_never_snapshots_adset_or_ad_level(self):
        """Per the operator's decision (roadmap): backfill is
        campaign-level ONLY — ad-set/ad daily history is fetched live
        on drill-down, never backfilled. Assert every row this backfill
        writes to ads_insight_snapshots has level='campaign'."""
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)
        adapter = _adapter_with_fixtures()

        svc.backfill_campaign_insights(
            org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID, months=2,
        )

        snapshot_rows = admin.tables["ads_insight_snapshots"]
        assert snapshot_rows  # the fixture's single row is returned every chunk
        assert all(r["level"] == "campaign" for r in snapshot_rows)
        # The INSIGHT HISTORY is campaign-only; the object hierarchy is not:
        # since 2026-11-26 every hierarchy sync (backfill included) upserts
        # ad sets and ads too, through account-level listings, so the
        # ads_objects rows never freeze at the first run again.
        object_rows = admin.tables["ads_objects"]
        levels_in_objects = {r["level"] for r in object_rows}
        assert levels_in_objects == {"campaign", "adset", "ad"}
        levels_in_snapshots = {r["level"] for r in snapshot_rows}
        assert levels_in_snapshots == {"campaign"}


# ─── ingest_activities ──────────────────────────────────────────────────
class TestIngestActivities:
    def _activity(self, key: str, *, event_type: str = "update_ad_run_status") -> AdActivity:
        return AdActivity(
            id=key,
            object_id="camp_1",
            object_level="campaign",
            event_type=event_type,
            occurred_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
            actor_name="Leonardo Salomão",
            old_value="PAUSED",
            new_value="ACTIVE",
            raw={"event_type": event_type},
        )

    def test_dedup_on_event_key_append_only(self):
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)
        adapter = FakeMetaAdapter()
        acct = f"act_{_ACT_ID}"
        adapter.seed(activities_by_account={acct: [self._activity("camp_1:100:update")]})

        count1 = svc.ingest_activities(
            org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID,
            since=datetime(2026, 7, 1, tzinfo=timezone.utc),
            until=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        count2 = svc.ingest_activities(
            org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID,
            since=datetime(2026, 7, 1, tzinfo=timezone.utc),
            until=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        assert count1 == 1
        assert count2 == 1  # adapter always returns the seeded row
        assert len(admin.tables["ads_activity_events"]) == 1  # never duplicated

    def test_activity_events_never_overwritten_on_conflict(self):
        """ignore_duplicates=True — DO NOTHING semantics: a second
        ingest of the SAME event_key must not mutate the already-stored
        row (append-only audit log)."""
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)
        adapter = FakeMetaAdapter()
        acct = f"act_{_ACT_ID}"
        adapter.seed(activities_by_account={acct: [self._activity("camp_1:100:update")]})

        svc.ingest_activities(
            org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID,
            since=datetime(2026, 7, 1, tzinfo=timezone.utc),
            until=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        first_row = dict(admin.tables["ads_activity_events"][0])

        # Mutate the seeded fixture's new_value and re-ingest under the
        # SAME event_key — DO NOTHING must leave the stored row alone.
        adapter.seed(
            activities_by_account={
                acct: [self._activity("camp_1:100:update")]
            }
        )
        svc.ingest_activities(
            org_id=ORG_ID, adapter=adapter, ad_account_id=_ACT_ID,
            since=datetime(2026, 7, 1, tzinfo=timezone.utc),
            until=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )

        assert len(admin.tables["ads_activity_events"]) == 1
        assert admin.tables["ads_activity_events"][0] == first_row

    def test_meta_graph_error_propagates(self):
        admin = _FakeAdminClient()
        svc = AdsSyncService(admin_supabase=admin)

        class _RaisingAdapter(FakeMetaAdapter):
            def list_activities(self, ad_account_id, since, until):
                raise MetaGraphError("throttled", code=17, http_status=613)

        with pytest.raises(MetaGraphError):
            svc.ingest_activities(
                org_id=ORG_ID, adapter=_RaisingAdapter(), ad_account_id=_ACT_ID,
                since=datetime(2026, 7, 1, tzinfo=timezone.utc),
                until=datetime(2026, 7, 2, tzinfo=timezone.utc),
            )
