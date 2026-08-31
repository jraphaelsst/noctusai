"""
Financial service — contracts, expenses, revenues CRUD + monthly cash-flow summary.

Tenancy: every write stamps org_id; every read filters by org_id.
No silent errors: every except logs at the right level and re-raises.
No mock-data fallbacks: callers receive explicit empty states / None.

Data-access pattern mirrors crm_service exactly:
  - _t(table) → self._db.table(table) (schema already pinned at DB module init)
  - org_id stripped from PATCH payloads to prevent escalation
  - Supabase client is the sole IO seam (MockSupabaseClient in tests)

NOC-REMEDIATE[orbity-finance-fiscal]
  Conexa/Asaas gateway integration seam: when the fiscal adapter lands,
  wire it at revenues.status → 'gateway_pending' + external_id column.
  See KB § ABSORPTIONS/orbity/09-DEEPDIVE-FINANCIAL-MANAGEMENT.md §5 for
  the dunning engine shape, billing_type enum, and gateway-fee netting. — 2026-06-03
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class FinancialService:
    def __init__(self, db: Any, org_id: UUID) -> None:
        self._db = db
        self._org_id = str(org_id)

    def _t(self, table: str):
        # Schema already pinned to "orbity" by create_database_module(settings,
        # schema="orbity"). Calling .schema() again would break
        # MockSupabaseClient's inserted_payloads tracking in tests.
        return self._db.table(table)

    # ------------------------------------------------------------------
    # contracts CRUD
    # ------------------------------------------------------------------

    def list_contracts(
        self,
        *,
        status: str | None = None,
        client_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        query = (
            self._t("contracts")
            .select("*", count="exact")
            .eq("org_id", self._org_id)
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
        )
        if status:
            query = query.eq("status", status)
        if client_id:
            query = query.eq("client_id", client_id)
        try:
            result = query.execute()
        except Exception:
            logger.exception("financial.list_contracts failed org=%s", self._org_id)
            raise
        return {
            "items": result.data or [],
            "total": result.count if result.count is not None else len(result.data or []),
            "page": page,
            "page_size": page_size,
        }

    def get_contract(self, contract_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("contracts")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", contract_id)
                .execute()
            )
        except Exception:
            logger.exception("financial.get_contract failed org=%s id=%s", self._org_id, contract_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def create_contract(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "org_id": self._org_id}
        try:
            result = self._t("contracts").insert(row).execute()
        except Exception:
            logger.exception("financial.create_contract failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            logger.error("financial.create_contract returned no rows org=%s", self._org_id)
            raise RuntimeError("Insert returned no data")
        return rows[0]

    def update_contract(self, contract_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        payload.pop("org_id", None)  # prevent escalation
        try:
            result = (
                self._t("contracts")
                .update(payload)
                .eq("org_id", self._org_id)
                .eq("id", contract_id)
                .execute()
            )
        except Exception:
            logger.exception("financial.update_contract failed org=%s id=%s", self._org_id, contract_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_contract(self, contract_id: str) -> bool:
        try:
            result = (
                self._t("contracts")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", contract_id)
                .execute()
            )
        except Exception:
            logger.exception("financial.delete_contract failed org=%s id=%s", self._org_id, contract_id)
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # expenses CRUD
    # ------------------------------------------------------------------

    def list_expenses(
        self,
        *,
        paid: bool | None = None,
        recurrence: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        query = (
            self._t("expenses")
            .select("*", count="exact")
            .eq("org_id", self._org_id)
            .order("due_date", desc=True)
            .range(offset, offset + page_size - 1)
        )
        if paid is not None:
            query = query.eq("paid", paid)
        if recurrence:
            query = query.eq("recurrence", recurrence)
        try:
            result = query.execute()
        except Exception:
            logger.exception("financial.list_expenses failed org=%s", self._org_id)
            raise
        return {
            "items": result.data or [],
            "total": result.count if result.count is not None else len(result.data or []),
            "page": page,
            "page_size": page_size,
        }

    def get_expense(self, expense_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("expenses")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", expense_id)
                .execute()
            )
        except Exception:
            logger.exception("financial.get_expense failed org=%s id=%s", self._org_id, expense_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def create_expense(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "org_id": self._org_id}
        try:
            result = self._t("expenses").insert(row).execute()
        except Exception:
            logger.exception("financial.create_expense failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            logger.error("financial.create_expense returned no rows org=%s", self._org_id)
            raise RuntimeError("Insert returned no data")
        return rows[0]

    def update_expense(self, expense_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        payload.pop("org_id", None)  # prevent escalation
        try:
            result = (
                self._t("expenses")
                .update(payload)
                .eq("org_id", self._org_id)
                .eq("id", expense_id)
                .execute()
            )
        except Exception:
            logger.exception("financial.update_expense failed org=%s id=%s", self._org_id, expense_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_expense(self, expense_id: str) -> bool:
        try:
            result = (
                self._t("expenses")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", expense_id)
                .execute()
            )
        except Exception:
            logger.exception("financial.delete_expense failed org=%s id=%s", self._org_id, expense_id)
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # revenues CRUD
    # ------------------------------------------------------------------

    def list_revenues(
        self,
        *,
        status: str | None = None,
        client_id: str | None = None,
        reference_month: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        query = (
            self._t("revenues")
            .select("*", count="exact")
            .eq("org_id", self._org_id)
            .order("reference_month", desc=True)
            .range(offset, offset + page_size - 1)
        )
        if status:
            query = query.eq("status", status)
        if client_id:
            query = query.eq("client_id", client_id)
        if reference_month:
            query = query.eq("reference_month", reference_month)
        try:
            result = query.execute()
        except Exception:
            logger.exception("financial.list_revenues failed org=%s", self._org_id)
            raise
        return {
            "items": result.data or [],
            "total": result.count if result.count is not None else len(result.data or []),
            "page": page,
            "page_size": page_size,
        }

    def get_revenue(self, revenue_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("revenues")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", revenue_id)
                .execute()
            )
        except Exception:
            logger.exception("financial.get_revenue failed org=%s id=%s", self._org_id, revenue_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def create_revenue(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "org_id": self._org_id}
        try:
            result = self._t("revenues").insert(row).execute()
        except Exception:
            logger.exception("financial.create_revenue failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            logger.error("financial.create_revenue returned no rows org=%s", self._org_id)
            raise RuntimeError("Insert returned no data")
        return rows[0]

    def update_revenue(self, revenue_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        payload.pop("org_id", None)  # prevent escalation
        try:
            result = (
                self._t("revenues")
                .update(payload)
                .eq("org_id", self._org_id)
                .eq("id", revenue_id)
                .execute()
            )
        except Exception:
            logger.exception("financial.update_revenue failed org=%s id=%s", self._org_id, revenue_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_revenue(self, revenue_id: str) -> bool:
        try:
            result = (
                self._t("revenues")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", revenue_id)
                .execute()
            )
        except Exception:
            logger.exception("financial.delete_revenue failed org=%s id=%s", self._org_id, revenue_id)
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # Monthly cash-flow summary
    # ------------------------------------------------------------------

    def monthly_cash_flow(self, reference_month: str) -> dict[str, Any]:
        """Cash-basis aggregate for a single calendar month.

        - paid_revenues:  Σ revenues.amount WHERE status='paid' AND reference_month=X
        - paid_expenses:  Σ expenses.amount WHERE paid=true AND due_date within month
        - pending/overdue revenues: additional AR aging buckets
        - net: paid_revenues − paid_expenses

        Note: expenses are matched by due_date within the ISO-month prefix
        (YYYY-MM) of reference_month, since expenses don't carry a reference_month
        column — this mirrors the absorbed source's cash-basis snapshot logic.
        """
        # Derive the month prefix (YYYY-MM) for due_date range filtering
        try:
            # reference_month is expected as YYYY-MM-DD (first of month)
            month_prefix = reference_month[:7]  # "YYYY-MM"
            month_start = f"{month_prefix}-01"
            # Compute next month start for range (exclusive upper bound)
            year, month = int(month_prefix[:4]), int(month_prefix[5:7])
            if month == 12:
                next_month_start = f"{year + 1}-01-01"
            else:
                next_month_start = f"{year}-{month + 1:02d}-01"
        except (ValueError, IndexError):
            logger.error(
                "financial.monthly_cash_flow: invalid reference_month=%r org=%s",
                reference_month, self._org_id,
            )
            raise ValueError(f"Invalid reference_month: {reference_month!r}")

        # --- revenues ---
        try:
            rev_result = (
                self._t("revenues")
                .select("amount, status")
                .eq("org_id", self._org_id)
                .eq("reference_month", month_start)
                .execute()
            )
        except Exception:
            logger.exception(
                "financial.monthly_cash_flow: revenues query failed org=%s month=%s",
                self._org_id, reference_month,
            )
            raise

        # --- expenses ---
        try:
            exp_result = (
                self._t("expenses")
                .select("amount, paid")
                .eq("org_id", self._org_id)
                .gte("due_date", month_start)
                .lt("due_date", next_month_start)
                .execute()
            )
        except Exception:
            logger.exception(
                "financial.monthly_cash_flow: expenses query failed org=%s month=%s",
                self._org_id, reference_month,
            )
            raise

        revenues = rev_result.data or []
        expenses = exp_result.data or []

        paid_revenues  = sum(float(r["amount"]) for r in revenues if r.get("status") == "paid")
        pending_rev    = sum(float(r["amount"]) for r in revenues if r.get("status") == "pending")
        overdue_rev    = sum(float(r["amount"]) for r in revenues if r.get("status") == "overdue")
        paid_expenses  = sum(float(e["amount"]) for e in expenses if e.get("paid"))

        return {
            "reference_month":  month_start,
            "paid_revenues":    round(paid_revenues, 2),
            "paid_expenses":    round(paid_expenses, 2),
            "net":              round(paid_revenues - paid_expenses, 2),
            "pending_revenues": round(pending_rev, 2),
            "overdue_revenues": round(overdue_rev, 2),
        }
