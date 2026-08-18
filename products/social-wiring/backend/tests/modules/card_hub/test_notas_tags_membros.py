"""Notas, tags, and membros — contract §3."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import cliente_row, corretor_row, tag_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


class TestNotas:
    def test_create_update_delete_roundtrip(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])

        resp = client.post(f"/api/clientes/{cid}/notas", json={"corpo": "primeira nota"}, headers=_auth())
        assert resp.status_code == 201, resp.text
        body = resp.json()
        nota_id = body["id"]
        assert body["corpo"] == "primeira nota"
        assert body["editado_em"] is None
        assert body["deleted_at"] is None

        resp = client.patch(
            f"/api/clientes/{cid}/notas/{nota_id}", json={"corpo": "editada"}, headers=_auth()
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["corpo"] == "editada"
        assert resp.json()["editado_em"] is not None

        resp = client.delete(f"/api/clientes/{cid}/notas/{nota_id}", headers=_auth())
        assert resp.status_code == 204, resp.text

        # A second delete/update on an already-deleted (tombstoned) note 404s.
        resp = client.patch(
            f"/api/clientes/{cid}/notas/{nota_id}", json={"corpo": "x"}, headers=_auth()
        )
        assert resp.status_code == 404

    def test_create_nota_unknown_cliente_404s(self, client, scoped):
        resp = client.post(f"/api/clientes/{uuid4()}/notas", json={"corpo": "x"}, headers=_auth())
        assert resp.status_code == 404

    def test_strict_body_rejects_unknown_field(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.post(
            f"/api/clientes/{cid}/notas", json={"corpo": "x", "extra": "nope"}, headers=_auth()
        )
        assert resp.status_code == 422

    def test_default_tipo_is_comentario(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.post(f"/api/clientes/{cid}/notas", json={"corpo": "x"}, headers=_auth())
        assert resp.status_code == 201, resp.text
        assert resp.json()["tipo"] == "comentario"

    def test_descricao_tipo_is_accepted_and_only_one_allowed(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.post(
            f"/api/clientes/{cid}/notas", json={"corpo": "Descrição do card", "tipo": "descricao"}, headers=_auth()
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["tipo"] == "descricao"

        # A second descricao is a typed 409, never a raw 500 from the
        # partial unique index (contract correction).
        resp2 = client.post(
            f"/api/clientes/{cid}/notas", json={"corpo": "Outra", "tipo": "descricao"}, headers=_auth()
        )
        assert resp2.status_code == 409, resp2.text

    def test_descricao_is_not_in_the_timeline(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        client.post(
            f"/api/clientes/{cid}/notas", json={"corpo": "Descrição", "tipo": "descricao"}, headers=_auth()
        )
        client.post(f"/api/clientes/{cid}/notas", json={"corpo": "Um comentário"}, headers=_auth())

        resp = client.get(f"/api/clientes/{cid}/timeline", headers=_auth())
        assert resp.status_code == 200, resp.text
        nota_entries = [e for e in resp.json()["items"] if e["kind"] == "nota"]
        assert len(nota_entries) == 1
        assert nota_entries[0]["corpo"] == "Um comentário"

    def test_invalid_tipo_422s(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.post(
            f"/api/clientes/{cid}/notas", json={"corpo": "x", "tipo": "nota_qualquer"}, headers=_auth()
        )
        assert resp.status_code == 422


class TestTags:
    def test_create_list_update_delete(self, client, scoped):
        resp = client.post("/api/clientes/tags", json={"nome": "Quente", "cor": "#ff0000"}, headers=_auth())
        assert resp.status_code == 201, resp.text
        tag = resp.json()
        assert tag["nome"] == "Quente"

        resp = client.get("/api/clientes/tags", headers=_auth())
        assert resp.status_code == 200
        assert {t["id"] for t in resp.json()["items"]} == {tag["id"]}

        resp = client.patch(f"/api/clientes/tags/{tag['id']}", json={"cor": "#00ff00"}, headers=_auth())
        assert resp.status_code == 200
        assert resp.json()["cor"] == "#00ff00"

        resp = client.delete(f"/api/clientes/tags/{tag['id']}", headers=_auth())
        assert resp.status_code == 204

        resp = client.get("/api/clientes/tags", headers=_auth())
        assert resp.json()["items"] == []

    def test_duplicate_name_conflicts(self, client, scoped):
        scoped.set_table_data("cliente_tags", [tag_row(str(uuid4()), nome="Quente")])
        resp = client.post("/api/clientes/tags", json={"nome": "quente", "cor": "#ff0000"}, headers=_auth())
        assert resp.status_code == 409

    def test_invalid_hex_color_422s(self, client, scoped):
        resp = client.post("/api/clientes/tags", json={"nome": "X", "cor": "red"}, headers=_auth())
        assert resp.status_code == 422

    def test_set_cliente_tags_full_replace(self, client, scoped):
        cid = str(uuid4())
        t1, t2 = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("cliente_tags", [tag_row(t1, nome="A"), tag_row(t2, nome="B")])

        resp = client.put(f"/api/clientes/{cid}/tags", json={"tag_ids": [t1, t2]}, headers=_auth())
        assert resp.status_code == 200, resp.text
        assert {t["id"] for t in resp.json()["items"]} == {t1, t2}

        # Full replace — dropping t2 removes it, not additive.
        resp = client.put(f"/api/clientes/{cid}/tags", json={"tag_ids": [t1]}, headers=_auth())
        assert resp.status_code == 200
        assert {t["id"] for t in resp.json()["items"]} == {t1}

    def test_set_cliente_tags_unknown_tag_404s(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.put(f"/api/clientes/{cid}/tags", json={"tag_ids": [str(uuid4())]}, headers=_auth())
        assert resp.status_code == 404


class TestMembros:
    def test_set_and_get_membros(self, client, scoped):
        cid = str(uuid4())
        c1, c2 = str(uuid4()), str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("lead_corretores", [corretor_row(c1, nome="Bia"), corretor_row(c2, nome="Caio")])

        resp = client.put(f"/api/clientes/{cid}/membros", json={"lead_corretor_ids": [c1, c2]}, headers=_auth())
        assert resp.status_code == 200, resp.text
        assert {m["id"] for m in resp.json()["items"]} == {c1, c2}

        resp = client.get(f"/api/clientes/{cid}/membros", headers=_auth())
        assert resp.status_code == 200
        assert {m["id"] for m in resp.json()["items"]} == {c1, c2}

    def test_set_membros_unknown_corretor_404s(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.put(f"/api/clientes/{cid}/membros", json={"lead_corretor_ids": [str(uuid4())]}, headers=_auth())
        assert resp.status_code == 404
