"""Tests for the Notes router — /api/notes endpoints."""

SAMPLE_NOTE = {
    "id": "note-1",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "titulo": "Ideias para projeto",
    "conteudo": "Implementar feature X usando abordagem Y",
    "categoria": "trabalho",
    "tags": ["projeto", "ideias"],
    "fixada": False,
    "updated_at": "2026-04-13T10:00:00Z",
}

SAMPLE_NOTE_PINNED = {
    "id": "note-2",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "titulo": "Contatos importantes",
    "conteudo": "Lista de fornecedores",
    "categoria": "pessoal",
    "tags": ["contatos"],
    "fixada": True,
    "updated_at": "2026-04-13T12:00:00Z",
}


# ---------------------------------------------------------------------------
# List notes
# ---------------------------------------------------------------------------

class TestListNotes:
    def test_list_notes(self, client):
        client.mock_supabase.set_table_data("notas", [SAMPLE_NOTE_PINNED, SAMPLE_NOTE])
        resp = client.get("/api/notes")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 2
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 20

    def test_list_notes_no_auth(self, client):
        resp = client.raw().get("/api/notes")
        assert resp.status_code == 401

    def test_list_notes_search(self, client):
        client.mock_supabase.set_table_data("notas", [SAMPLE_NOTE])
        resp = client.get("/api/notes", params={"busca": "projeto"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["titulo"] == "Ideias para projeto"

    def test_list_notes_search_by_conteudo(self, client):
        """Search should match notes by conteudo, not just titulo."""
        note_match_conteudo = {
            **SAMPLE_NOTE,
            "id": "note-3",
            "titulo": "Anotacao generica",
            "conteudo": "Lembrar de comprar ingredientes para o jantar",
        }
        client.mock_supabase.set_table_data("notas", [note_match_conteudo])
        resp = client.get("/api/notes", params={"busca": "ingredientes"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == "note-3"
        # The term "ingredientes" appears only in conteudo, not titulo
        assert "ingredientes" in data[0]["conteudo"]
        assert "ingredientes" not in data[0]["titulo"]

    def test_list_notes_search_multi_field(self, client):
        """Search with busca should match across both titulo and conteudo via .or_()."""
        note_titulo_match = {
            **SAMPLE_NOTE,
            "id": "note-t",
            "titulo": "Receita de bolo",
            "conteudo": "Farinha e ovos",
        }
        note_conteudo_match = {
            **SAMPLE_NOTE,
            "id": "note-c",
            "titulo": "Lista de compras",
            "conteudo": "Comprar bolo na padaria",
        }
        # Both notes match "bolo" — one in titulo, one in conteudo
        client.mock_supabase.set_table_data("notas", [note_titulo_match, note_conteudo_match])
        resp = client.get("/api/notes", params={"busca": "bolo"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2

    def test_list_notes_filter_categoria(self, client):
        client.mock_supabase.set_table_data("notas", [SAMPLE_NOTE])
        resp = client.get("/api/notes", params={"categoria": "trabalho"})
        assert resp.status_code == 200
        assert resp.json()["data"][0]["categoria"] == "trabalho"

    def test_list_notes_pagination(self, client):
        client.mock_supabase.set_table_data("notas", [SAMPLE_NOTE])
        resp = client.get("/api/notes", params={"page": 3, "page_size": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 3
        assert body["pagination"]["page_size"] == 5

    def test_list_notes_empty(self, client):
        client.mock_supabase.set_table_data("notas", [])
        resp = client.get("/api/notes")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# Create note
# ---------------------------------------------------------------------------

class TestCreateNote:
    def test_create_note(self, client):
        client.mock_supabase.set_table_data("notas", [SAMPLE_NOTE])
        resp = client.post("/api/notes", json={
            "titulo": "Ideias para projeto",
            "conteudo": "Implementar feature X usando abordagem Y",
            "categoria": "trabalho",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["titulo"] == "Ideias para projeto"
        assert body["data"]["conteudo"] == "Implementar feature X usando abordagem Y"

    def test_create_note_with_tags(self, client):
        note_with_tags = {**SAMPLE_NOTE, "tags": ["work", "important"]}
        client.mock_supabase.set_table_data("notas", [note_with_tags])
        resp = client.post("/api/notes", json={
            "titulo": "Tagged note",
            "tags": ["work", "important"],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "work" in data["tags"]
        assert "important" in data["tags"]

    def test_create_note_pinned(self, client):
        client.mock_supabase.set_table_data("notas", [SAMPLE_NOTE_PINNED])
        resp = client.post("/api/notes", json={
            "titulo": "Contatos importantes",
            "fixada": True,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["fixada"] is True

    def test_create_note_empty_titulo(self, client):
        resp = client.post("/api/notes", json={"titulo": ""})
        assert resp.status_code == 422

    def test_create_note_missing_titulo(self, client):
        resp = client.post("/api/notes", json={"conteudo": "Sem titulo"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get single note
# ---------------------------------------------------------------------------

class TestGetNote:
    def test_get_note(self, client):
        client.mock_supabase.set_table_data("notas", [SAMPLE_NOTE])
        resp = client.get("/api/notes/note-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["id"] == "note-1"
        assert body["data"]["titulo"] == "Ideias para projeto"
        assert body["data"]["tags"] == ["projeto", "ideias"]

    def test_get_note_not_found(self, client):
        client.mock_supabase.set_table_data("notas", [])
        resp = client.get("/api/notes/nonexistent")
        assert resp.status_code == 404
        assert "nao encontrada" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Update note
# ---------------------------------------------------------------------------

class TestUpdateNote:
    def test_update_note(self, client):
        updated = {**SAMPLE_NOTE, "titulo": "Ideias atualizadas"}
        client.mock_supabase.set_table_data("notas", [updated])
        resp = client.patch("/api/notes/note-1", json={"titulo": "Ideias atualizadas"})
        assert resp.status_code == 200
        assert resp.json()["data"]["titulo"] == "Ideias atualizadas"

    def test_pin_note(self, client):
        pinned = {**SAMPLE_NOTE, "fixada": True}
        client.mock_supabase.set_table_data("notas", [pinned])
        resp = client.patch("/api/notes/note-1", json={"fixada": True})
        assert resp.status_code == 200
        assert resp.json()["data"]["fixada"] is True

    def test_update_note_tags(self, client):
        updated = {**SAMPLE_NOTE, "tags": ["novo", "tag"]}
        client.mock_supabase.set_table_data("notas", [updated])
        resp = client.patch("/api/notes/note-1", json={"tags": ["novo", "tag"]})
        assert resp.status_code == 200
        assert resp.json()["data"]["tags"] == ["novo", "tag"]

    def test_update_note_not_found(self, client):
        client.mock_supabase.set_table_data("notas", [])
        resp = client.patch("/api/notes/nonexistent", json={"titulo": "Nada"})
        assert resp.status_code == 404

    def test_update_note_no_fields(self, client):
        resp = client.patch("/api/notes/note-1", json={})
        assert resp.status_code == 400
        assert "nenhum campo" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Delete note
# ---------------------------------------------------------------------------

class TestDeleteNote:
    def test_delete_note(self, client):
        client.mock_supabase.set_table_data("notas", [SAMPLE_NOTE])
        resp = client.delete("/api/notes/note-1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "removida" in resp.json()["message"].lower()

    def test_delete_note_not_found(self, client):
        client.mock_supabase.set_table_data("notas", [])
        resp = client.delete("/api/notes/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# D4 — Extract tasks from note (ai-expansion Phase 16)
# ---------------------------------------------------------------------------

class TestExtractTasks:
    """D4 note extraction tests. Daily Life's `note_extract` is registered
    with `default_granted=False` (high-risk personal data); these happy-path
    tests pre-seed the consent grant inside each test (no autouse fixture
    here since this file mainly tests non-AI note CRUD)."""

    @staticmethod
    def _grant_note_extract(client):
        client.mock_supabase.set_table_data("ai_consent", [{
            "feature_key": "daily_life.note_extract",
            "granted": True, "user_id": "test-user-123",
            "granted_at": "2026-04-27T00:00:00Z", "revoked_at": None,
        }])

    def test_extract_tasks_returns_list(self, client):
        from unittest.mock import patch, AsyncMock

        self._grant_note_extract(client)
        client.mock_supabase.set_table_data("notas", [SAMPLE_NOTE])
        with patch(
            "app.services.ai_service.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = (
                '{"tasks": ['
                ' {"title": "Implementar feature X", "due_hint": null},'
                ' {"title": "Avaliar abordagem Y", "due_hint": "sexta-feira"}'
                ']}'
            )
            resp = client.post("/api/notes/note-1/extract-tasks")

        assert resp.status_code == 200
        body = resp.json()
        assert "tasks" in body["data"]
        assert len(body["data"]["tasks"]) == 2
        assert body["data"]["tasks"][0]["title"] == "Implementar feature X"

    def test_extract_tasks_note_not_found(self, client):
        self._grant_note_extract(client)
        client.mock_supabase.set_table_data("notas", [])
        resp = client.post("/api/notes/nonexistent/extract-tasks")
        assert resp.status_code == 404
