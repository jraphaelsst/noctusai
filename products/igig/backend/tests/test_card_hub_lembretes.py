"""The card-hub "Lembretes" subpage CRUD, mounted on both igig card hubs
(`CARD_HUB_CLIENTE` / `CARD_HUB_NEGOCIO`, `lembretes_crud=True` —
`app/card_hub.py`). The generic mechanics live in the seed
(`seed/lib/backend/tests/domain/card_hub/test_lembretes_crud.py`); these pin
that igig's TWO cards actually expose the routes end to end on the shared
mock, and that `app/services/notificacoes.py::processar_lembretes_pendentes`
(the scheduler drain) still finds a row this CRUD creates.
"""
from uuid import uuid4

import pytest

from app.dependencies import coerce_org_uuid
from app.services.notificacoes import processar_lembretes_pendentes

ORG = str(coerce_org_uuid("test-org-123"))


@pytest.fixture
def api(crm_api):
    return crm_api


@pytest.fixture
def cliente(igig_db) -> dict:
    return igig_db.table("cliente").insert(
        {"id": str(uuid4()), "org_id": ORG, "nome": "Padaria Sol", "status": "ativo"}
    ).execute().data[0]


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
def profissional(igig_db) -> dict:
    return igig_db.table("profissional").insert(
        {"id": str(uuid4()), "org_id": ORG, "nome": "Ana", "ativo": True}
    ).execute().data[0]


class TestClienteLembretes:
    def test_create_list_edit_conclude_delete(self, api, cliente, profissional):
        base = f"/api/clientes/{cliente['id']}/lembretes"
        criado = api.post(base, json={
            "titulo": "Ligar para confirmar a arte", "dispara_em": "2026-10-05T09:00:00-03:00",
            "responsavel_id": profissional["id"],
        })
        assert criado.status_code == 201, criado.text
        body = criado.json()
        assert body["titulo"] == "Ligar para confirmar a arte"
        assert body["dispara_em"] == "2026-10-05T12:00:00+00:00"
        assert body["responsavel"] == {"id": profissional["id"], "nome": "Ana", "cor": None}
        assert body["concluido"] is False

        listado = api.get(base)
        assert listado.status_code == 200
        assert listado.json()["total"] == 1

        editado = api.patch(f"{base}/{body['id']}", json={"titulo": "Ligar amanhã"})
        assert editado.status_code == 200, editado.text
        assert editado.json()["titulo"] == "Ligar amanhã"

        concluido = api.patch(f"{base}/{body['id']}", json={"concluido": True})
        assert concluido.status_code == 200
        assert concluido.json()["concluido"] is True

        apagado = api.delete(f"{base}/{body['id']}")
        assert apagado.status_code == 204
        assert api.get(base).json()["total"] == 0

    def test_unknown_cliente_is_404(self, api):
        resp = api.post(
            "/api/clientes/00000000-0000-0000-0000-000000000000/lembretes",
            json={"titulo": "X", "dispara_em": "2026-10-05T09:00:00-03:00"},
        )
        assert resp.status_code == 404

    def test_requires_auth(self, api, cliente):
        assert api.raw().get(f"/api/clientes/{cliente['id']}/lembretes").status_code == 401

    def test_a_delivered_reminder_still_drains_through_the_scheduler(self, api, igig_db, core_db, cliente, profissional):
        """The CRUD's own `enviado_em: None` row IS the shape
        `processar_lembretes_pendentes` already drains — proves the two
        halves (create here, deliver in `notificacoes.py`) still agree."""
        base = f"/api/clientes/{cliente['id']}/lembretes"
        criado = api.post(base, json={
            "titulo": "Padaria Sol — renovação", "dispara_em": "2020-01-01T09:00:00-03:00",
        }).json()
        igig_db.table("cliente_membros").insert(
            {"org_id": ORG, "cliente_id": cliente["id"], "profissional_id": profissional["id"]}
        ).execute()
        igig_db.table("profissional").update({"usuario_id": "user-ana"}).eq("id", profissional["id"]).execute()

        resumo = processar_lembretes_pendentes(igig_db, core_db)
        assert resumo["notificados"] == 1
        [notificacao] = core_db.table("notifications")._data
        assert notificacao["user_id"] == "user-ana"

        # delivered ⇒ the CRUD's own list now reports it done, never re-sent.
        assert api.get(base).json()["items"][0]["concluido"] is True
        resumo2 = processar_lembretes_pendentes(igig_db, core_db)
        assert resumo2["processados"] == 0


class TestNegocioLembretes:
    def test_create_and_list(self, api, negocio):
        base = f"/api/comercial/negocios/{negocio['id']}/lembretes"
        criado = api.post(base, json={"titulo": "Follow-up comercial", "dispara_em": "2026-10-05T09:00:00-03:00"})
        assert criado.status_code == 201, criado.text
        assert api.get(base).json()["total"] == 1

    def test_requires_auth(self, api, negocio):
        assert api.raw().get(f"/api/comercial/negocios/{negocio['id']}/lembretes").status_code == 401
