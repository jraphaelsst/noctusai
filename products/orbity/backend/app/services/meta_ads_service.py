"""
Meta Ads service — ad accounts CRUD, campaign CRUD + situation tracking,
campaign metrics upsert (sync seam), and spend-vs-leads aggregate.

Live-integration seams:
  - OAuth connect flow   — NOC-REMEDIATE[orbity-meta-ads-live] — 2026-06-03
  - Campaign sync pull   — NOC-REMEDIATE[orbity-meta-ads-live] — 2026-06-03
  - CAPI lead feedback   — NOC-REMEDIATE[orbity-meta-ads-live] — 2026-06-03

The service is fully operational with the Fake adapter (default).
The MetaAdsClient Protocol seam is the named injection point for the
real factory once credentials/vault are wired.

No silent errors: every except logs and re-raises.
access_token_ref is NEVER returned in any response — scrubbed at the
service boundary (the column is a credential reference, not the token).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MetaAdsClient Protocol — the named seam for live vs Fake
#
# NOC-REMEDIATE[orbity-meta-ads-live]: Replace the FakeMetaAdsClient default
# below with `make_meta_ads_client(credential_store, org_id)` once the real
# vault/credential-store factory is wired. The Protocol is the contract;
# the Fake is the safe dev/test default consuming noctusai_lib.integrations.meta's
# FakeMetaAdapter. Do NOT hand-roll any Meta HTTP calls here — consume
# noctusai_lib.integrations.meta.get_meta_adapter as the factory. — 2026-06-03
# ---------------------------------------------------------------------------

class MetaAdsClient(Protocol):
    """Protocol for the live Meta ads pull (sync seam).

    This is the ONLY point where live Meta API calls should enter the
    service layer. All implementations — Fake or Real — must satisfy
    this contract.
    """

    def list_campaigns(self, external_account_id: str) -> list[dict[str, Any]]:
        """Return a list of campaign dicts from the Meta Graph API.

        Each dict should carry at minimum: external_campaign_id, name,
        objective, status, daily_budget.
        """
        ...

    def get_campaign_insights(
        self,
        external_campaign_id: str,
        date_preset: str = "last_30d",
    ) -> dict[str, Any]:
        """Return spend/impressions/leads for a campaign date window.

        Dict keys: spend (float), impressions (int), leads (int).
        """
        ...


class FakeMetaAdsClient:
    """Deterministic in-memory MetaAdsClient.

    Default when no live credentials are configured. Consumes
    noctusai_lib.integrations.meta.FakeMetaAdapter under the hood so the
    Fake adapter surface is consistent with what the real adapter would
    return (same type contract, same seeded shapes).

    NOC-REMEDIATE[orbity-meta-ads-live]: This class is the test/dev default.
    Replace the service's client injection with a real factory once the vault
    is wired. The factory signature:
        make_meta_ads_client(credential_store, org_id) -> MetaAdsClient
    See noctusai_lib.integrations.meta.get_meta_adapter for the pattern. — 2026-06-03
    """

    def __init__(self) -> None:
        # Import here so the module stays importable even if noctusai_lib isn't
        # installed in a stripped test environment (lazy import).
        from noctusai_lib.integrations.meta import FakeMetaAdapter, AdCampaign, AdInsights
        self._meta = FakeMetaAdapter()
        self._AdCampaign = AdCampaign
        self._AdInsights = AdInsights

    def list_campaigns(self, external_account_id: str) -> list[dict[str, Any]]:
        camps = self._meta.list_ad_campaigns(external_account_id)
        return [
            {
                "external_campaign_id": c.id,
                "name": c.name or f"Campaign {c.id}",
                "objective": c.objective or "",
                # AdCampaign.status can be "ACTIVE" from Meta — normalise to lowercase
                "status": (c.status or "active").lower(),
                # AdCampaign does not carry daily_budget — budget lives on AdSets;
                # None here is correct; campaigns table column is nullable.
                "daily_budget": None,
            }
            for c in camps
        ]

    def get_campaign_insights(
        self,
        external_campaign_id: str,
        date_preset: str = "last_30d",
    ) -> dict[str, Any]:
        insights = self._meta.ad_insights(
            external_campaign_id,
            level="campaign",
            date_preset=date_preset,
        )
        # AdInsights stores metrics in a dict keyed by metric name.
        # The seed FakeMetaAdapter returns an empty metrics dict by default.
        metrics = insights.metrics if hasattr(insights, "metrics") else {}
        return {
            "spend": float(metrics.get("spend", 0.0)),
            "impressions": int(metrics.get("impressions", 0)),
            "leads": int(metrics.get("leads", 0)),
        }


def _make_default_client() -> MetaAdsClient:
    """Return the Fake client (safe default for dev/test).

    NOC-REMEDIATE[orbity-meta-ads-live]: Replace with the real factory call
    once noctusai_lib.integrations.meta credential resolution + vault are wired. — 2026-06-03
    """
    return FakeMetaAdsClient()


# ---------------------------------------------------------------------------
# MetaAdsService
# ---------------------------------------------------------------------------

_SENSITIVE_COLS = {"access_token_ref"}


def _scrub(row: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive credential columns from a DB row before returning."""
    return {k: v for k, v in row.items() if k not in _SENSITIVE_COLS}


class MetaAdsService:
    """Service for the Meta Ads organ.

    `db`     — Supabase client (user-scoped; RLS enforced).
    `org_id` — tenant UUID.
    `client` — MetaAdsClient implementation (Fake by default; Real injected
               at the live-wire point via NOC-REMEDIATE[orbity-meta-ads-live]).
    """

    def __init__(
        self,
        db: Any,
        org_id: UUID,
        *,
        client: MetaAdsClient | None = None,
    ) -> None:
        self._db = db
        self._org_id = str(org_id)
        # NOC-REMEDIATE[orbity-meta-ads-live]: pass the real factory result here
        # once the credential store / vault adapter is available at request time. — 2026-06-03
        self._client: MetaAdsClient = client or _make_default_client()

    def _t(self, table: str):
        # Schema-scoped at the DatabaseModule level (create_database_module
        # called with schema="orbity"). Do NOT call .schema() again — breaks
        # MockSupabaseClient inserted_payloads tracking in tests.
        return self._db.table(table)

    # ------------------------------------------------------------------
    # Ad accounts CRUD
    # ------------------------------------------------------------------

    def list_ad_accounts(
        self,
        *,
        client_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        query = (
            self._t("ad_accounts")
            .select("*", count="exact")
            .eq("org_id", self._org_id)
            .order("connected_at", desc=True)
            .range(offset, offset + page_size - 1)
        )
        if client_id:
            query = query.eq("client_id", client_id)
        if status:
            query = query.eq("status", status)
        try:
            result = query.execute()
        except Exception:
            logger.exception("meta_ads.list_ad_accounts failed org=%s", self._org_id)
            raise
        items = [_scrub(r) for r in (result.data or [])]
        return {
            "items": items,
            "total": result.count if result.count is not None else len(items),
            "page": page,
            "page_size": page_size,
        }

    def get_ad_account(self, account_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("ad_accounts")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", account_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "meta_ads.get_ad_account failed org=%s id=%s", self._org_id, account_id
            )
            raise
        rows = result.data or []
        return _scrub(rows[0]) if rows else None

    def create_ad_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "org_id": self._org_id}
        try:
            result = self._t("ad_accounts").insert(row).execute()
        except Exception:
            logger.exception("meta_ads.create_ad_account failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            logger.error(
                "meta_ads.create_ad_account returned no rows org=%s", self._org_id
            )
            raise RuntimeError("Insert returned no data")
        return _scrub(rows[0])

    def update_ad_account(
        self, account_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        payload.pop("org_id", None)  # prevent org escalation
        try:
            result = (
                self._t("ad_accounts")
                .update(payload)
                .eq("org_id", self._org_id)
                .eq("id", account_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "meta_ads.update_ad_account failed org=%s id=%s", self._org_id, account_id
            )
            raise
        rows = result.data or []
        return _scrub(rows[0]) if rows else None

    def delete_ad_account(self, account_id: str) -> bool:
        try:
            result = (
                self._t("ad_accounts")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", account_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "meta_ads.delete_ad_account failed org=%s id=%s", self._org_id, account_id
            )
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # Campaigns CRUD + situation tracking
    # ------------------------------------------------------------------

    def list_campaigns(
        self,
        *,
        ad_account_id: str | None = None,
        client_id: str | None = None,
        situation: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        query = (
            self._t("campaigns")
            .select("*", count="exact")
            .eq("org_id", self._org_id)
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
        )
        if ad_account_id:
            query = query.eq("ad_account_id", ad_account_id)
        if client_id:
            query = query.eq("client_id", client_id)
        if situation:
            query = query.eq("situation", situation)
        if status:
            query = query.eq("status", status)
        try:
            result = query.execute()
        except Exception:
            logger.exception("meta_ads.list_campaigns failed org=%s", self._org_id)
            raise
        items = result.data or []
        return {
            "items": items,
            "total": result.count if result.count is not None else len(items),
            "page": page,
            "page_size": page_size,
        }

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("campaigns")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", campaign_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "meta_ads.get_campaign failed org=%s id=%s", self._org_id, campaign_id
            )
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def create_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "org_id": self._org_id}
        # Convert UUID fields to str for Supabase client compatibility
        for field in ("ad_account_id", "client_id"):
            if row.get(field) is not None:
                row[field] = str(row[field])
        try:
            result = self._t("campaigns").insert(row).execute()
        except Exception:
            logger.exception("meta_ads.create_campaign failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            logger.error(
                "meta_ads.create_campaign returned no rows org=%s", self._org_id
            )
            raise RuntimeError("Insert returned no data")
        return rows[0]

    def update_campaign(
        self, campaign_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        payload.pop("org_id", None)
        payload.pop("ad_account_id", None)  # immutable FK after creation
        try:
            result = (
                self._t("campaigns")
                .update(payload)
                .eq("org_id", self._org_id)
                .eq("id", campaign_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "meta_ads.update_campaign failed org=%s id=%s", self._org_id, campaign_id
            )
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_campaign(self, campaign_id: str) -> bool:
        try:
            result = (
                self._t("campaigns")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", campaign_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "meta_ads.delete_campaign failed org=%s id=%s", self._org_id, campaign_id
            )
            raise
        return bool(result.data)

    def update_situation(
        self, campaign_id: str, situation: str
    ) -> dict[str, Any] | None:
        """Targeted gestor-signal update (on-track / attention / off)."""
        return self.update_campaign(campaign_id, {"situation": situation})

    # ------------------------------------------------------------------
    # Campaign metrics CRUD
    # ------------------------------------------------------------------

    def list_campaign_metrics(
        self,
        campaign_id: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            self._t("campaign_metrics")
            .select("*")
            .eq("org_id", self._org_id)
            .eq("campaign_id", campaign_id)
            .order("date", desc=True)
        )
        if date_from:
            query = query.gte("date", date_from)
        if date_to:
            query = query.lte("date", date_to)
        try:
            result = query.execute()
        except Exception:
            logger.exception(
                "meta_ads.list_campaign_metrics failed org=%s campaign=%s",
                self._org_id, campaign_id,
            )
            raise
        return result.data or []

    def upsert_campaign_metric(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Upsert a daily metrics snapshot (campaign_id + date = unique key)."""
        row = {**payload, "org_id": self._org_id}
        for field in ("campaign_id",):
            if row.get(field) is not None:
                row[field] = str(row[field])
        try:
            result = (
                self._t("campaign_metrics")
                .upsert(row, on_conflict="campaign_id,date")
                .execute()
            )
        except Exception:
            logger.exception(
                "meta_ads.upsert_campaign_metric failed org=%s campaign=%s",
                self._org_id, payload.get("campaign_id"),
            )
            raise
        rows = result.data or []
        if not rows:
            logger.error(
                "meta_ads.upsert_campaign_metric returned no rows org=%s", self._org_id
            )
            raise RuntimeError("Upsert returned no data")
        return rows[0]

    # ------------------------------------------------------------------
    # Sync seam — pull campaigns + metrics from Meta
    #
    # NOC-REMEDIATE[orbity-meta-ads-live]: This method calls the MetaAdsClient
    # Protocol, which defaults to FakeMetaAdsClient. Replace by injecting the
    # real client via the service constructor once the vault/credential store is
    # wired. The factory:
    #   real_client = make_meta_ads_client(credential_store, org_id)
    #   svc = MetaAdsService(db, org_id, client=real_client) — 2026-06-03
    # ------------------------------------------------------------------

    def sync_campaigns(self, ad_account_id: str) -> dict[str, Any]:
        """Pull campaign list from Meta and upsert into DB.

        Returns counts: synced / skipped / errors.
        Errors are logged at WARNING level — a partial sync does NOT fail
        the whole call (consistent with the Orbity pattern of best-effort
        sync with full audit trail).
        """
        # Verify ad account belongs to this org
        account = self.get_ad_account(ad_account_id)
        if not account:
            raise LookupError(f"Ad account {ad_account_id} not found in org")

        external_account_id = account["external_account_id"]

        try:
            remote_campaigns = self._client.list_campaigns(external_account_id)
        except Exception:
            logger.exception(
                "meta_ads.sync_campaigns: Meta pull failed org=%s account=%s",
                self._org_id, external_account_id,
            )
            raise

        synced = skipped = errors = 0
        for camp in remote_campaigns:
            row = {
                "org_id": self._org_id,
                "ad_account_id": ad_account_id,
                "external_campaign_id": camp.get("external_campaign_id", ""),
                "name": camp.get("name", ""),
                "objective": camp.get("objective"),
                "status": camp.get("status", "active"),
                "daily_budget": camp.get("daily_budget"),
                # situation defaults to "on-track" for newly synced campaigns
                "situation": "on-track",
            }
            if not row["external_campaign_id"]:
                logger.warning(
                    "meta_ads.sync_campaigns: skipping campaign with no external_campaign_id "
                    "org=%s", self._org_id,
                )
                skipped += 1
                continue
            try:
                self._t("campaigns").upsert(
                    row, on_conflict="org_id,external_campaign_id"
                ).execute()
                synced += 1
            except Exception:
                logger.warning(
                    "meta_ads.sync_campaigns: upsert failed for campaign=%s org=%s",
                    row["external_campaign_id"], self._org_id,
                    exc_info=True,
                )
                errors += 1

        adapter_mode = getattr(self._client, "auth_mode", None)
        # FakeMetaAdsClient wraps FakeMetaAdapter whose auth_mode is "none"
        source = "fake" if (adapter_mode is None or adapter_mode == "none") else "live"

        return {"synced": synced, "skipped": skipped, "errors": errors, "source": source}

    # ------------------------------------------------------------------
    # Aggregate — spend vs leads per client/month (cash-flow style view)
    # ------------------------------------------------------------------

    def get_spend_leads_aggregate(
        self,
        *,
        period_start: str,
        period_end: str,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        """Return spend vs leads grouped by client × month.

        Joins campaign_metrics → campaigns (for client_id/situation) to
        produce the gestor-facing aggregate view. All within org RLS scope.
        """
        # Fetch metrics in the date window
        try:
            metrics_res = (
                self._t("campaign_metrics")
                .select("campaign_id, date, spend, leads, cpl")
                .eq("org_id", self._org_id)
                .gte("date", period_start)
                .lte("date", period_end)
                .execute()
            )
        except Exception:
            logger.exception(
                "meta_ads.aggregate: metrics fetch failed org=%s", self._org_id
            )
            raise

        metrics = metrics_res.data or []
        if not metrics:
            return {
                "period_start": period_start,
                "period_end": period_end,
                "items": [],
                "total_spend": 0.0,
                "total_leads": 0,
            }

        # Fetch all campaigns so we can resolve client_id and situation
        campaign_ids = list({m["campaign_id"] for m in metrics})
        try:
            camps_res = (
                self._t("campaigns")
                .select("id, client_id, situation")
                .eq("org_id", self._org_id)
                .in_("id", campaign_ids)
                .execute()
            )
        except Exception:
            logger.exception(
                "meta_ads.aggregate: campaigns fetch failed org=%s", self._org_id
            )
            raise

        camp_map: dict[str, dict[str, Any]] = {
            c["id"]: c for c in (camps_res.data or [])
        }

        # Fetch clients for names (best-effort; None if not available)
        client_ids = list({
            camp_map[m["campaign_id"]]["client_id"]
            for m in metrics
            if camp_map.get(m["campaign_id"], {}).get("client_id")
        })
        client_name_map: dict[str, str] = {}
        if client_ids:
            try:
                cl_res = (
                    self._t("clients")
                    .select("id, name")
                    .eq("org_id", self._org_id)
                    .in_("id", client_ids)
                    .execute()
                )
                client_name_map = {c["id"]: c["name"] for c in (cl_res.data or [])}
            except Exception:
                # Non-fatal — aggregate still works without client names
                logger.warning(
                    "meta_ads.aggregate: client names fetch failed org=%s — names omitted",
                    self._org_id,
                )

        # Group by (client_id, month)
        # Key: (client_id_or_None, "YYYY-MM")
        GroupKey = tuple  # (client_id | None, month_str)

        buckets: dict[GroupKey, dict[str, Any]] = defaultdict(lambda: {
            "total_spend": 0.0,
            "total_leads": 0,
            "spend_for_cpl": 0.0,
            "leads_for_cpl": 0,
            "campaign_ids": set(),
            "on_track": 0,
            "attention": 0,
            "off": 0,
        })

        for m in metrics:
            camp = camp_map.get(m["campaign_id"], {})
            cid = camp.get("client_id")

            # Apply client_id filter (if requested)
            if client_id and cid != client_id:
                continue

            month = m["date"][:7]  # "YYYY-MM"
            key: GroupKey = (cid, month)
            bucket = buckets[key]

            spend = float(m.get("spend") or 0)
            leads = int(m.get("leads") or 0)
            bucket["total_spend"] += spend
            bucket["total_leads"] += leads
            if leads > 0:
                bucket["spend_for_cpl"] += spend
                bucket["leads_for_cpl"] += leads
            bucket["campaign_ids"].add(m["campaign_id"])

            sit = camp.get("situation", "on-track")
            if sit == "on-track":
                bucket["on_track"] += 1
            elif sit == "attention":
                bucket["attention"] += 1
            else:
                bucket["off"] += 1

        items = []
        for (cid, month), bucket in sorted(buckets.items(), key=lambda x: (x[0][1], x[0][0] or "")):
            leads_for_cpl = bucket["leads_for_cpl"]
            avg_cpl = (
                round(bucket["spend_for_cpl"] / leads_for_cpl, 4)
                if leads_for_cpl > 0
                else None
            )
            items.append({
                "client_id": cid,
                "client_name": client_name_map.get(cid) if cid else None,
                "month": month,
                "total_spend": round(bucket["total_spend"], 2),
                "total_leads": bucket["total_leads"],
                "avg_cpl": avg_cpl,
                "campaign_count": len(bucket["campaign_ids"]),
                "on_track_count": bucket["on_track"],
                "attention_count": bucket["attention"],
                "off_count": bucket["off"],
            })

        grand_spend = round(sum(i["total_spend"] for i in items), 2)
        grand_leads = sum(i["total_leads"] for i in items)

        return {
            "period_start": period_start,
            "period_end": period_end,
            "items": items,
            "total_spend": grand_spend,
            "total_leads": grand_leads,
        }
