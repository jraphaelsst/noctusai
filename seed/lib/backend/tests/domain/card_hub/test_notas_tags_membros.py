"""Notas, tags, membros — ported from social-wiring's
`tests/modules/card_hub/test_notas_tags_membros.py`, run against both configs."""
from __future__ import annotations

from uuid import uuid4

from tests.domain.card_hub.conftest import AUTH, USER_ID


class TestNotas:
    def test_create_update_delete_roundtrip(self, hub):
        eid = hub.new_entity()

        resp = hub.client.post(hub.url(eid, "/notas"), json={"corpo": "primeira nota"}, headers=AUTH)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        nota_id = body["id"]
        assert body["corpo"] == "primeira nota"
        assert body["editado_em"] is None
        assert body["deleted_at"] is None
        # The author is RESOLVED to a name, never served as a bare id.
        assert body["autor"] == {"id": USER_ID, "nome": "Rapha"}
        assert list(body) == ["id", "tipo", "corpo", "autor", "editado_em", "deleted_at"]

        resp = hub.client.patch(hub.url(eid, f"/notas/{nota_id}"), json={"corpo": "editada"}, headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert resp.json()["corpo"] == "editada"
        assert resp.json()["editado_em"] is not None

        resp = hub.client.delete(hub.url(eid, f"/notas/{nota_id}"), headers=AUTH)
        assert resp.status_code == 204, resp.text

        # A tombstoned note 404s on a second edit — and the row survives.
        resp = hub.client.patch(hub.url(eid, f"/notas/{nota_id}"), json={"corpo": "x"}, headers=AUTH)
        assert resp.status_code == 404
        assert resp.json()["error"]["details"]["resource"] == hub.cfg.tables.notas
        stored = hub.rows(hub.cfg.tables.notas)
        assert len(stored) == 1 and stored[0]["deleted_at"] is not None

    def test_create_nota_unknown_entity_404s_naming_the_entity_table(self, hub):
        resp = hub.client.post(hub.url(str(uuid4()), "/notas"), json={"corpo": "x"}, headers=AUTH)
        assert resp.status_code == 404
        assert resp.json()["error"]["details"]["resource"] == hub.cfg.entity_table

    def test_strict_body_rejects_unknown_field(self, hub):
        eid = hub.new_entity()
        resp = hub.client.post(hub.url(eid, "/notas"), json={"corpo": "x", "extra": "nope"}, headers=AUTH)
        assert resp.status_code == 422

    def test_default_tipo_is_comentario(self, hub):
        eid = hub.new_entity()
        resp = hub.client.post(hub.url(eid, "/notas"), json={"corpo": "x"}, headers=AUTH)
        assert resp.status_code == 201, resp.text
        assert resp.json()["tipo"] == "comentario"

    def test_descricao_tipo_is_accepted_and_only_one_allowed(self, hub):
        eid = hub.new_entity()
        resp = hub.client.post(
            hub.url(eid, "/notas"), json={"corpo": "Descrição do card", "tipo": "descricao"}, headers=AUTH
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["tipo"] == "descricao"

        # A second descricao is a typed 409, never a raw 500 from the index.
        resp2 = hub.client.post(hub.url(eid, "/notas"), json={"corpo": "Outra", "tipo": "descricao"}, headers=AUTH)
        assert resp2.status_code == 409, resp2.text
        err = resp2.json()["error"]
        assert err["code"] == "CONFLICT"
        assert err["details"]["resource"] == hub.cfg.tables.notas
        assert f"Este {hub.cfg.entity_kind} já possui uma descrição" in err["message"]

    def test_a_deleted_descricao_does_not_block_a_fresh_one(self, hub):
        eid = hub.new_entity()
        first = hub.client.post(hub.url(eid, "/notas"), json={"corpo": "a", "tipo": "descricao"}, headers=AUTH).json()
        hub.client.delete(hub.url(eid, f"/notas/{first['id']}"), headers=AUTH)
        resp = hub.client.post(hub.url(eid, "/notas"), json={"corpo": "b", "tipo": "descricao"}, headers=AUTH)
        assert resp.status_code == 201, resp.text

    def test_descricao_is_not_in_the_timeline(self, hub):
        eid = hub.new_entity()
        hub.client.post(hub.url(eid, "/notas"), json={"corpo": "Descrição", "tipo": "descricao"}, headers=AUTH)
        hub.client.post(hub.url(eid, "/notas"), json={"corpo": "Um comentário"}, headers=AUTH)

        resp = hub.client.get(hub.url(eid, "/timeline"), headers=AUTH)
        assert resp.status_code == 200, resp.text
        nota_entries = [e for e in resp.json()["items"] if e["kind"] == "nota"]
        assert len(nota_entries) == 1
        assert nota_entries[0]["corpo"] == "Um comentário"

    def test_invalid_tipo_422s(self, hub):
        eid = hub.new_entity()
        resp = hub.client.post(hub.url(eid, "/notas"), json={"corpo": "x", "tipo": "nota_qualquer"}, headers=AUTH)
        assert resp.status_code == 422


class TestTags:
    def test_create_list_update_delete(self, hub):
        resp = hub.client.post(f"{hub.prefix}/tags", json={"nome": "Quente", "cor": "#ff0000"}, headers=AUTH)
        assert resp.status_code == 201, resp.text
        tag = resp.json()
        assert tag["nome"] == "Quente"
        assert list(tag) == ["id", "nome", "cor"]

        resp = hub.client.get(f"{hub.prefix}/tags", headers=AUTH)
        assert resp.status_code == 200
        assert {t["id"] for t in resp.json()["items"]} == {tag["id"]}

        resp = hub.client.patch(f"{hub.prefix}/tags/{tag['id']}", json={"cor": "#00ff00"}, headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["cor"] == "#00ff00"

        resp = hub.client.delete(f"{hub.prefix}/tags/{tag['id']}", headers=AUTH)
        assert resp.status_code == 204

        resp = hub.client.get(f"{hub.prefix}/tags", headers=AUTH)
        assert resp.json() == {"items": [], "total": 0}

    def test_duplicate_name_conflicts(self, hub):
        hub.seed(hub.cfg.tables.tags, [hub.tag_row(str(uuid4()), nome="Quente")])
        resp = hub.client.post(f"{hub.prefix}/tags", json={"nome": "quente", "cor": "#ff0000"}, headers=AUTH)
        assert resp.status_code == 409
        assert resp.json()["error"]["message"] == "Tag 'quente' já existe"

    def test_rename_onto_an_existing_name_conflicts(self, hub):
        a, b = str(uuid4()), str(uuid4())
        hub.seed(hub.cfg.tables.tags, [hub.tag_row(a, nome="A"), hub.tag_row(b, nome="B")])
        resp = hub.client.patch(f"{hub.prefix}/tags/{a}", json={"nome": "b"}, headers=AUTH)
        assert resp.status_code == 409

    def test_invalid_hex_color_422s(self, hub):
        resp = hub.client.post(f"{hub.prefix}/tags", json={"nome": "X", "cor": "red"}, headers=AUTH)
        assert resp.status_code == 422

    def test_delete_tag_unlinks_it_from_every_card(self, hub):
        eid = hub.new_entity()
        t1 = str(uuid4())
        hub.seed(hub.cfg.tables.tags, [hub.tag_row(t1)])
        hub.client.put(hub.url(eid, "/tags"), json={"tag_ids": [t1]}, headers=AUTH)
        assert hub.client.delete(f"{hub.prefix}/tags/{t1}", headers=AUTH).status_code == 204
        assert hub.rows(hub.cfg.tables.tag_links) == []

    def test_set_entity_tags_full_replace(self, hub):
        eid = hub.new_entity()
        t1, t2 = str(uuid4()), str(uuid4())
        hub.seed(hub.cfg.tables.tags, [hub.tag_row(t1, nome="A"), hub.tag_row(t2, nome="B")])

        resp = hub.client.put(hub.url(eid, "/tags"), json={"tag_ids": [t1, t2]}, headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert [t["nome"] for t in resp.json()["items"]] == ["A", "B"]

        # Full replace — dropping t2 removes it, not additive.
        resp = hub.client.put(hub.url(eid, "/tags"), json={"tag_ids": [t1]}, headers=AUTH)
        assert resp.status_code == 200
        assert {t["id"] for t in resp.json()["items"]} == {t1}

    def test_set_entity_tags_unknown_tag_404s(self, hub):
        eid = hub.new_entity()
        resp = hub.client.put(hub.url(eid, "/tags"), json={"tag_ids": [str(uuid4())]}, headers=AUTH)
        assert resp.status_code == 404
        assert resp.json()["error"]["details"]["resource"] == hub.cfg.tables.tags


class TestMembros:
    def test_set_and_get_membros(self, hub):
        eid = hub.new_entity()
        c1, c2 = str(uuid4()), str(uuid4())
        hub.seed(hub.cfg.member_source.table, [hub.member_row(c1, nome="Bia"), hub.member_row(c2, nome="Caio")])
        key = hub.cfg.member_source.body_key

        resp = hub.client.put(hub.url(eid, "/membros"), json={key: [c2, c1]}, headers=AUTH)
        assert resp.status_code == 200, resp.text
        assert [m["nome"] for m in resp.json()["items"]] == ["Bia", "Caio"]
        assert resp.json()["items"][0] == {"id": c1, "nome": "Bia", "cor": "#00ff00"}

        resp = hub.client.get(hub.url(eid, "/membros"), headers=AUTH)
        assert resp.status_code == 200
        assert {m["id"] for m in resp.json()["items"]} == {c1, c2}

    def test_body_field_is_the_member_source_contract(self, hub):
        """Social-wiring's HTTP contract names the list `lead_corretor_ids`;
        the neutral config's is `membro_ids`. A body with the other name is a
        strict-model 422, never a silently-empty assignment."""
        expected = {"lead": "membro_ids", "sw": "lead_corretor_ids"}[hub.name]
        assert hub.cfg.member_source.body_key == expected
        eid = hub.new_entity()
        wrong = "lead_corretor_ids" if hub.name == "lead" else "membro_ids"
        resp = hub.client.put(hub.url(eid, "/membros"), json={wrong: []}, headers=AUTH)
        assert resp.status_code == 422

    def test_set_membros_unknown_member_404s_naming_the_member_table(self, hub):
        eid = hub.new_entity()
        key = hub.cfg.member_source.body_key
        resp = hub.client.put(hub.url(eid, "/membros"), json={key: [str(uuid4())]}, headers=AUTH)
        assert resp.status_code == 404
        assert resp.json()["error"]["details"]["resource"] == hub.cfg.member_source.table
