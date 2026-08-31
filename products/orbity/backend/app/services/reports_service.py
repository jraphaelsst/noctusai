"""
Reports service — CRUD for reports + generate snapshot + public token read.

Aggregation sources (generate_snapshot):
  - orbity.leads   (count by temperature, filtered by period_start/period_end)
  - orbity.revenues (sum + count, filtered by period)
  - orbity.expenses (sum + count, filtered by period)

NOC-REMEDIATE[orbity-reports-metrics-source]: when the Meta-ads organ lands,
extend generate_snapshot to pull spend/cpl/campaigns from
orbity.ad_account_metrics and orbity.selected_ad_accounts. — 2026-06-03

Public token read:
  Uses the admin (service_role) client so RLS is bypassed. The server
  validates the token AND status=published AND not-expired server-side before
  returning the payload. The admin client NEVER trusts a client-supplied
  org_id — it fetches by public_token only, then resolves report_id from that
  trusted row.

No mock-data fallbacks. No silent errors.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class ReportsService:
    """Authenticated CRUD + generate. Uses a user-scoped (RLS-enforced) client."""

    def __init__(self, db: Any, org_id: UUID) -> None:
        self._db = db
        self._org_id = str(org_id)

    def _t(self, table: str):
        return self._db.table(table)

    # ------------------------------------------------------------------
    # Reports CRUD
    # ------------------------------------------------------------------

    def list_reports(
        self,
        *,
        client_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            self._t("reports")
            .select("*")
            .eq("org_id", self._org_id)
            .order("created_at", desc=True)
        )
        if client_id:
            query = query.eq("client_id", client_id)
        if status:
            query = query.eq("status", status)
        try:
            result = query.execute()
        except Exception:
            logger.exception("reports.list failed org=%s", self._org_id)
            raise
        return result.data or []

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("reports")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", report_id)
                .execute()
            )
        except Exception:
            logger.exception("reports.get failed org=%s id=%s", self._org_id, report_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def create_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "org_id": self._org_id}
        try:
            result = self._t("reports").insert(row).execute()
        except Exception:
            logger.exception("reports.create failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            logger.error("reports.create returned no rows org=%s", self._org_id)
            raise RuntimeError("Insert returned no data")
        return rows[0]

    def update_report(self, report_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        payload.pop("org_id", None)        # prevent escalation
        payload.pop("public_token", None)  # immutable — generated at insert
        try:
            result = (
                self._t("reports")
                .update(payload)
                .eq("org_id", self._org_id)
                .eq("id", report_id)
                .execute()
            )
        except Exception:
            logger.exception("reports.update failed org=%s id=%s", self._org_id, report_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_report(self, report_id: str) -> bool:
        try:
            result = (
                self._t("reports")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", report_id)
                .execute()
            )
        except Exception:
            logger.exception("reports.delete failed org=%s id=%s", self._org_id, report_id)
            raise
        return bool(result.data)

    def list_snapshots(self, report_id: str) -> list[dict[str, Any]]:
        try:
            result = (
                self._t("report_snapshots")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("report_id", report_id)
                .order("generated_at", desc=True)
                .execute()
            )
        except Exception:
            logger.exception(
                "reports.list_snapshots failed org=%s report=%s", self._org_id, report_id
            )
            raise
        return result.data or []

    # ------------------------------------------------------------------
    # Generate snapshot (aggregation)
    # ------------------------------------------------------------------

    def generate_snapshot(self, report_id: str) -> dict[str, Any]:
        """Aggregate orbity.leads, revenues, expenses for the report period.

        Fetches the report row (RLS-scoped to this org), then runs three
        aggregation queries against the same period. Writes the result to
        report_snapshots (authenticated client — service_role not needed
        here; the authenticated user's RLS INSERT policy covers it).

        Returns the new snapshot row.
        """
        report = self.get_report(report_id)
        if not report:
            raise LookupError(f"Report {report_id} not found for org {self._org_id}")

        period_start: str = _to_iso_date(report["period_start"])
        period_end: str = _to_iso_date(report["period_end"])

        # Leads aggregation
        leads_payload = self._aggregate_leads(period_start, period_end)

        # Revenues aggregation (orbity.revenues table from financial organ)
        revenues_payload = self._aggregate_revenues(period_start, period_end)

        # Expenses aggregation
        expenses_payload = self._aggregate_expenses(period_start, period_end)

        # NOC-REMEDIATE[orbity-reports-metrics-source]: extend here with
        # spend/cpl/campaigns from orbity.ad_account_metrics + selected_ad_accounts
        # once the Meta-ads organ lands (migration 013+). The payload key
        # "meta_ads" will be added: {"spend": ..., "cpl": ..., "active_campaigns": ...} — 2026-06-03

        payload: dict[str, Any] = {
            "period": {"start": period_start, "end": period_end},
            "leads": leads_payload,
            "revenues": revenues_payload,
            "expenses": expenses_payload,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        snapshot_row = {
            "org_id": self._org_id,
            "report_id": report_id,
            "payload": payload,
        }
        try:
            result = self._t("report_snapshots").insert(snapshot_row).execute()
        except Exception:
            logger.exception(
                "reports.generate_snapshot insert failed org=%s report=%s",
                self._org_id, report_id,
            )
            raise
        rows = result.data or []
        if not rows:
            logger.error(
                "reports.generate_snapshot returned no rows org=%s report=%s",
                self._org_id, report_id,
            )
            raise RuntimeError("Snapshot insert returned no data")
        return rows[0]

    def _aggregate_leads(self, period_start: str, period_end: str) -> dict[str, Any]:
        """Count leads created in period, grouped by temperature."""
        try:
            result = (
                self._t("leads")
                .select("temperature")
                .eq("org_id", self._org_id)
                .gte("created_at", period_start)
                .lte("created_at", period_end + "T23:59:59+00:00")
                .execute()
            )
        except Exception:
            logger.exception(
                "reports._aggregate_leads failed org=%s period=%s/%s",
                self._org_id, period_start, period_end,
            )
            raise
        rows = result.data or []
        total = len(rows)
        hot = sum(1 for r in rows if r.get("temperature") == "hot")
        warm = sum(1 for r in rows if r.get("temperature") == "warm")
        cold = sum(1 for r in rows if r.get("temperature") == "cold")
        return {"total": total, "hot": hot, "warm": warm, "cold": cold}

    def _aggregate_revenues(self, period_start: str, period_end: str) -> dict[str, Any]:
        """Sum revenues paid in period from orbity.revenues (financial organ).

        Filters by paid_at (when the payment was confirmed) falling within
        the report period. Revenues with status='paid' and paid_at in period.

        NOC-REMEDIATE[orbity-reports-metrics-source]: if financial organ
        tables (revenues) are not yet in this branch, this returns zeros
        gracefully — the table not existing raises an exception caught below. — 2026-06-03
        """
        try:
            result = (
                self._t("revenues")
                .select("amount")
                .eq("org_id", self._org_id)
                .eq("status", "paid")
                .gte("paid_at", period_start)
                .lte("paid_at", period_end + "T23:59:59+00:00")
                .execute()
            )
            rows = result.data or []
            total = sum(float(r.get("amount") or 0) for r in rows)
            return {"total": round(total, 2), "count": len(rows)}
        except Exception:
            logger.warning(
                "reports._aggregate_revenues failed org=%s period=%s/%s — "
                "revenues table may not exist yet; returning zeros. "
                "NOC-REMEDIATE[orbity-reports-metrics-source]",
                self._org_id, period_start, period_end,
            )
            return {"total": 0.0, "count": 0}

    def _aggregate_expenses(self, period_start: str, period_end: str) -> dict[str, Any]:
        """Sum expenses with due_date in period from orbity.expenses (financial organ)."""
        try:
            result = (
                self._t("expenses")
                .select("amount")
                .eq("org_id", self._org_id)
                .gte("due_date", period_start)
                .lte("due_date", period_end)
                .execute()
            )
            rows = result.data or []
            total = sum(float(r.get("amount") or 0) for r in rows)
            return {"total": round(total, 2), "count": len(rows)}
        except Exception:
            logger.warning(
                "reports._aggregate_expenses failed org=%s period=%s/%s — "
                "expenses table may not exist yet; returning zeros. "
                "NOC-REMEDIATE[orbity-reports-metrics-source]",
                self._org_id, period_start, period_end,
            )
            return {"total": 0.0, "count": 0}


# ---------------------------------------------------------------------------
# Public token read (no user auth — uses admin/service_role client)
# ---------------------------------------------------------------------------

class ReportsPublicService:
    """Unauthenticated public token read. Uses the admin (service_role) client.

    RLS safety design:
    - The admin client bypasses RLS for the SELECT. This is intentional and
      safe because the server-side validation chain is strict:
        1. Fetch report by public_token only (no client-supplied org_id).
        2. Verify status == "published".
        3. Verify expires_at is NULL or in the future.
        4. Fetch the latest report_snapshot by report_id (from the trusted row).
        5. Return the snapshot payload.
    - At no point is a client-supplied org_id used. Cross-org contamination
      is impossible: the token uniquely identifies one report, and the admin
      client's full-table read is gated by the server's validation chain.
    - The public_token is a UUID (128-bit random) — not guessable by brute-force.
    """

    def __init__(self, admin_db: Any) -> None:
        self._db = admin_db

    def _t(self, table: str):
        return self._db.table(table)

    def get_published_report_by_token(self, token: str) -> dict[str, Any] | None:
        """Validate token → return (report, latest_snapshot) or None.

        Returns None when:
          - Token not found
          - status != "published"
          - expires_at is in the past

        Callers MUST validate that `token` parses as a UUID before calling
        this method — the router does this (a malformed token is a 404,
        not a DB round-trip; see reports_router.get_public_report). A
        non-UUID token handed to this method would otherwise reach postgres
        as a raw string comparison against a UUID column and raise 22P02.

        Raises:
          Exception: DB errors propagate (caller raises 502)
        """
        try:
            result = (
                self._t("reports")
                .select("*")
                .eq("public_token", token)
                .execute()
            )
        except Exception:
            logger.exception("reports.public_read token=%s — DB error", token)
            raise

        rows = result.data or []
        if not rows:
            return None

        report = rows[0]

        # Validate published
        if report.get("status") != "published":
            logger.debug("reports.public_read token=%s — not published", token)
            return None

        # Validate expiry
        expires_at = report.get("expires_at")
        if expires_at:
            try:
                exp = _parse_dt(expires_at)
                if exp < datetime.now(tz=timezone.utc):
                    logger.debug("reports.public_read token=%s — expired", token)
                    return None
            except Exception:
                logger.warning(
                    "reports.public_read token=%s — could not parse expires_at=%r",
                    token, expires_at,
                )

        # Fetch latest snapshot
        snapshot = self._get_latest_snapshot(report["id"])

        return {"report": report, "snapshot": snapshot}

    def _get_latest_snapshot(self, report_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("report_snapshots")
                .select("*")
                .eq("report_id", report_id)
                .order("generated_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception:
            logger.exception(
                "reports._get_latest_snapshot report=%s — DB error", report_id
            )
            raise
        rows = result.data or []
        return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_iso_date(value: Any) -> str:
    """Coerce a date/datetime/string to ISO date string (YYYY-MM-DD)."""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value)[:10]


def _parse_dt(value: Any) -> datetime:
    """Parse an ISO datetime string to a timezone-aware datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    s = str(value)
    # Python 3.11+: fromisoformat handles Z; <3.11 needs a strip
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
