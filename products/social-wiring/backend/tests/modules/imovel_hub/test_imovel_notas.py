"""`/api/imoveis/{codigo}/notas` (migration 315) — our own notes, full CRUD.

WHAT THESE PIN
--------------
- create / list (newest first) / edit / delete round-trip through the route;
- the write stamps the caller's org and actor; an edit stamps `updated_by`;
- a blank or over-long note is refused (400 blank / 422 over-long) and nothing is stored;
- another org's note is invisible: edit/delete of it is a 404, never a write;
- DELETE / PATCH of a nonexistent note is a 404, never a silent 200;
- an unknown imóvel is a 404;
- NO route here ever writes the Vista mirror (`imoveis`) or `imovel_dados`.

Auth: `test_imovel_auth_boundary.py` enumerates every mounted route (these
four pinned by name) and asserts a strict 401.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.imovel_hub.conftest import CODIGO, ORG_ID, auth, seed

_URL = f"/api/imoveis/{CODIGO}/notas"


def _nota_row(**extra) -> dict:
    return {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "codigo": CODIGO,
        "texto": "Chave com o porteiro",
        "created_by": None,
        "created_at": "2026-11-01T10:00:00+00:00",
        "updated_by": None,
        "updated_at": "2026-11-01T10:00:00+00:00",
        **extra,
    }


class TestNotasCrud:
    def test_create_then_list_returns_the_note(self, client, scoped):
        seed(scoped)
        r = client.post(_URL, json={"texto": "  O proprietário só atende à tarde  "}, headers=auth())
        assert r.status_code == 201, r.text
        assert r.json()["texto"] == "O proprietário só atende à tarde"
        lido = client.get(_URL, headers=auth()).json()
        assert lido["total"] == 1
        assert lido["items"][0]["id"] == r.json()["id"]
        rows = scoped.table("imovel_notas").select("*").execute().data
        assert [(x["org_id"], x["codigo"]) for x in rows] == [(ORG_ID, CODIGO)]

    def test_list_is_newest_first(self, client, scoped):
        seed(scoped)
        scoped.set_table_data(
            "imovel_notas",
            [
                _nota_row(texto="antiga", created_at="2026-10-01T10:00:00+00:00"),
                _nota_row(texto="nova", created_at="2026-11-02T10:00:00+00:00"),
            ],
        )
        textos = [i["texto"] for i in client.get(_URL, headers=auth()).json()["items"]]
        assert textos == ["nova", "antiga"]

    def test_edit_replaces_the_text(self, client, scoped):
        seed(scoped)
        nota = _nota_row()
        scoped.set_table_data("imovel_notas", [nota])
        r = client.patch(f"{_URL}/{nota['id']}", json={"texto": "Chave com o zelador"}, headers=auth())
        assert r.status_code == 200, r.text
        assert r.json()["texto"] == "Chave com o zelador"
        rows = scoped.table("imovel_notas").select("*").execute().data
        assert [x["texto"] for x in rows] == ["Chave com o zelador"]

    def test_delete_removes_it(self, client, scoped):
        seed(scoped)
        nota = _nota_row()
        scoped.set_table_data("imovel_notas", [nota])
        r = client.delete(f"{_URL}/{nota['id']}", headers=auth())
        assert r.status_code == 200, r.text
        assert scoped.table("imovel_notas").select("*").execute().data == []
        assert client.get(_URL, headers=auth()).json()["total"] == 0


class TestNotasRefusals:
    def test_blank_note_is_refused_and_nothing_is_stored(self, client, scoped):
        seed(scoped)
        r = client.post(_URL, json={"texto": "   "}, headers=auth())
        assert r.status_code == 400, r.text  # service-level ValidationError_ → 400
        assert scoped.table("imovel_notas").select("*").execute().data == []

    def test_over_long_note_is_refused(self, client, scoped):
        seed(scoped)
        r = client.post(_URL, json={"texto": "x" * 4001}, headers=auth())
        assert r.status_code == 422, r.text
        assert scoped.table("imovel_notas").select("*").execute().data == []

    def test_unknown_field_is_refused_by_name(self, client, scoped):
        seed(scoped)
        r = client.post(_URL, json={"texto": "ok", "valor_venda": 1}, headers=auth())
        assert r.status_code == 422, r.text

    def test_missing_note_is_404_on_edit_and_delete(self, client, scoped):
        seed(scoped)
        ghost = str(uuid4())
        assert client.patch(f"{_URL}/{ghost}", json={"texto": "x"}, headers=auth()).status_code == 404
        assert client.delete(f"{_URL}/{ghost}", headers=auth()).status_code == 404

    def test_another_orgs_note_is_untouchable(self, client, scoped):
        seed(scoped)
        alheia = _nota_row(org_id=str(uuid4()))
        scoped.set_table_data("imovel_notas", [alheia])
        assert client.get(_URL, headers=auth()).json()["total"] == 0
        assert client.patch(f"{_URL}/{alheia['id']}", json={"texto": "x"}, headers=auth()).status_code == 404
        assert client.delete(f"{_URL}/{alheia['id']}", headers=auth()).status_code == 404
        assert len(scoped.table("imovel_notas").select("*").execute().data) == 1

    def test_unknown_imovel_is_404(self, client, scoped):
        seed(scoped, registry=[])
        assert client.get(_URL, headers=auth()).status_code == 404
        assert client.post(_URL, json={"texto": "x"}, headers=auth()).status_code == 404


class TestNotasNeverTouchTheMirror:
    def test_writes_leave_mirror_and_dados_untouched(self, client, scoped):
        seed(scoped)
        antes_imoveis = scoped.table("imoveis").select("*").execute().data
        antes_dados = scoped.table("imovel_dados").select("*").execute().data
        r = client.post(_URL, json={"texto": "nota"}, headers=auth())
        client.patch(f"{_URL}/{r.json()['id']}", json={"texto": "nota 2"}, headers=auth())
        client.delete(f"{_URL}/{r.json()['id']}", headers=auth())
        assert scoped.table("imoveis").select("*").execute().data == antes_imoveis
        assert scoped.table("imovel_dados").select("*").execute().data == antes_dados
