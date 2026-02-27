"""
Tests for Metas router — /api/metas
"""
import pytest


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------

class TestListarMetas:
    def test_list_metas(self, client):
        client._mock_supabase.set_table_data("metas", [
            {"id": "m1", "categoria": "captacao", "meta_pretendida": 10},
        ])
        resp = client.get("/api/metas")
        assert resp.status_code == 200

    def test_list_by_corretor(self, client):
        resp = client.get("/api/metas?corretor_id=user-123")
        assert resp.status_code == 200


class TestCriarMeta:
    def test_create_meta(self, client):
        client._mock_supabase.set_table_data("metas", {"id": "m-new", "categoria": "contatos"})
        resp = client.post("/api/metas", json={
            "categoria": "contatos",
            "tipo": "diaria",
            "meta_pretendida": 10,
            "data_prazo": "2026-02-23",
        })
        assert resp.status_code == 200

    def test_create_meta_missing_fields(self, client):
        resp = client.post("/api/metas", json={"categoria": "captacao"})
        assert resp.status_code == 422

    def test_create_meta_with_expanded_fields(self, client):
        client._mock_supabase.set_table_data("metas", {
            "id": "m-exp",
            "categoria": "outro",
            "categoria_custom": "Networking",
            "detalhes": "Meta especial",
            "criada_manualmente": True,
            "meta_realizada": 0,
            "status": "no_prazo",
            "tem_impedimento": False,
        })
        resp = client.post("/api/metas", json={
            "categoria": "outro",
            "categoria_custom": "Networking",
            "tipo": "mensal",
            "meta_pretendida": 20,
            "data_prazo": "2026-02-28",
            "detalhes": "Meta especial",
            "criada_manualmente": True,
            "meta_realizada": 0,
            "status": "no_prazo",
            "tem_impedimento": False,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["categoria_custom"] == "Networking"

    def test_create_meta_invalid_status(self, client):
        resp = client.post("/api/metas", json={
            "categoria": "captacao",
            "tipo": "diaria",
            "meta_pretendida": 5,
            "data_prazo": "2026-02-23",
            "status": "invalido",
        })
        assert resp.status_code == 422


class TestAtualizarMeta:
    def test_update_meta(self, client):
        client._mock_supabase.set_table_data("metas", {"id": "m1", "meta_realizada": 5})
        resp = client.patch("/api/metas/m1", json={"meta_realizada": 5})
        assert resp.status_code == 200

    def test_update_meta_expanded_fields(self, client):
        client._mock_supabase.set_table_data("metas", {
            "id": "m1",
            "tem_impedimento": True,
            "motivo_impedimento": "Falta de estoque",
            "finalizada_em": "2026-02-23T10:00:00",
            "finalizada_no_prazo": True,
            "nivel_performance": "alto",
        })
        resp = client.patch("/api/metas/m1", json={
            "tem_impedimento": True,
            "motivo_impedimento": "Falta de estoque",
            "finalizada_em": "2026-02-23T10:00:00",
            "finalizada_no_prazo": True,
            "nivel_performance": "alto",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["tem_impedimento"] is True
        assert data["nivel_performance"] == "alto"

    def test_update_meta_carry_fields(self, client):
        client._mock_supabase.set_table_data("metas", {
            "id": "m1", "carry_in": 3, "carry_out": 2,
        })
        resp = client.patch("/api/metas/m1", json={
            "carry_in": 3,
            "carry_out": 2,
        })
        assert resp.status_code == 200


class TestExcluirMeta:
    def test_delete_meta(self, client):
        resp = client.delete("/api/metas/m1")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Data-prazo endpoint
# ---------------------------------------------------------------------------

class TestDataPrazo:
    def test_data_prazo_default(self, client):
        resp = client.get("/api/metas/data-prazo")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "data_hoje" in data
        assert "data_prazo" in data

    def test_data_prazo_with_tipo(self, client):
        resp = client.get("/api/metas/data-prazo?tipo=diaria")
        assert resp.status_code == 200

    def test_data_prazo_invalid_tipo(self, client):
        resp = client.get("/api/metas/data-prazo?tipo=bimestral")
        assert resp.status_code == 422

    def test_data_prazo_no_auth(self, client):
        resp = client._tc.get("/api/metas/data-prazo")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Config CRUD endpoints
# ---------------------------------------------------------------------------

class TestListarConfig:
    def test_list_config(self, client):
        client._mock_supabase.set_table_data("metas_config", [
            {"id": "cfg1", "usuario_id": "test-user-123", "tipo": "mensal",
             "categoria": "captacao", "meta_pretendida": 10, "ativo": True},
        ])
        resp = client.get("/api/metas/config")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 1

    def test_list_config_empty(self, client):
        client._mock_supabase.set_table_data("metas_config", [])
        resp = client.get("/api/metas/config")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_config_no_auth(self, client):
        resp = client._tc.get("/api/metas/config")
        assert resp.status_code == 401


class TestUpsertConfig:
    def test_upsert_config(self, client):
        client._mock_supabase.set_table_data("metas_config", {
            "id": "cfg-new", "usuario_id": "test-user-123",
            "tipo": "mensal", "categoria": "visitas",
            "meta_pretendida": 15, "ativo": True,
        })
        resp = client.post("/api/metas/config", json={
            "categoria": "visitas",
            "meta_pretendida": 15,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["categoria"] == "visitas"

    def test_upsert_config_with_custom(self, client):
        client._mock_supabase.set_table_data("metas_config", {
            "id": "cfg-cust", "usuario_id": "test-user-123",
            "tipo": "mensal", "categoria": "outro",
            "categoria_custom": "Networking", "meta_pretendida": 5, "ativo": True,
        })
        resp = client.post("/api/metas/config", json={
            "categoria": "outro",
            "categoria_custom": "Networking",
            "meta_pretendida": 5,
        })
        assert resp.status_code == 200

    def test_upsert_config_inactive(self, client):
        client._mock_supabase.set_table_data("metas_config", {
            "id": "cfg-off", "usuario_id": "test-user-123",
            "tipo": "mensal", "categoria": "captacao",
            "meta_pretendida": 10, "ativo": False,
        })
        resp = client.post("/api/metas/config", json={
            "categoria": "captacao",
            "meta_pretendida": 10,
            "ativo": False,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["ativo"] is False

    def test_upsert_config_missing_required(self, client):
        resp = client.post("/api/metas/config", json={
            "categoria": "captacao",
        })
        assert resp.status_code == 422

    def test_upsert_config_no_auth(self, client):
        resp = client._tc.post("/api/metas/config", json={
            "categoria": "captacao", "meta_pretendida": 10,
        }, headers={"Content-Type": "application/json"})
        assert resp.status_code == 401


class TestExcluirConfig:
    def test_delete_config(self, client):
        resp = client.delete("/api/metas/config/cfg-123")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_config_no_auth(self, client):
        resp = client._tc.delete("/api/metas/config/cfg-123")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Concluir endpoint
# ---------------------------------------------------------------------------

class TestConcluirMeta:
    def test_concluir_meta(self, client):
        client._mock_supabase.set_rpc_data("concluir_meta_agrupada", {
            "success": True, "message": "Meta concluída",
        })
        resp = client.post("/api/metas/m1/concluir")
        assert resp.status_code == 200

    def test_concluir_meta_rpc_failure(self, client):
        client._mock_supabase.set_rpc_data("concluir_meta_agrupada", {
            "success": False, "error": "Meta já concluída",
        })
        resp = client.post("/api/metas/m1/concluir")
        assert resp.status_code == 400
        assert "Meta já concluída" in resp.json()["error"]["message"]

    def test_concluir_meta_no_auth(self, client):
        resp = client._tc.post("/api/metas/m1/concluir")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Atualizar status endpoint
# ---------------------------------------------------------------------------

class TestAtualizarStatus:
    def test_atualizar_status(self, client):
        client._mock_supabase.set_table_data("metas", [
            {"id": "m1"}, {"id": "m2"},
        ])
        resp = client.post("/api/metas/atualizar-status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "metas_atualizadas" in data

    def test_atualizar_status_no_overdue(self, client):
        client._mock_supabase.set_table_data("metas", [])
        resp = client.post("/api/metas/atualizar-status")
        assert resp.status_code == 200
        assert resp.json()["data"]["metas_atualizadas"] == 0

    def test_atualizar_status_no_auth(self, client):
        resp = client._tc.post("/api/metas/atualizar-status")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Criar hoje endpoint
# ---------------------------------------------------------------------------

class TestCriarHoje:
    def test_criar_hoje_no_configs(self, client):
        client._mock_supabase.set_table_data("metas_config", [])
        resp = client.post("/api/metas/criar-hoje")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["metas_criadas"] == 0

    def test_criar_hoje_with_configs(self, client):
        client._mock_supabase.set_table_data("metas_config", [
            {"id": "cfg1", "usuario_id": "test-user-123", "tipo": "mensal",
             "categoria": "captacao", "meta_pretendida": 10, "ativo": True},
        ])
        # ensure_scaffold_meta returns None (no existing meta) so new ones are created
        client._mock_supabase.set_rpc_data("ensure_scaffold_meta", None)
        client._mock_supabase.set_rpc_data("calcular_meta_proporcional", 8)
        client._mock_supabase.set_rpc_data("period_end_date", "2026-02-28")
        client._mock_supabase.set_table_data("metas", {"id": "m-new"})

        resp = client.post("/api/metas/criar-hoje")
        assert resp.status_code == 200
        assert resp.json()["data"]["metas_criadas"] >= 0

    def test_criar_hoje_no_auth(self, client):
        resp = client._tc.post("/api/metas/criar-hoje")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Scaffold endpoint
# ---------------------------------------------------------------------------

class TestScaffold:
    def test_scaffold(self, client):
        client._mock_supabase.set_rpc_data("ensure_scaffold_meta", "meta-id-123")
        resp = client.post("/api/metas/scaffold", json={
            "tipo": "mensal",
            "categoria": "captacao",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["meta_id"] is not None

    def test_scaffold_with_data_ref(self, client):
        client._mock_supabase.set_rpc_data("ensure_scaffold_meta", "meta-id-456")
        resp = client.post("/api/metas/scaffold", json={
            "tipo": "diaria",
            "categoria": "visitas",
            "data_ref": "2026-02-20",
        })
        assert resp.status_code == 200

    def test_scaffold_invalid_tipo(self, client):
        resp = client.post("/api/metas/scaffold", json={
            "tipo": "bimestral",
            "categoria": "captacao",
        })
        assert resp.status_code == 422

    def test_scaffold_no_auth(self, client):
        resp = client._tc.post("/api/metas/scaffold",
                               json={"tipo": "mensal", "categoria": "captacao"},
                               headers={"Content-Type": "application/json"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Calcular proporcional endpoint
# ---------------------------------------------------------------------------

class TestCalcularProporcional:
    def test_calcular_proporcional(self, client):
        client._mock_supabase.set_rpc_data("calcular_meta_proporcional", 8)
        resp = client.post("/api/metas/calcular-proporcional", json={
            "meta_mensal": 30,
            "tipo": "diaria",
        })
        assert resp.status_code == 200
        assert "meta_proporcional" in resp.json()["data"]

    def test_calcular_proporcional_with_data_ref(self, client):
        client._mock_supabase.set_rpc_data("calcular_meta_proporcional", 15)
        resp = client.post("/api/metas/calcular-proporcional", json={
            "meta_mensal": 30,
            "tipo": "semanal",
            "data_ref": "2026-02-15",
        })
        assert resp.status_code == 200

    def test_calcular_proporcional_missing_fields(self, client):
        resp = client.post("/api/metas/calcular-proporcional", json={
            "tipo": "mensal",
        })
        assert resp.status_code == 422

    def test_calcular_proporcional_no_auth(self, client):
        resp = client._tc.post("/api/metas/calcular-proporcional",
                               json={"meta_mensal": 30, "tipo": "diaria"},
                               headers={"Content-Type": "application/json"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Metas hoje endpoint
# ---------------------------------------------------------------------------

class TestMetasHoje:
    def test_metas_hoje(self, client):
        client._mock_supabase.set_table_data("metas", [
            {"id": "m1", "categoria": "captacao"},
        ])
        resp = client.get("/api/metas/hoje")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "metas" in data
        assert "data_hoje" in data

    def test_metas_hoje_no_auth(self, client):
        resp = client._tc.get("/api/metas/hoje")
        assert resp.status_code == 401
