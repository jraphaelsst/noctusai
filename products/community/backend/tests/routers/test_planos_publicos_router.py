"""Tests for `GET /api/planos/publicos` — contract amendment A17.

PUBLIC, no auth header (`client.raw()`), org via `seed_public_license`.
"""
from tests.conftest import ORG_UUID, seed_public_license

PLANO_ATIVO = "11111111-1111-1111-1111-111111111111"
PLANO_INATIVO = "22222222-2222-2222-2222-222222222222"
PLANO_SEM_REFS = "33333333-3333-3333-3333-333333333333"


def _plano_row(**over) -> dict:
    base = {
        "id": PLANO_ATIVO, "org_id": ORG_UUID, "nome": "Círculo", "descricao": "desc",
        "preco_centavos": 9900, "ciclo": "mensal",
        "entitlements": {
            "feed": True, "forum": False, "chat": True, "eventos": False,
            "conteudo_ids": ["seg-1", "seg-2"], "grupos_whatsapp": ["grp-1"],
            "conteudo_todos": True,
        },
        "ativo": True, "ordem": 0,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _seed(client, *, plano_rows=None, ref_rows=None):
    seed_public_license(client)
    client.mock_supabase.set_table_data(
        "planos", plano_rows if plano_rows is not None else [_plano_row()],
    )
    client.mock_supabase.set_table_data(
        "plano_gateway_refs",
        ref_rows if ref_rows is not None else [{
            "id": "ref-1", "org_id": ORG_UUID, "plano_id": PLANO_ATIVO, "gateway": "stripe",
            "ref_externo": "price_1",
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }, {
            "id": "ref-2", "org_id": ORG_UUID, "plano_id": PLANO_ATIVO, "gateway": "asaas",
            "ref_externo": "asaas-ref-1",
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }],
    )


class TestPublicoPublicAccess:
    def test_no_auth_required_200(self, client):
        _seed(client)
        resp = client.raw().get("/api/planos/publicos")
        assert resp.status_code == 200

    def test_inactive_plans_absent(self, client):
        _seed(client, plano_rows=[
            _plano_row(),
            _plano_row(id=PLANO_INATIVO, nome="Descontinuado", ativo=False),
        ])
        resp = client.raw().get("/api/planos/publicos")
        ids = {item["id"] for item in resp.json()["items"]}
        assert PLANO_INATIVO not in ids
        assert PLANO_ATIVO in ids

    def test_forbidden_fields_absent(self, client):
        _seed(client)
        resp = client.raw().get("/api/planos/publicos")
        item = resp.json()["items"][0]
        assert set(item.keys()) == {
            "id", "nome", "descricao", "preco_centavos", "ciclo",
            "beneficios", "metodos_disponiveis",
        }
        for forbidden in ("ref_externo", "membros_ativos", "ativo", "ordem", "created_at", "updated_at"):
            assert forbidden not in item
        assert set(item["beneficios"].keys()) == {"feed", "forum", "chat", "eventos"}
        assert "conteudo_ids" not in item["beneficios"]
        assert "grupos_whatsapp" not in item["beneficios"]

    def test_metodos_disponiveis_reflects_refs(self, client):
        _seed(client)
        resp = client.raw().get("/api/planos/publicos")
        item = resp.json()["items"][0]
        assert set(item["metodos_disponiveis"]) == {"cartao", "pix", "boleto"}

    def test_plano_with_no_refs_returns_empty_list(self, client):
        _seed(client, plano_rows=[_plano_row(id=PLANO_SEM_REFS, nome="Sem refs")], ref_rows=[])
        resp = client.raw().get("/api/planos/publicos")
        item = resp.json()["items"][0]
        assert item["metodos_disponiveis"] == []
