"""
Tests for the Admin Financials Router.

Covers: global dashboard, list all wallets, set commission override,
list payouts, process payout, and auth/permission checks (platform_admin only).
"""
import pytest

SAMPLE_TRANSACTION = {
    "id": "tx-001",
    "gross_amount": "200.00",
    "platform_fee_amount": "20.00",
    "clinic_share_amount": "36.00",
    "therapist_share_amount": "144.00",
    "status": "captured",
}

SAMPLE_PAYOUT = {
    "id": "payout-001",
    "recipient_id": "therapist-001",
    "recipient_type": "therapist",
    "amount": "500.00",
    "net_amount": "490.00",
    "fee_amount": "10.00",
    "status": "pending",
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_WALLET = {
    "id": "wallet-001",
    "owner_id": "therapist-001",
    "owner_type": "therapist",
    "balance": "1000.00",
    "last_updated": "2026-04-01T10:00:00Z",
}

SAMPLE_COMMISSION_OVERRIDE = {
    "id": "override-001",
    "target_type": "clinic",
    "target_id": "clinic-001",
    "custom_commission_pct": 8.0,
}

SAMPLE_REFUND = {
    "id": "ref-001",
    "refund_amount": "50.00",
    "status": "pending",
}


class TestGlobalDashboard:
    """GET /api/admin/financials/"""

    def test_dashboard(self, admin_client):
        """Platform admin gets global financial dashboard."""
        admin_client._mock_supabase.set_table_data("transactions", [SAMPLE_TRANSACTION])
        admin_client._mock_supabase.set_table_data("payouts", [SAMPLE_PAYOUT])
        admin_client._mock_supabase.set_table_data("refund_requests", [SAMPLE_REFUND])
        resp = admin_client.get("/api/admin/financials/")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        data = body["data"]
        assert "transactions" in data
        assert "payouts" in data
        assert "refunds" in data

    def test_dashboard_therapist_forbidden(self, client):
        """Therapist cannot access admin dashboard."""
        resp = client.get("/api/admin/financials/")
        assert resp.status_code == 403

    def test_dashboard_patient_forbidden(self, patient_client):
        """Patient cannot access admin dashboard."""
        resp = patient_client.get("/api/admin/financials/")
        assert resp.status_code == 403

    def test_dashboard_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/admin/financials/")
        assert resp.status_code == 401


class TestListAllWallets:
    """GET /api/admin/financials/wallets"""

    def test_list_all_wallets(self, admin_client):
        """Admin lists all wallets."""
        admin_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        resp = admin_client.get("/api/admin/financials/wallets")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_list_wallets_with_filter(self, admin_client):
        """Filter by owner_type."""
        admin_client._mock_supabase.set_table_data("wallets", [SAMPLE_WALLET])
        resp = admin_client.get("/api/admin/financials/wallets?owner_type=therapist")
        assert resp.status_code == 200

    def test_list_wallets_therapist_forbidden(self, client):
        """Therapist cannot list all wallets."""
        resp = client.get("/api/admin/financials/wallets")
        assert resp.status_code == 403


class TestSetCommissionOverride:
    """POST /api/admin/financials/commissions"""

    def test_set_commission(self, admin_client):
        """Admin sets a commission override."""
        admin_client._mock_supabase.set_table_data(
            "platform_commission_overrides", [SAMPLE_COMMISSION_OVERRIDE]
        )
        resp = admin_client.post("/api/admin/financials/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": "8.0",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_set_commission_therapist_forbidden(self, client):
        """Therapist cannot set commission overrides."""
        resp = client.post("/api/admin/financials/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": "8.0",
        })
        assert resp.status_code == 403


class TestListPayouts:
    """GET /api/admin/financials/payouts"""

    def test_list_payouts(self, admin_client):
        """Admin lists all payouts."""
        admin_client._mock_supabase.set_table_data("payouts", [SAMPLE_PAYOUT])
        resp = admin_client.get("/api/admin/financials/payouts")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_payouts_with_status_filter(self, admin_client):
        """Filter by status."""
        admin_client._mock_supabase.set_table_data("payouts", [SAMPLE_PAYOUT])
        resp = admin_client.get("/api/admin/financials/payouts?status=pending")
        assert resp.status_code == 200

    def test_list_payouts_therapist_forbidden(self, client):
        """Therapist cannot list payouts."""
        resp = client.get("/api/admin/financials/payouts")
        assert resp.status_code == 403


class TestProcessPayout:
    """POST /api/admin/financials/payouts/:id/process"""

    def test_process_payout(self, admin_client):
        """Admin processes a pending payout."""
        admin_client._mock_supabase.set_table_data("payouts", [SAMPLE_PAYOUT])
        admin_client._mock_supabase.set_table_data("wallets", [])
        admin_client._mock_supabase.set_table_data("wallet_movements", [])
        resp = admin_client.post("/api/admin/financials/payouts/payout-001/process")
        assert resp.status_code == 200

    def test_process_payout_therapist_forbidden(self, client):
        """Therapist cannot process payouts."""
        resp = client.post("/api/admin/financials/payouts/payout-001/process")
        assert resp.status_code == 403

    def test_process_payout_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/admin/financials/payouts/payout-001/process")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Phase 2 regressions — summary, transactions, commissions GET/DELETE.
# ---------------------------------------------------------------------------


class TestFinancialSummary:
    """GET /api/admin/financials/summary"""

    def test_summary_aggregates(self, admin_client):
        # NOTE: MockSelectBuilder doesn't apply `.eq()` filters on reads
        # (only on UPDATE/DELETE). Seed only the captured rows the service
        # should consume — the production code's `.eq("status", "captured")`
        # is still on the wire and would filter against a real DB.
        admin_client._mock_supabase.set_table_data("transactions", [
            {"gross_amount": "200.00", "platform_fee_amount": "20.00", "status": "captured"},
            {"gross_amount": "100.00", "platform_fee_amount": "10.00", "status": "captured"},
        ])
        admin_client._mock_supabase.set_table_data("payouts", [
            {"amount": "150.00", "net_amount": "145.00", "status": "completed"},
            {"amount": "200.00", "net_amount": "0.00", "status": "pending"},
        ])
        resp = admin_client.get("/api/admin/financials/summary")
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["total_revenue"] == 300.0
        assert data["platform_fees"] == 30.0
        assert data["payouts_completed"] == 145.0
        assert data["payouts_pending"] == 200.0

    def test_summary_therapist_forbidden(self, client):
        resp = client.get("/api/admin/financials/summary")
        assert resp.status_code == 403

    def test_summary_no_auth(self, client):
        resp = client._tc.get("/api/admin/financials/summary")
        assert resp.status_code == 401


class TestListAllTransactions:
    """GET /api/admin/financials/transactions"""

    def test_list_transactions(self, admin_client):
        admin_client._mock_supabase.set_table_data("transactions", [SAMPLE_TRANSACTION])
        resp = admin_client.get("/api/admin/financials/transactions")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == "tx-001"

    def test_list_transactions_status_filter(self, admin_client):
        admin_client._mock_supabase.set_table_data("transactions", [])
        resp = admin_client.get("/api/admin/financials/transactions?status=captured")
        assert resp.status_code == 200

    def test_list_transactions_date_range(self, admin_client):
        admin_client._mock_supabase.set_table_data("transactions", [])
        resp = admin_client.get(
            "/api/admin/financials/transactions?date_start=2026-05-01&date_end=2026-05-31"
        )
        assert resp.status_code == 200

    def test_list_transactions_therapist_forbidden(self, client):
        resp = client.get("/api/admin/financials/transactions")
        assert resp.status_code == 403

    def test_list_transactions_no_auth(self, client):
        resp = client._tc.get("/api/admin/financials/transactions")
        assert resp.status_code == 401


class TestGetCommissionConfig:
    """GET /api/admin/financials/commissions"""

    def test_get_config_with_overrides(self, admin_client):
        admin_client._mock_supabase.set_table_data("platform_settings", [
            {"key": "global_commission_rate", "value": "12.5"},
        ])
        admin_client._mock_supabase.set_table_data(
            "platform_commission_overrides",
            [
                {"id": "ov-1", "target_type": "clinic", "target_id": "clinic-001",
                 "custom_commission_pct": 8.0, "created_at": "2026-05-01T00:00:00Z"},
                {"id": "ov-2", "target_type": "therapist", "target_id": "therapist-001",
                 "custom_commission_pct": 5.0, "created_at": "2026-05-02T00:00:00Z"},
            ],
        )
        admin_client._mock_supabase.set_table_data("clinics", [
            {"id": "clinic-001", "name": "Clínica Alpha"},
        ])
        resp = admin_client.get("/api/admin/financials/commissions")
        assert resp.status_code == 200
        body = resp.json()
        data = body["data"]
        assert data["global_rate_pct"] == 12.5
        assert len(data["overrides"]) == 2
        ids = {o["id"] for o in data["overrides"]}
        assert ids == {"ov-1", "ov-2"}
        clinic_row = next(o for o in data["overrides"] if o["entity_type"] == "clinic")
        assert clinic_row["entity_name"] == "Clínica Alpha"
        assert clinic_row["rate_pct"] == 8.0

    def test_get_config_default_when_setting_missing(self, admin_client):
        admin_client._mock_supabase.set_table_data("platform_settings", [])
        admin_client._mock_supabase.set_table_data("platform_commission_overrides", [])
        resp = admin_client.get("/api/admin/financials/commissions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["global_rate_pct"] == 10.0
        assert body["data"]["overrides"] == []

    def test_get_config_therapist_forbidden(self, client):
        resp = client.get("/api/admin/financials/commissions")
        assert resp.status_code == 403

    def test_get_config_no_auth(self, client):
        resp = client._tc.get("/api/admin/financials/commissions")
        assert resp.status_code == 401


class TestSetCommissionConfig:
    """POST /api/admin/financials/commissions (new shape)"""

    def test_post_global_rate_only(self, admin_client):
        admin_client._mock_supabase.set_table_data("platform_settings", [
            {"key": "global_commission_rate", "value": "10"},
        ])
        resp = admin_client.post(
            "/api/admin/financials/commissions",
            json={"global_rate_pct": "15.0"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["global_rate_pct"] == 15.0

    def test_post_global_rate_creates_setting_when_absent(self, admin_client):
        admin_client._mock_supabase.set_table_data("platform_settings", [])
        resp = admin_client.post(
            "/api/admin/financials/commissions",
            json={"global_rate_pct": "11.0"},
        )
        assert resp.status_code == 200

    def test_post_override_only(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "platform_commission_overrides", []
        )
        resp = admin_client.post(
            "/api/admin/financials/commissions",
            json={
                "override": {
                    "entity_type": "clinic",
                    "entity_id": "clinic-001",
                    "rate_pct": "7.5",
                },
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["override"]["entity_type"] == "clinic"
        assert body["data"]["override"]["rate_pct"] == 7.5

    def test_post_legacy_shape_still_accepted(self, admin_client):
        """The legacy ``{target_type, target_id, custom_commission_pct}`` body
        is normalized into ``override`` so existing tooling keeps working."""
        admin_client._mock_supabase.set_table_data(
            "platform_commission_overrides", []
        )
        resp = admin_client.post(
            "/api/admin/financials/commissions",
            json={
                "target_type": "clinic",
                "target_id": "clinic-001",
                "custom_commission_pct": "8.0",
            },
        )
        assert resp.status_code == 200

    def test_post_empty_body_rejected(self, admin_client):
        resp = admin_client.post("/api/admin/financials/commissions", json={})
        assert resp.status_code == 422

    def test_post_therapist_forbidden(self, client):
        resp = client.post(
            "/api/admin/financials/commissions",
            json={"global_rate_pct": "5.0"},
        )
        assert resp.status_code == 403


class TestDeleteCommissionOverride:
    """DELETE /api/admin/financials/commissions/{id}"""

    def test_delete_override(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "platform_commission_overrides",
            [{"id": "ov-1", "target_type": "clinic", "target_id": "clinic-001",
              "custom_commission_pct": 8.0}],
        )
        resp = admin_client.delete("/api/admin/financials/commissions/ov-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["id"] == "ov-1"
        assert body["data"]["deleted"] is True

    def test_delete_nonexistent_override(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "platform_commission_overrides", []
        )
        resp = admin_client.delete("/api/admin/financials/commissions/missing")
        assert resp.status_code == 404

    def test_delete_therapist_forbidden(self, client):
        resp = client.delete("/api/admin/financials/commissions/any-id")
        assert resp.status_code == 403

    def test_delete_no_auth(self, client):
        resp = client._tc.delete("/api/admin/financials/commissions/any-id")
        assert resp.status_code == 401
