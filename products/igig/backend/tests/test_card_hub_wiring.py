"""The seed card hub, consumed twice: the Cliente card and the Negócio card.

Pins (a) that `migrations/019_card_hub.sql` is still exactly what the seed
generator emits for `app/card_hub.py`'s configs, (b) the route-ORDER hazard
(`GET /api/clientes/tags` must not be swallowed by `GET /api/clientes/{id}`),
and (c) that both cards actually work end to end on the shared `igig` mock.
"""
from pathlib import Path
from uuid import uuid4

import pytest

from app.dependencies import coerce_org_uuid

ORG = str(coerce_org_uuid("test-org-123"))
MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "019_card_hub.sql"


def test_migration_019_is_the_generators_output():
    from app.card_hub import gerar_migration_card_hub

    assert MIGRATION.read_text(encoding="utf-8") == gerar_migration_card_hub(), (
        "019_card_hub.sql drifted from noctusai_lib.domain.card_hub.card_hub_migration — "
        "regenerate it (see the file header); never hand-edit a generated migration"
    )


def test_card_hub_documents_never_touch_the_igig_bucket():
    """019 grants org members read/write on their org folder of the card-hub
    bucket; `igig` (peças/logos) must stay service-role-only."""
    from app.card_hub import CARD_HUB_CLIENTE, CARD_HUB_NEGOCIO

    assert CARD_HUB_CLIENTE.bucket == CARD_HUB_NEGOCIO.bucket == "igig-cardhub"
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "bucket_id = 'igig'" not in sql
    assert "('igig', 'igig'" not in sql
    assert '"igig_storage_' not in sql
    assert "bucket_id = 'igig-cardhub'" in sql


def test_both_cards_use_the_profissional_team_as_members():
    from app.card_hub import CARD_HUB_CLIENTE, CARD_HUB_NEGOCIO

    for cfg in (CARD_HUB_CLIENTE, CARD_HUB_NEGOCIO):
        assert cfg.member_source.table == "profissional"
        assert cfg.member_source.body_key == "profissional_ids"
    assert CARD_HUB_CLIENTE.tables.notas == "cliente_notas"
    assert CARD_HUB_NEGOCIO.tables.notas == "negocio_notas"


@pytest.fixture
def api(crm_api):
    return crm_api


# The card-hub routes type their ids as UUID (as Postgres generates them), so
# these rows get real UUIDs rather than the mock's `mock-<table>-N` auto-ids.
@pytest.fixture
def negocio(api, igig_db) -> dict:
    entrada = api.get("/api/comercial/pipeline/stages").json()["data"][0]
    lead = igig_db.table("lead").insert(
        {"id": str(uuid4()), "org_id": ORG, "nome": "João", "origem": "manual"}
    ).execute().data[0]
    return igig_db.table("negocio").insert({
        "id": str(uuid4()), "org_id": ORG, "lead_id": lead["id"], "titulo": "Padaria",
        "etapa_id": entrada["id"], "status": "aberto",
    }).execute().data[0]


@pytest.fixture
def cliente(igig_db) -> dict:
    return igig_db.table("cliente").insert(
        {"id": str(uuid4()), "org_id": ORG, "nome": "Padaria Sol", "status": "ativo"}
    ).execute().data[0]


class TestRotas:
    def test_cliente_tags_is_not_swallowed_by_the_bare_id_route(self, api):
        resp = api.get("/api/clientes/tags")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"items": [], "total": 0}

    def test_negocio_tags_resolve_too(self, api):
        assert api.get("/api/comercial/negocios/tags").status_code == 200

    @pytest.mark.parametrize("path", ["/api/clientes/tags", "/api/comercial/negocios/tags"])
    def test_requires_auth(self, api, path):
        assert api.raw().get(path).status_code == 401

    def test_card_hub_routes_use_the_service_role_client(self):
        """The generated tables grant `authenticated` SELECT only — writes go
        through service_role by construction (app/card_hub.py)."""
        from app.main import app
        from app.pipelines import get_admin_db

        for route in app.routes:
            if getattr(route, "path", "") == "/api/comercial/negocios/{negocio_id}/notas":
                calls = {d.call for d in route.dependant.dependencies}
                assert get_admin_db in calls
                return
        raise AssertionError("negocio notas route not mounted")


class TestCartaoNegocio:
    def test_nota_round_trip(self, api, negocio):
        criada = api.post(f"/api/comercial/negocios/{negocio['id']}/notas",
                          json={"corpo": "Ligar na segunda"})
        assert criada.status_code == 201, criada.text
        timeline = api.get(f"/api/comercial/negocios/{negocio['id']}/timeline")
        assert timeline.status_code == 200, timeline.text

    def test_card_resumo(self, api, negocio):
        resp = api.get(f"/api/comercial/negocios/{negocio['id']}/card")
        assert resp.status_code == 200, resp.text

    def test_unknown_negocio_is_404(self, api):
        resp = api.post("/api/comercial/negocios/00000000-0000-0000-0000-000000000000/notas",
                        json={"corpo": "x"})
        assert resp.status_code == 404


class TestCartaoCliente:
    def test_nota_on_the_cliente_card(self, api, cliente):
        resp = api.post(f"/api/clientes/{cliente['id']}/notas", json={"corpo": "Briefing ok"})
        assert resp.status_code == 201, resp.text

    def test_membros_are_profissionais(self, api, igig_db, cliente):
        prof = igig_db.table("profissional").insert(
            {"id": str(uuid4()), "org_id": ORG, "nome": "Ana", "ativo": True}
        ).execute().data[0]
        resp = api.put(f"/api/clientes/{cliente['id']}/membros",
                       json={"profissional_ids": [prof["id"]]})
        assert resp.status_code == 200, resp.text
