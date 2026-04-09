"""
Tests for the Therapeutic Journal Router.

Covers: CRUD operations (patient only), delete pre-check,
update ownership check, and auth/permission checks.
"""
import pytest

SAMPLE_ENTRY = {
    "id": "journal-001",
    "patient_id": "test-user-123",
    "titulo": "Reflexão sobre a sessão",
    "conteudo": "Hoje percebi que a ansiedade diminuiu bastante.",
    "is_shared_with_therapist": False,
    "created_at": "2026-04-01T10:00:00Z",
}


class TestCreateJournalEntry:
    """POST /api/diario"""

    def test_create_entry(self, patient_client):
        """Patient creates a journal entry."""
        patient_client._mock_supabase.set_table_data("journal_entries", [SAMPLE_ENTRY])
        resp = patient_client.post("/api/diario", json={
            "conteudo": "Hoje percebi que a ansiedade diminuiu bastante.",
            "titulo": "Reflexão sobre a sessão",
        })
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_create_entry_therapist_forbidden(self, client):
        """Therapist cannot create journal entries."""
        resp = client.post("/api/diario", json={
            "conteudo": "Teste",
        })
        assert resp.status_code == 403

    def test_create_entry_admin_forbidden(self, admin_client):
        """Admin cannot create journal entries."""
        resp = admin_client.post("/api/diario", json={
            "conteudo": "Teste",
        })
        assert resp.status_code == 403

    def test_create_entry_401(self, patient_client):
        """No auth returns 401."""
        resp = patient_client._tc.post("/api/diario", json={
            "conteudo": "Teste",
        })
        assert resp.status_code == 401


class TestListJournalEntries:
    """GET /api/diario"""

    def test_list_entries(self, patient_client):
        """Patient lists their journal entries."""
        patient_client._mock_supabase.set_table_data("journal_entries", [SAMPLE_ENTRY])
        resp = patient_client.get("/api/diario")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_entries_therapist_forbidden(self, client):
        """Therapist cannot list patient journal entries."""
        resp = client.get("/api/diario")
        assert resp.status_code == 403


class TestUpdateJournalEntry:
    """PATCH /api/diario/{entry_id}"""

    def test_update_entry(self, patient_client):
        """Patient updates their own entry."""
        patient_client._mock_supabase.set_table_data("therapeutic_journal", [SAMPLE_ENTRY])
        patient_client._mock_supabase.set_table_data("journal_entries", [SAMPLE_ENTRY])
        resp = patient_client.patch("/api/diario/journal-001", json={
            "conteudo": "Conteúdo atualizado com novas reflexões.",
        })
        assert resp.status_code == 200

    def test_update_entry_not_found(self, patient_client):
        """Non-existent entry returns 404."""
        patient_client._mock_supabase.set_table_data("therapeutic_journal", [])
        resp = patient_client.patch("/api/diario/nonexistent", json={
            "conteudo": "Teste",
        })
        assert resp.status_code == 404

    def test_update_entry_not_owner(self, patient_client):
        """Patient cannot update another patient's entry."""
        other_entry = {**SAMPLE_ENTRY, "patient_id": "other-patient-999"}
        patient_client._mock_supabase.set_table_data("therapeutic_journal", [other_entry])
        resp = patient_client.patch("/api/diario/journal-001", json={
            "conteudo": "Teste",
        })
        assert resp.status_code == 403

    def test_update_entry_therapist_forbidden(self, client):
        """Therapist cannot update journal entries."""
        resp = client.patch("/api/diario/journal-001", json={
            "conteudo": "Teste",
        })
        assert resp.status_code == 403


class TestDeleteJournalEntry:
    """DELETE /api/diario/{entry_id}"""

    def test_delete_entry(self, patient_client):
        """Patient deletes their own entry."""
        patient_client._mock_supabase.set_table_data("therapeutic_journal", [SAMPLE_ENTRY])
        patient_client._mock_supabase.set_table_data("journal_entries", [SAMPLE_ENTRY])
        resp = patient_client.delete("/api/diario/journal-001")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_entry_not_found(self, patient_client):
        """Non-existent entry returns 404."""
        patient_client._mock_supabase.set_table_data("therapeutic_journal", [])
        resp = patient_client.delete("/api/diario/nonexistent")
        assert resp.status_code == 404

    def test_delete_entry_not_owner(self, patient_client):
        """Patient cannot delete another patient's entry."""
        other_entry = {**SAMPLE_ENTRY, "patient_id": "other-patient-999"}
        patient_client._mock_supabase.set_table_data("therapeutic_journal", [other_entry])
        resp = patient_client.delete("/api/diario/journal-001")
        assert resp.status_code == 403

    def test_delete_entry_therapist_forbidden(self, client):
        """Therapist cannot delete journal entries."""
        resp = client.delete("/api/diario/journal-001")
        assert resp.status_code == 403
