"""
Tests for the Evolution Notes Router.

Covers: create SOAP, create livre, list paginated, update,
get single note, and auth/permission checks.
"""
import pytest

SAMPLE_NOTE_SOAP = {
    "id": "note-001",
    "patient_id": "patient-001",
    "therapist_id": "test-user-123",
    "formato": "soap",
    "subjetivo": "Paciente relata melhora na qualidade do sono",
    "objetivo": "Apresenta-se calmo e comunicativo",
    "avaliacao": "Evolução positiva no quadro de ansiedade",
    "plano": "Manter frequência semanal",
    "conteudo_livre": None,
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_NOTE_LIVRE = {
    "id": "note-002",
    "patient_id": "patient-001",
    "therapist_id": "test-user-123",
    "formato": "livre",
    "subjetivo": None,
    "objetivo": None,
    "avaliacao": None,
    "plano": None,
    "conteudo_livre": "Sessão focada em exercícios de exposição.",
    "created_at": "2026-04-02T10:00:00Z",
}


class TestCreateEvolutionNote:
    """POST /api/evolucao"""

    def test_create_soap_note(self, client):
        """Therapist creates a SOAP evolution note."""
        client._mock_supabase.set_table_data("evolution_notes", [SAMPLE_NOTE_SOAP])
        resp = client.post("/api/evolucao", json={
            "patient_id": "patient-001",
            "formato": "soap",
            "subjetivo": "Paciente relata melhora",
            "objetivo": "Calmo e comunicativo",
            "avaliacao": "Evolução positiva",
            "plano": "Manter sessões",
        })
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_create_livre_note(self, client):
        """Therapist creates a free-form evolution note."""
        client._mock_supabase.set_table_data("evolution_notes", [SAMPLE_NOTE_LIVRE])
        resp = client.post("/api/evolucao", json={
            "patient_id": "patient-001",
            "formato": "livre",
            "conteudo_livre": "Sessão focada em exercícios de exposição.",
        })
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_create_note_patient_forbidden(self, patient_client):
        """Patient cannot create evolution notes."""
        resp = patient_client.post("/api/evolucao", json={
            "patient_id": "patient-001",
            "formato": "soap",
            "subjetivo": "Teste",
        })
        assert resp.status_code == 403

    def test_create_note_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/evolucao", json={
            "formato": "soap",
        })
        assert resp.status_code == 401


class TestListEvolutionNotes:
    """GET /api/evolucao/paciente/{patient_id}"""

    def test_list_notes(self, client):
        """Therapist lists notes for a patient."""
        client._mock_supabase.set_table_data("evolution_notes", [SAMPLE_NOTE_SOAP, SAMPLE_NOTE_LIVRE])
        resp = client.get("/api/evolucao/paciente/patient-001")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_notes_patient_forbidden(self, patient_client):
        """Patient cannot list evolution notes."""
        resp = patient_client.get("/api/evolucao/paciente/patient-001")
        assert resp.status_code == 403

    def test_list_notes_admin_allowed(self, admin_client):
        """Platform admin can list evolution notes."""
        admin_client._mock_supabase.set_table_data("evolution_notes", [SAMPLE_NOTE_SOAP])
        resp = admin_client.get("/api/evolucao/paciente/patient-001")
        assert resp.status_code == 200


class TestGetEvolutionNote:
    """GET /api/evolucao/{note_id}"""

    def test_get_note(self, client):
        """Therapist gets their own note."""
        client._mock_supabase.set_table_data("evolution_notes", [SAMPLE_NOTE_SOAP])
        resp = client.get("/api/evolucao/note-001")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_get_note_not_found(self, client):
        """Non-existent note returns 404."""
        client._mock_supabase.set_table_data("evolution_notes", [])
        resp = client.get("/api/evolucao/nonexistent")
        assert resp.status_code == 404

    def test_get_note_not_owner(self, client):
        """Therapist cannot view another therapist's note."""
        other_note = {**SAMPLE_NOTE_SOAP, "therapist_id": "other-therapist-999"}
        client._mock_supabase.set_table_data("evolution_notes", [other_note])
        resp = client.get("/api/evolucao/note-001")
        assert resp.status_code == 403


class TestUpdateEvolutionNote:
    """PATCH /api/evolucao/{note_id}"""

    def test_update_note(self, client):
        """Therapist updates their own note."""
        client._mock_supabase.set_table_data("evolution_notes", [SAMPLE_NOTE_SOAP])
        resp = client.patch("/api/evolucao/note-001", json={
            "plano": "Aumentar frequência para 2x/semana",
        })
        assert resp.status_code == 200

    def test_update_note_not_found(self, client):
        """Non-existent note returns 404."""
        client._mock_supabase.set_table_data("evolution_notes", [])
        resp = client.patch("/api/evolucao/nonexistent", json={
            "plano": "Teste",
        })
        assert resp.status_code == 404

    def test_update_note_not_owner(self, client):
        """Therapist cannot update another therapist's note."""
        other_note = {**SAMPLE_NOTE_SOAP, "therapist_id": "other-therapist-999"}
        client._mock_supabase.set_table_data("evolution_notes", [other_note])
        resp = client.patch("/api/evolucao/note-001", json={
            "plano": "Teste",
        })
        assert resp.status_code == 403

    def test_update_note_patient_forbidden(self, patient_client):
        """Patient cannot update evolution notes."""
        resp = patient_client.patch("/api/evolucao/note-001", json={
            "plano": "Teste",
        })
        assert resp.status_code == 403
