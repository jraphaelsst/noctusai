"""NoctusAI's own funnel (`/api/admin/funnel`): platform tier, admin only; strict 401 / 403, then the
real gate, lose-reason and write behaviour over the seed organ with core's declared config."""
from __future__ import annotations

import pytest

from app.main import app
from app.noc_funnel import FUNNEL, NOC_FUNNEL_ORG_ID, PREFIX

CARD = "11111111-1111-4111-8111-111111111111"
S_NOVO = "aaaaaaaa-0000-4000-8000-000000000001"
S_CONTATADO = "aaaaaaaa-0000-4000-8000-000000000002"
S_QUALIFICADO = "aaaaaaaa-0000-4000-8000-000000000003"
S_PROPOSTA = "aaaaaaaa-0000-4000-8000-000000000004"

ROUTES = [
    ("GET", "/meta"),
    ("GET", "/board"),
    ("GET", "/board/orfaos"),
    ("POST", "/cards"),
    ("GET", f"/cards/{CARD}"),
    ("PATCH", f"/cards/{CARD}"),
    ("POST", f"/cards/{CARD}/mover-etapa"),
    ("POST", f"/cards/{CARD}/perder"),
    ("POST", f"/cards/{CARD}/reabrir"),
    ("POST", f"/cards/{CARD}/arquivar"),
    ("POST", f"/cards/{CARD}/acoes/ganhar"),
    ("GET", f"/cards/{CARD}/movimentos"),
    ("GET", "/etapas"),
]


def _stage(sid: str, slug: str, pos: int, papel: str | None) -> dict:
    return {"id": sid, "org_id": NOC_FUNNEL_ORG_ID, "pipeline": "funil_noc", "slug": slug, "label": slug.title(),
            "cor": "secondary", "posicao": pos, "papel": papel, "ativo": True}


def _lead(**over) -> dict:
    return {"id": CARD, "name": "Ana Souza", "company": "Acme", "email": None, "phone_e164": None,
            "source": "contact", "product_interest": ["agents"], "message": "Oi", "consent": {"marketing": True},
            "etapa_id": S_NOVO, "kanban_pos": "0", "status": "aberto", "owner_user_id": None,
            "valor_unico": None, "valor_mensal": None, "oferta_tipo": None, "oferta_descricao": None,
            "motivo_perda_codigo": None, "motivo_perda": None,
            "created_at": "2026-11-01T10:00:00+00:00", "updated_at": "2026-11-01T10:00:00+00:00", **over}


@pytest.fixture
def seeded(admin_client):
    sb = admin_client.mock_supabase
    sb.set_table_data("noctus_users", [{"id": "admin-user-456", "role": "admin", "nome": "Admin"}])
    sb.set_table_data("pipeline_stages", [
        _stage(S_NOVO, "novo", 0, "novo"), _stage(S_CONTATADO, "contatado", 1, "contatado"),
        _stage(S_QUALIFICADO, "qualificado", 2, "qualificado"), _stage(S_PROPOSTA, "proposta", 3, "proposta"),
    ])
    sb.set_table_data("website_leads", [_lead()])
    sb.set_table_data("pipeline_movimentos", [])
    return admin_client


AUTH = {"Authorization": "Bearer test-token-valid"}


class TestAccessTier:
    @pytest.mark.parametrize("method,path", ROUTES)
    def test_unauthenticated_is_strictly_401(self, method, path, unauth_client):
        assert unauth_client._tc.request(method, PREFIX + path).status_code == 401

    @pytest.mark.parametrize("method,path", ROUTES)
    def test_non_admin_is_strictly_403(self, method, path, client):
        client.mock_supabase.set_table_data("noctus_users", [{"id": "test-user-123", "role": "user"}])
        r = client._tc.request(method, PREFIX + path, headers=AUTH, json={})
        assert r.status_code == 403

    def test_router_is_mounted_and_declared_platform(self):
        paths = {getattr(r, "path", "") for r in app.routes}
        assert PREFIX + "/board" in paths and FUNNEL.tenancy == "platform"


class TestConfig:
    def test_outcomes_are_statuses_not_stage_roles(self):
        assert not {"ganho", "perdido"} & set(FUNNEL.pipeline.stage_roles)

    def test_lost_reasons_end_with_outro_that_requires_text(self):
        assert FUNNEL.lost_reasons[-1].codigo == "outro" and FUNNEL.lost_reasons[-1].exige_texto
        assert len(FUNNEL.lost_reasons) == 7


class TestFlow:
    def test_meta_serves_reasons_gates_and_the_ganho_action(self, seeded):
        r = seeded.get(f"{PREFIX}/meta", headers=AUTH)
        assert r.status_code == 200
        data = r.json()["data"]
        assert {x["codigo"] for x in data["lost_reasons"]} >= {"preco", "outro"}
        assert set(data["gates"]) == {"contatado", "qualificado", "proposta"}
        assert [a["codigo"] for a in data["acoes"]] == ["ganhar"]

    def test_board_has_one_column_per_stage_with_the_lead_as_a_card(self, seeded):
        r = seeded.get(f"{PREFIX}/board", headers=AUTH)
        assert r.status_code == 200
        cols = r.json()["data"]
        assert [c["stage"]["slug"] for c in cols] == ["novo", "contatado", "qualificado", "proposta"]
        card = cols[0]["cards"][0]
        assert card["titulo"] == "Ana Souza" and card["subtitulo"] == "Acme"
        assert card["campos"]["origem"] == "Contato" and card["campos"]["mensagem"] == "Oi"

    def test_move_to_qualificado_without_owner_is_refused_and_writes_nothing(self, seeded):
        r = seeded.post(f"{PREFIX}/cards/{CARD}/mover-etapa", headers=AUTH, json={"para_etapa_id": S_QUALIFICADO})
        assert r.status_code == 409
        err = r.json()["error"]
        assert err["code"] == "gate_refused"
        assert err["details"]["pendencias"][0]["codigo"] == "sem_responsavel"
        assert not getattr(seeded.mock_supabase.table("pipeline_movimentos"), "inserted_payloads", [])

    def test_lose_requires_text_for_outro(self, seeded):
        r = seeded.post(f"{PREFIX}/cards/{CARD}/perder", headers=AUTH, json={"motivo_codigo": "outro"})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "motivo_obrigatorio"

    def test_ganhar_marks_won_and_writes_a_history_row(self, seeded):
        r = seeded.post(f"{PREFIX}/cards/{CARD}/acoes/ganhar", headers=AUTH, json={"payload": {}})
        assert r.status_code == 200
        assert r.json()["data"]["efeitos"]["ponte_financeira"] == "nao_implementada"
        sb = seeded.mock_supabase
        assert any(p.get("kind") == "ganho" for p in sb.table("pipeline_movimentos").inserted_payloads)
