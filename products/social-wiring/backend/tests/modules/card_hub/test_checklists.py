"""Checklists — D11, BOTH kinds; multiple checklists per card required
(screenshot 10). Progress (`total_itens`/`concluidos`) is served, not
counted in the browser."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import cliente_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


class TestChecklists:
    def test_create_two_checklists_on_one_card(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])

        r1 = client.post(f"/api/clientes/{cid}/checklists", json={"titulo": "Documentação"}, headers=_auth())
        r2 = client.post(f"/api/clientes/{cid}/checklists", json={"titulo": "Visita"}, headers=_auth())
        assert r1.status_code == 201, r1.text
        assert r2.status_code == 201, r2.text
        assert r1.json()["origem"] == "ad_hoc"
        assert r1.json()["posicao"] == 0
        assert r2.json()["posicao"] == 1

        resp = client.get(f"/api/clientes/{cid}/checklists", headers=_auth())
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_items_progress_is_served(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        cl = client.post(f"/api/clientes/{cid}/checklists", json={"titulo": "X"}, headers=_auth()).json()

        i1 = client.post(f"/api/clientes/{cid}/checklists/{cl['id']}/itens", json={"texto": "a"}, headers=_auth()).json()
        client.post(f"/api/clientes/{cid}/checklists/{cl['id']}/itens", json={"texto": "b"}, headers=_auth())

        resp = client.patch(
            f"/api/clientes/{cid}/checklists/{cl['id']}/itens/{i1['id']}",
            json={"concluido": True},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["concluido"] is True
        assert resp.json()["concluido_em"] is not None

        listed = client.get(f"/api/clientes/{cid}/checklists", headers=_auth()).json()
        checklist = next(c for c in listed["items"] if c["id"] == cl["id"])
        assert checklist["total_itens"] == 2
        assert checklist["concluidos"] == 1

    def test_uncompleting_an_item_clears_concluido_em(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        cl = client.post(f"/api/clientes/{cid}/checklists", json={"titulo": "X"}, headers=_auth()).json()
        item = client.post(f"/api/clientes/{cid}/checklists/{cl['id']}/itens", json={"texto": "a"}, headers=_auth()).json()
        client.patch(f"/api/clientes/{cid}/checklists/{cl['id']}/itens/{item['id']}", json={"concluido": True}, headers=_auth())

        resp = client.patch(
            f"/api/clientes/{cid}/checklists/{cl['id']}/itens/{item['id']}",
            json={"concluido": False},
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["concluido"] is False
        assert resp.json()["concluido_em"] is None

    def test_delete_checklist_cascades_items(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        cl = client.post(f"/api/clientes/{cid}/checklists", json={"titulo": "X"}, headers=_auth()).json()
        client.post(f"/api/clientes/{cid}/checklists/{cl['id']}/itens", json={"texto": "a"}, headers=_auth())

        resp = client.delete(f"/api/clientes/{cid}/checklists/{cl['id']}", headers=_auth())
        assert resp.status_code == 204

        remaining_items = (
            scoped.table("cliente_checklist_itens").select("*").eq("checklist_id", cl["id"]).execute().data
        )
        assert remaining_items == []

    def test_unknown_checklist_404s(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.patch(
            f"/api/clientes/{cid}/checklists/{uuid4()}", json={"titulo": "x"}, headers=_auth()
        )
        assert resp.status_code == 404

    def test_delete_item_unknown_404s(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        cl = client.post(f"/api/clientes/{cid}/checklists", json={"titulo": "X"}, headers=_auth()).json()
        resp = client.delete(
            f"/api/clientes/{cid}/checklists/{cl['id']}/itens/{uuid4()}", headers=_auth()
        )
        assert resp.status_code == 404
