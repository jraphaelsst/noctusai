"""Checklists — both kinds, many per card, progress SERVED. Ported from
social-wiring's `tests/modules/card_hub/test_checklists.py`."""
from __future__ import annotations

from uuid import uuid4

from tests.domain.card_hub.conftest import AUTH, USER_ID


class TestChecklists:
    def test_create_two_checklists_on_one_card(self, hub):
        eid = hub.new_entity()
        r1 = hub.client.post(hub.url(eid, "/checklists"), json={"titulo": "Documentação"}, headers=AUTH)
        r2 = hub.client.post(hub.url(eid, "/checklists"), json={"titulo": "Visita"}, headers=AUTH)
        assert r1.status_code == 201, r1.text
        assert r2.status_code == 201, r2.text
        assert r1.json()["origem"] == "ad_hoc"
        assert r1.json()["posicao"] == 0
        assert r2.json()["posicao"] == 1
        assert list(r1.json()) == [
            "id", "titulo", "posicao", "origem", "etapa_id", "itens", "total_itens", "concluidos",
        ]

        resp = hub.client.get(hub.url(eid, "/checklists"), headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["total"] == 2
        assert [c["titulo"] for c in resp.json()["items"]] == ["Documentação", "Visita"]

    def test_items_progress_is_served(self, hub):
        eid = hub.new_entity()
        cl = hub.client.post(hub.url(eid, "/checklists"), json={"titulo": "X"}, headers=AUTH).json()
        i1 = hub.client.post(hub.url(eid, f"/checklists/{cl['id']}/itens"), json={"texto": "a"}, headers=AUTH).json()
        i2 = hub.client.post(hub.url(eid, f"/checklists/{cl['id']}/itens"), json={"texto": "b"}, headers=AUTH).json()
        assert (i1["posicao"], i2["posicao"]) == (0, 1)

        resp = hub.client.patch(
            hub.url(eid, f"/checklists/{cl['id']}/itens/{i1['id']}"), json={"concluido": True}, headers=AUTH
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["concluido"] is True
        assert resp.json()["concluido_em"] is not None
        assert resp.json()["concluido_por"] == USER_ID

        listed = hub.client.get(hub.url(eid, "/checklists"), headers=AUTH).json()
        checklist = next(c for c in listed["items"] if c["id"] == cl["id"])
        assert checklist["total_itens"] == 2
        assert checklist["concluidos"] == 1
        assert [i["texto"] for i in checklist["itens"]] == ["a", "b"]

    def test_uncompleting_an_item_clears_concluido_em(self, hub):
        eid = hub.new_entity()
        cl = hub.client.post(hub.url(eid, "/checklists"), json={"titulo": "X"}, headers=AUTH).json()
        item = hub.client.post(hub.url(eid, f"/checklists/{cl['id']}/itens"), json={"texto": "a"}, headers=AUTH).json()
        hub.client.patch(hub.url(eid, f"/checklists/{cl['id']}/itens/{item['id']}"), json={"concluido": True}, headers=AUTH)

        resp = hub.client.patch(
            hub.url(eid, f"/checklists/{cl['id']}/itens/{item['id']}"), json={"concluido": False}, headers=AUTH
        )
        assert resp.status_code == 200
        assert resp.json()["concluido"] is False
        assert resp.json()["concluido_em"] is None
        assert resp.json()["concluido_por"] is None

    def test_rename_and_reposition_a_checklist(self, hub):
        eid = hub.new_entity()
        cl = hub.client.post(hub.url(eid, "/checklists"), json={"titulo": "X"}, headers=AUTH).json()
        resp = hub.client.patch(hub.url(eid, f"/checklists/{cl['id']}"), json={"titulo": "Y", "posicao": 4}, headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert (resp.json()["titulo"], resp.json()["posicao"]) == ("Y", 4)

    def test_delete_checklist_cascades_items(self, hub):
        eid = hub.new_entity()
        cl = hub.client.post(hub.url(eid, "/checklists"), json={"titulo": "X"}, headers=AUTH).json()
        hub.client.post(hub.url(eid, f"/checklists/{cl['id']}/itens"), json={"texto": "a"}, headers=AUTH)

        resp = hub.client.delete(hub.url(eid, f"/checklists/{cl['id']}"), headers=AUTH)
        assert resp.status_code == 204
        remaining = hub.db.table(hub.cfg.tables.checklist_itens).select("*").eq("checklist_id", cl["id"]).execute().data
        assert remaining == []

    def test_unknown_checklist_404s(self, hub):
        eid = hub.new_entity()
        resp = hub.client.patch(hub.url(eid, f"/checklists/{uuid4()}"), json={"titulo": "x"}, headers=AUTH)
        assert resp.status_code == 404
        assert resp.json()["error"]["details"]["resource"] == hub.cfg.tables.checklists

    def test_another_entitys_checklist_is_a_404(self, hub):
        eid, other = hub.new_entity(), hub.new_entity()
        cl = hub.client.post(hub.url(eid, "/checklists"), json={"titulo": "X"}, headers=AUTH).json()
        resp = hub.client.delete(hub.url(other, f"/checklists/{cl['id']}"), headers=AUTH)
        assert resp.status_code == 404

    def test_delete_item_unknown_404s(self, hub):
        eid = hub.new_entity()
        cl = hub.client.post(hub.url(eid, "/checklists"), json={"titulo": "X"}, headers=AUTH).json()
        resp = hub.client.delete(hub.url(eid, f"/checklists/{cl['id']}/itens/{uuid4()}"), headers=AUTH)
        assert resp.status_code == 404
        assert resp.json()["error"]["details"]["resource"] == hub.cfg.tables.checklist_itens
