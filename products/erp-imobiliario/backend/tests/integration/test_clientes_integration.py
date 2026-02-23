"""
Integration tests for Clientes router.

Tests complete CRUD cycles and workflow scenarios using stateful mocking.
"""
import pytest


class TestClientesCRUDCycle:
    """Test complete create-read-update-delete cycle for clients."""

    def test_full_crud_cycle(self, integration_client):
        """Test creating, reading, updating, and deleting a client."""
        # CREATE
        create_response = integration_client.post("/api/clientes", json={
            "nome": "João da Silva",
            "email": "joao@example.com",
            "telefone": "11999998888",
            "origem": "site",
            "interesse": "Apartamento 3 quartos",
            "probabilidade": 70,
            "valor_estimado": 500000.0,
        })
        assert create_response.status_code == 200
        data = create_response.json()["data"]
        assert data["nome"] == "João da Silva"
        cliente_id = data["id"]

        # READ - Get single
        get_response = integration_client.get(f"/api/clientes/{cliente_id}")
        assert get_response.status_code == 200
        assert get_response.json()["data"]["email"] == "joao@example.com"

        # READ - List
        list_response = integration_client.get("/api/clientes")
        assert list_response.status_code == 200
        assert list_response.json()["pagination"]["total"] >= 1

        # UPDATE
        update_response = integration_client.patch(f"/api/clientes/{cliente_id}", json={
            "probabilidade": 85,
            "observacoes": "Cliente muito interessado",
        })
        assert update_response.status_code == 200
        assert update_response.json()["data"]["probabilidade"] == 85

        # DELETE
        delete_response = integration_client.delete(f"/api/clientes/{cliente_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["ok"] is True


class TestClientesPipelineWorkflow:
    """Test client pipeline movement workflows."""

    def test_client_through_pipeline(self, integration_client):
        """Test moving a client through sales pipeline stages."""
        # Create client
        response = integration_client.post("/api/clientes", json={
            "nome": "Maria Souza",
            "email": "maria@example.com",
            "interesse": "Casa em condomínio",
        })
        assert response.status_code == 200
        cliente_id = response.json()["data"]["id"]

        # Move through pipeline stages
        stages = ["qualificacao", "visitas", "proposta", "negociacao", "fechado"]

        for stage in stages:
            move_response = integration_client.post(
                f"/api/clientes/{cliente_id}/mover-etapa",
                json={"para_etapa": stage, "motivo": f"Avançando para {stage}"}
            )
            assert move_response.status_code == 200
            assert move_response.json()["data"]["etapa_atual"] == stage


class TestClientesArchiving:
    """Test client archiving functionality."""

    def test_archive_unarchive_cycle(self, integration_client):
        """Test archiving and unarchiving a client."""
        # Create client
        response = integration_client.post("/api/clientes", json={
            "nome": "Pedro Santos",
            "email": "pedro@example.com",
        })
        cliente_id = response.json()["data"]["id"]

        # Archive
        archive_response = integration_client.post(f"/api/clientes/{cliente_id}/arquivar")
        assert archive_response.status_code == 200
        assert archive_response.json()["data"]["arquivado"] is True

        # Unarchive
        unarchive_response = integration_client.post(f"/api/clientes/{cliente_id}/arquivar")
        assert unarchive_response.status_code == 200
        assert unarchive_response.json()["data"]["arquivado"] is False


class TestClientesPagination:
    """Test pagination functionality."""

    def test_pagination_parameters(self, integration_client):
        """Test that pagination parameters work correctly."""
        # Seed some clients
        for i in range(5):
            integration_client.post("/api/clientes", json={
                "nome": f"Cliente {i}",
                "email": f"cliente{i}@example.com",
            })

        # Test first page
        response = integration_client.get("/api/clientes?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 2
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 2


class TestClientesValidation:
    """Test input validation."""

    def test_invalid_probabilidade_rejected(self, integration_client):
        """Test that invalid probability values are rejected."""
        response = integration_client.post("/api/clientes", json={
            "nome": "Test",
            "probabilidade": 150,  # Invalid: > 100
        })
        assert response.status_code == 422

    def test_invalid_email_rejected(self, integration_client):
        """Test that invalid email format is rejected."""
        response = integration_client.post("/api/clientes", json={
            "nome": "Test",
            "email": "not-an-email",
        })
        assert response.status_code == 422

    def test_invalid_etapa_rejected(self, integration_client):
        """Test that invalid pipeline stage is rejected."""
        # First create a valid client
        create_response = integration_client.post("/api/clientes", json={
            "nome": "Test Cliente",
        })
        cliente_id = create_response.json()["data"]["id"]

        # Try to move to invalid stage
        move_response = integration_client.post(
            f"/api/clientes/{cliente_id}/mover-etapa",
            json={"para_etapa": "invalid_stage"}
        )
        assert move_response.status_code == 400
