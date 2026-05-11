"""
Tests for the Invoices Router.

Covers: generate invoice (therapist only), list (role-filtered),
get single invoice, and auth/permission checks.
"""
import pytest

SAMPLE_INVOICE = {
    "id": "inv-001",
    "transaction_id": "tx-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
    "amount": 250.00,
    "descricao": "Sessão de terapia individual",
    "status": "gerada",
    "created_at": "2026-04-01T10:00:00Z",
}


class TestGenerateInvoice:
    """POST /api/recibos/gerar"""

    def test_generate_invoice_duplicate(self, client):
        """Generating duplicate invoice returns 409."""
        client._mock_supabase.set_table_data("transactions", [
            {"id": "tx-001", "amount": 250.00, "description": "Sessão individual"},
        ])
        # Mock returns existing invoice -> duplicate check fails
        client._mock_supabase.set_table_data("invoices", [SAMPLE_INVOICE])
        resp = client.post("/api/recibos/gerar", json={
            "transaction_id": "tx-001",
            "patient_id": "patient-001",
        })
        assert resp.status_code == 409

    def test_generate_invoice_patient_forbidden(self, patient_client):
        """Patient cannot generate invoices."""
        resp = patient_client.post("/api/recibos/gerar", json={
            "transaction_id": "tx-001",
            "patient_id": "patient-001",
        })
        assert resp.status_code == 403

    def test_generate_invoice_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/recibos/gerar", json={
            "transaction_id": "tx-001",
        })
        assert resp.status_code == 401


class TestListInvoices:
    """GET /api/recibos"""

    def test_list_invoices_therapist(self, client):
        """Therapist lists their invoices."""
        client._mock_supabase.set_table_data("invoices", [SAMPLE_INVOICE])
        resp = client.get("/api/recibos")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_invoices_patient(self, patient_client):
        """Patient lists invoices addressed to them."""
        patient_client._mock_supabase.set_table_data("invoices", [SAMPLE_INVOICE])
        resp = patient_client.get("/api/recibos")
        assert resp.status_code == 200

    def test_list_invoices_admin(self, admin_client):
        """Platform admin lists all invoices."""
        admin_client._mock_supabase.set_table_data("invoices", [SAMPLE_INVOICE])
        resp = admin_client.get("/api/recibos")
        assert resp.status_code == 200


class TestGetInvoice:
    """GET /api/recibos/{invoice_id}"""

    def test_get_invoice_therapist(self, client):
        """Therapist gets their own invoice."""
        client._mock_supabase.set_table_data("invoices", [SAMPLE_INVOICE])
        resp = client.get("/api/recibos/inv-001")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_get_invoice_not_found(self, client):
        """Non-existent invoice returns 404."""
        client._mock_supabase.set_table_data("invoices", [])
        resp = client.get("/api/recibos/nonexistent")
        assert resp.status_code == 404

    def test_get_invoice_not_owner_therapist(self, client):
        """Therapist cannot view another therapist's invoice."""
        other_invoice = {**SAMPLE_INVOICE, "therapist_id": "other-therapist-999"}
        client._mock_supabase.set_table_data("invoices", [other_invoice])
        resp = client.get("/api/recibos/inv-001")
        assert resp.status_code == 403

    def test_get_invoice_patient_own(self, patient_client):
        """Patient gets their own invoice."""
        patient_invoice = {**SAMPLE_INVOICE, "patient_id": "test-user-123"}
        patient_client._mock_supabase.set_table_data("invoices", [patient_invoice])
        resp = patient_client.get("/api/recibos/inv-001")
        assert resp.status_code == 200

    def test_get_invoice_patient_not_owner(self, patient_client):
        """Patient cannot view another patient's invoice."""
        other_invoice = {**SAMPLE_INVOICE, "patient_id": "other-patient-999"}
        patient_client._mock_supabase.set_table_data("invoices", [other_invoice])
        resp = patient_client.get("/api/recibos/inv-001")
        assert resp.status_code == 403
