"""Tests for `aplicacoes_router` — contract §Aplicações.

The two PUBLIC routes (`GET /formulario`, `POST ""`) need NO auth header
at all (`client.raw()`) and are org-scoped via `resolve_public_org_id`
(seeded via `seed_public_license`).
"""
from tests.conftest import ORG_UUID, seed_community_role, seed_public_license

PERGUNTA_1 = "11111111-1111-1111-1111-111111111111"
PERGUNTA_2 = "22222222-2222-2222-2222-222222222222"
PLANO_1 = "33333333-3333-3333-3333-333333333333"
APLICACAO_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
UNKNOWN_ID = "99999999-9999-9999-9999-999999999999"


def _pergunta_row(**over) -> dict:
    base = {
        "id": PERGUNTA_1,
        "org_id": ORG_UUID,
        "pergunta": "Por que você quer entrar?",
        "tipo": "texto",
        "opcoes": [],
        "obrigatoria": True,
        "ordem": 0,
        "ativa": True,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _aplicacao_row(**over) -> dict:
    base = {
        "id": APLICACAO_1,
        "org_id": ORG_UUID,
        "nome": "Joana",
        "email": "joana@x.com",
        "telefone": None,
        "respostas": {PERGUNTA_1: "Porque sim"},
        "status": "pendente",
        "motivo": None,
        "revisado_por": None,
        "revisado_em": None,
        "membro_id": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


class TestPerguntasAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/aplicacoes/perguntas").status_code == 401

    def test_create_without_auth_401(self, client):
        assert client.raw().post("/api/aplicacoes/perguntas", json={}).status_code == 401

    def test_update_without_auth_401(self, client):
        resp = client.raw().patch(f"/api/aplicacoes/perguntas/{PERGUNTA_1}", json={})
        assert resp.status_code == 401

    def test_delete_without_auth_401(self, client):
        resp = client.raw().delete(f"/api/aplicacoes/perguntas/{PERGUNTA_1}")
        assert resp.status_code == 401


class TestAplicacoesAuthBoundary:
    def test_list_without_auth_401(self, client):
        assert client.raw().get("/api/aplicacoes").status_code == 401

    def test_aprovar_without_auth_401(self, client):
        resp = client.raw().post(f"/api/aplicacoes/{APLICACAO_1}/aprovar", json={})
        assert resp.status_code == 401

    def test_rejeitar_without_auth_401(self, client):
        resp = client.raw().post(f"/api/aplicacoes/{APLICACAO_1}/rejeitar", json={"motivo": "x"})
        assert resp.status_code == 401


class TestPerguntasRoleGate:
    def test_moderador_can_read(self, client):
        seed_community_role(client, org_role="moderador")
        assert client.get("/api/aplicacoes/perguntas").status_code == 200

    def test_moderador_create_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post("/api/aplicacoes/perguntas", json={
            "pergunta": "X?", "tipo": "texto",
        })
        assert resp.status_code == 403
        assert resp.json()["detail"].startswith("Apenas administradores podem")


class TestPerguntasCrud:
    def test_create_201(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post("/api/aplicacoes/perguntas", json={
            "pergunta": "Qual sua idade?", "tipo": "texto",
        })
        assert resp.status_code == 201
        assert resp.json()["pergunta"] == "Qual sua idade?"

    def test_create_choice_type_without_opcoes_422(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post("/api/aplicacoes/perguntas", json={
            "pergunta": "Qual seu signo?", "tipo": "escolha_unica",
        })
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Informe as opções para este tipo de pergunta."

    def test_create_choice_type_with_opcoes_201(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.post("/api/aplicacoes/perguntas", json={
            "pergunta": "Qual seu signo?", "tipo": "escolha_unica",
            "opcoes": ["Áries", "Touro"],
        })
        assert resp.status_code == 201

    def test_list_includes_inactive(self, client):
        client.mock_supabase.set_table_data("aplicacao_perguntas", [
            _pergunta_row(id=PERGUNTA_1, ordem=1, ativa=True),
            _pergunta_row(id=PERGUNTA_2, ordem=0, ativa=False),
        ])
        resp = client.get("/api/aplicacoes/perguntas")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert [p["id"] for p in body["items"]] == [PERGUNTA_2, PERGUNTA_1]

    def test_update_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("aplicacao_perguntas", [_pergunta_row()])
        resp = client.patch(f"/api/aplicacoes/perguntas/{PERGUNTA_1}", json={"ordem": 5})
        assert resp.status_code == 200
        assert resp.json()["ordem"] == 5

    def test_update_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.patch(f"/api/aplicacoes/perguntas/{UNKNOWN_ID}", json={"ordem": 5})
        assert resp.status_code == 404

    def test_delete_204_soft_delete(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("aplicacao_perguntas", [_pergunta_row()])
        resp = client.delete(f"/api/aplicacoes/perguntas/{PERGUNTA_1}")
        assert resp.status_code == 204

    def test_delete_404(self, client):
        seed_community_role(client, org_role="admin")
        resp = client.delete(f"/api/aplicacoes/perguntas/{UNKNOWN_ID}")
        assert resp.status_code == 404


class TestPublicFormulario:
    def test_formulario_only_returns_active_ordered(self, client):
        seed_public_license(client)
        client.mock_supabase.set_table_data("aplicacao_perguntas", [
            _pergunta_row(id=PERGUNTA_1, ordem=1, ativa=True),
            _pergunta_row(id=PERGUNTA_2, ordem=0, ativa=False),
        ])
        resp = client.raw().get("/api/aplicacoes/formulario")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == PERGUNTA_1

    def test_formulario_503_when_not_licensed(self, client):
        # No seed_public_license call — no product/license rows at all.
        resp = client.raw().get("/api/aplicacoes/formulario")
        assert resp.status_code == 503


class TestPublicSubmit:
    def test_submit_201(self, client):
        seed_public_license(client)
        client.mock_supabase.set_table_data("aplicacao_perguntas", [
            _pergunta_row(id=PERGUNTA_1, obrigatoria=True),
        ])
        resp = client.raw().post("/api/aplicacoes", json={
            "nome": "Joana", "email": "joana@x.com",
            "respostas": {PERGUNTA_1: "Porque sim"},
        })
        assert resp.status_code == 201
        assert resp.json()["status"] == "pendente"

    def test_submit_missing_required_question_422(self, client):
        seed_public_license(client)
        client.mock_supabase.set_table_data("aplicacao_perguntas", [
            _pergunta_row(id=PERGUNTA_1, obrigatoria=True),
        ])
        resp = client.raw().post("/api/aplicacoes", json={
            "nome": "Joana", "email": "joana@x.com", "respostas": {},
        })
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Responda todas as perguntas obrigatórias."

    def test_submit_unknown_question_id_422(self, client):
        seed_public_license(client)
        client.mock_supabase.set_table_data("aplicacao_perguntas", [
            _pergunta_row(id=PERGUNTA_1, obrigatoria=False),
        ])
        resp = client.raw().post("/api/aplicacoes", json={
            "nome": "Joana", "email": "joana@x.com",
            "respostas": {UNKNOWN_ID: "x"},
        })
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Pergunta inválida no formulário."

    def test_submit_duplicate_pendente_email_409(self, client):
        seed_public_license(client)
        client.mock_supabase.set_table_data("aplicacao_perguntas", [
            _pergunta_row(id=PERGUNTA_1, obrigatoria=False),
        ])
        client.mock_supabase.set_table_data("aplicacoes", [
            _aplicacao_row(email="joana@x.com", status="pendente"),
        ])
        resp = client.raw().post("/api/aplicacoes", json={
            "nome": "Joana", "email": "joana@x.com", "respostas": {},
        })
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Já existe uma inscrição em análise para esse e-mail."

    def test_submit_without_auth_header_is_allowed(self, client):
        """Genuinely unauthenticated — no Authorization header at all."""
        seed_public_license(client)
        client.mock_supabase.set_table_data("aplicacao_perguntas", [])
        resp = client.raw().post("/api/aplicacoes", json={
            "nome": "Sem Token", "email": "semtoken@x.com", "respostas": {},
        })
        assert resp.status_code == 201


class TestAplicacoesReview:
    def test_list_200_with_resumo(self, client):
        client.mock_supabase.set_table_data("aplicacoes", [
            _aplicacao_row(id=APLICACAO_1, status="pendente"),
            _aplicacao_row(id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", status="aprovada"),
        ])
        resp = client.get("/api/aplicacoes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["resumo"] == {"pendente": 1, "aprovada": 1, "rejeitada": 0}

    def test_list_filters_by_status(self, client):
        client.mock_supabase.set_table_data("aplicacoes", [
            _aplicacao_row(id=APLICACAO_1, status="pendente"),
            _aplicacao_row(id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", status="aprovada"),
        ])
        resp = client.get("/api/aplicacoes", params={"status": "pendente"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "pendente"

    def test_moderador_aprovar_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post(f"/api/aplicacoes/{APLICACAO_1}/aprovar", json={})
        assert resp.status_code == 403

    def test_aprovar_creates_membro_pendente_by_default(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("aplicacoes", [_aplicacao_row(status="pendente")])
        resp = client.post(f"/api/aplicacoes/{APLICACAO_1}/aprovar", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["aplicacao"]["status"] == "aprovada"
        assert body["membro"]["status"] == "pendente"
        assert body["membro"]["origem"] == "aplicacao"
        assert body["aplicacao"]["membro_id"] == body["membro"]["id"]

    def test_aprovar_with_plano_and_ativar_sets_membro_ativo(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("aplicacoes", [_aplicacao_row(status="pendente")])
        resp = client.post(f"/api/aplicacoes/{APLICACAO_1}/aprovar", json={
            "plano_id": PLANO_1, "ativar": True,
        })
        assert resp.status_code == 200
        assert resp.json()["membro"]["status"] == "ativo"
        assert resp.json()["membro"]["plano_id"] == PLANO_1

    def test_aprovar_idempotent_returns_same_membro(self, client):
        seed_community_role(client, org_role="admin")
        membro_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        client.mock_supabase.set_table_data("aplicacoes", [
            _aplicacao_row(status="aprovada", membro_id=membro_id),
        ])
        client.mock_supabase.set_table_data("membros", [{
            "id": membro_id, "org_id": ORG_UUID, "nome": "Joana", "email": "joana@x.com",
            "telefone": None, "status": "pendente", "plano_id": None, "origem": "aplicacao",
            "tags": [], "user_id": None, "observacoes": None, "entrou_em": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        resp = client.post(f"/api/aplicacoes/{APLICACAO_1}/aprovar", json={})
        assert resp.status_code == 200
        assert resp.json()["membro"]["id"] == membro_id

    def test_aprovar_email_already_member_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("aplicacoes", [_aplicacao_row(status="pendente")])
        client.mock_supabase.set_table_data("membros", [{
            "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", "org_id": ORG_UUID,
            "nome": "Joana", "email": "joana@x.com", "telefone": None, "status": "ativo",
            "plano_id": None, "origem": "checkout", "tags": [], "user_id": None,
            "observacoes": None, "entrou_em": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        resp = client.post(f"/api/aplicacoes/{APLICACAO_1}/aprovar", json={})
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Esse e-mail já é um membro."

    def test_aprovar_already_rejected_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("aplicacoes", [_aplicacao_row(status="rejeitada")])
        resp = client.post(f"/api/aplicacoes/{APLICACAO_1}/aprovar", json={})
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Essa inscrição já foi rejeitada."

    def test_rejeitar_200(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("aplicacoes", [_aplicacao_row(status="pendente")])
        resp = client.post(f"/api/aplicacoes/{APLICACAO_1}/rejeitar", json={"motivo": "Não é o perfil"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejeitada"
        assert resp.json()["motivo"] == "Não é o perfil"

    def test_rejeitar_missing_motivo_422(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("aplicacoes", [_aplicacao_row(status="pendente")])
        resp = client.post(f"/api/aplicacoes/{APLICACAO_1}/rejeitar", json={})
        assert resp.status_code == 422

    def test_rejeitar_already_approved_409(self, client):
        seed_community_role(client, org_role="admin")
        client.mock_supabase.set_table_data("aplicacoes", [_aplicacao_row(status="aprovada")])
        resp = client.post(f"/api/aplicacoes/{APLICACAO_1}/rejeitar", json={"motivo": "x"})
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Essa inscrição já foi aprovada."

    def test_moderador_rejeitar_403(self, client):
        seed_community_role(client, org_role="moderador")
        resp = client.post(f"/api/aplicacoes/{APLICACAO_1}/rejeitar", json={"motivo": "x"})
        assert resp.status_code == 403
