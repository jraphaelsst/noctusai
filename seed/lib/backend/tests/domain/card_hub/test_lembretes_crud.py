"""The ad-hoc lembretes CRUD (`lembretes_crud` opt-in) — list/create/edit/
mark-done/delete, mounted behind `CardHubConfig.lembretes_crud` so
social-wiring (flag off) never gains routes its `lembretes` table has no
columns for."""
from __future__ import annotations

from uuid import uuid4

from tests.domain.card_hub.conftest import AUTH, ORG_ID


class TestOptOutByDefault:
    def test_the_routes_do_not_exist_when_the_flag_is_off(self, hub):
        """Both parametrizations of the plain `hub` fixture (`lead`, `sw`)
        default `lembretes_crud=False` — a 404, never a raw missing-column
        DB error, for a product that has not opted in."""
        eid = hub.new_entity()
        resp = hub.client.get(hub.url(eid, "/lembretes"), headers=AUTH)
        assert resp.status_code == 404


class TestListAndCreate:
    def test_create_requires_titulo_and_dispara_em(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        resp = hub.client.post(
            hub.url(eid, "/lembretes"),
            json={"titulo": "Ligar para o cliente", "dispara_em": "2026-10-01T14:00:00-03:00"},
            headers=AUTH,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["titulo"] == "Ligar para o cliente"
        assert body["dispara_em"] == "2026-10-01T17:00:00+00:00"
        assert body["concluido"] is False
        assert body["concluido_em"] is None
        assert body["responsavel"] is None

    def test_an_unknown_field_is_a_strict_422(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        resp = hub.client.post(
            hub.url(eid, "/lembretes"),
            json={"titulo": "X", "dispara_em": "2026-10-01T14:00:00-03:00", "canal": "email"},
            headers=AUTH,
        )
        assert resp.status_code == 422

    def test_create_with_a_responsavel(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        member_id = str(uuid4())
        hub.seed(hub.cfg.member_source.table, [hub.member_row(member_id, nome="Bia")])
        resp = hub.client.post(
            hub.url(eid, "/lembretes"),
            json={"titulo": "X", "dispara_em": "2026-10-01T14:00:00-03:00", "responsavel_id": member_id},
            headers=AUTH,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["responsavel"] == {"id": member_id, "nome": "Bia", "cor": "#00ff00"}

    def test_an_unknown_responsavel_is_a_404_naming_the_member_table(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        resp = hub.client.post(
            hub.url(eid, "/lembretes"),
            json={"titulo": "X", "dispara_em": "2026-10-01T14:00:00-03:00", "responsavel_id": str(uuid4())},
            headers=AUTH,
        )
        assert resp.status_code == 404
        assert hub.cfg.member_source.table in resp.text

    def test_list_is_ordered_by_dispara_em_and_excludes_cancelled(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        l1 = str(uuid4())
        l2 = str(uuid4())
        cancelado = str(uuid4())
        hub.seed(hub.cfg.tables.lembretes, [
            hub.lembrete_row(l2, eid, titulo="Depois", dispara_em="2026-02-01T00:00:00+00:00"),
            hub.lembrete_row(l1, eid, titulo="Antes", dispara_em="2026-01-01T00:00:00+00:00"),
            hub.lembrete_row(cancelado, eid, titulo="Cancelado", cancelado_em="2026-01-01T00:00:00+00:00"),
        ])
        resp = hub.client.get(hub.url(eid, "/lembretes"), headers=AUTH)
        assert resp.status_code == 200
        assert [item["titulo"] for item in resp.json()["items"]] == ["Antes", "Depois"]
        assert resp.json()["total"] == 2

    def test_an_already_delivered_reminder_lists_as_concluido(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        lid = str(uuid4())
        hub.seed(hub.cfg.tables.lembretes, [
            hub.lembrete_row(lid, eid, enviado_em="2026-01-05T00:00:00+00:00"),
        ])
        item = hub.client.get(hub.url(eid, "/lembretes"), headers=AUTH).json()["items"][0]
        assert item["concluido"] is True
        assert item["concluido_em"] == "2026-01-05T00:00:00+00:00"


class TestUpdate:
    def _criar(self, hub, eid, **over):
        payload = {"titulo": "Original", "dispara_em": "2026-10-01T14:00:00-03:00", **over}
        return hub.client.post(hub.url(eid, "/lembretes"), json=payload, headers=AUTH).json()

    def test_edit_titulo_and_data(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        lembrete = self._criar(hub, eid)
        resp = hub.client.patch(
            hub.url(eid, f"/lembretes/{lembrete['id']}"),
            json={"titulo": "Editado", "dispara_em": "2026-11-01T09:00:00-03:00"},
            headers=AUTH,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["titulo"] == "Editado"
        assert resp.json()["dispara_em"] == "2026-11-01T12:00:00+00:00"

    def test_mark_done_sets_concluido_without_a_body_change_to_titulo(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        lembrete = self._criar(hub, eid)
        resp = hub.client.patch(
            hub.url(eid, f"/lembretes/{lembrete['id']}"), json={"concluido": True}, headers=AUTH
        )
        assert resp.status_code == 200
        assert resp.json()["concluido"] is True
        assert resp.json()["concluido_em"] is not None
        assert resp.json()["titulo"] == "Original"

    def test_reopening_clears_concluido_em(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        lembrete = self._criar(hub, eid)
        hub.client.patch(hub.url(eid, f"/lembretes/{lembrete['id']}"), json={"concluido": True}, headers=AUTH)
        resp = hub.client.patch(
            hub.url(eid, f"/lembretes/{lembrete['id']}"), json={"concluido": False}, headers=AUTH
        )
        assert resp.status_code == 200
        assert resp.json()["concluido"] is False
        assert resp.json()["concluido_em"] is None

    def test_setting_a_responsavel_then_clearing_it(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        member_id = str(uuid4())
        hub.seed(hub.cfg.member_source.table, [hub.member_row(member_id, nome="Bia")])
        lembrete = self._criar(hub, eid)

        resp = hub.client.patch(
            hub.url(eid, f"/lembretes/{lembrete['id']}"), json={"responsavel_id": member_id}, headers=AUTH
        )
        assert resp.json()["responsavel"]["id"] == member_id

        # explicit null clears it; an ABSENT field (below) leaves it alone.
        resp = hub.client.patch(
            hub.url(eid, f"/lembretes/{lembrete['id']}"), json={"responsavel_id": None}, headers=AUTH
        )
        assert resp.status_code == 200
        assert resp.json()["responsavel"] is None

        resp = hub.client.patch(
            hub.url(eid, f"/lembretes/{lembrete['id']}"), json={"titulo": "Sem mudar responsável"}, headers=AUTH
        )
        assert resp.json()["responsavel"] is None

    def test_editing_an_unknown_lembrete_is_404(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        resp = hub.client.patch(
            hub.url(eid, f"/lembretes/{uuid4()}"), json={"titulo": "X"}, headers=AUTH
        )
        assert resp.status_code == 404

    def test_the_404_names_lembrete_not_the_raw_table(self, lead_lembretes_hub):
        """"Lembrete não encontrado" — never the raw `cliente_lembretes` /
        `negocio_lembretes` / `lead_lembretes` table name a user never typed
        or chose."""
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        resp = hub.client.patch(
            hub.url(eid, f"/lembretes/{uuid4()}"), json={"titulo": "X"}, headers=AUTH
        )
        body = resp.json()
        assert body["error"]["message"] == "Lembrete não encontrado"
        assert body["error"]["details"]["resource"] == "Lembrete"
        assert hub.cfg.tables.lembretes not in body["error"]["message"]


class TestDelete:
    def test_delete_removes_the_row(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        lembrete = hub.client.post(
            hub.url(eid, "/lembretes"),
            json={"titulo": "X", "dispara_em": "2026-10-01T14:00:00-03:00"},
            headers=AUTH,
        ).json()
        resp = hub.client.delete(hub.url(eid, f"/lembretes/{lembrete['id']}"), headers=AUTH)
        assert resp.status_code == 204
        assert hub.client.get(hub.url(eid, "/lembretes"), headers=AUTH).json()["total"] == 0

    def test_deleting_an_unknown_lembrete_is_404(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        resp = hub.client.delete(hub.url(eid, f"/lembretes/{uuid4()}"), headers=AUTH)
        assert resp.status_code == 404


class TestAuthBoundary:
    def test_every_lembrete_route_is_strict_401(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = str(uuid4())
        lid = str(uuid4())
        calls = [
            ("GET", hub.url(eid, "/lembretes")),
            ("POST", hub.url(eid, "/lembretes")),
            ("PATCH", hub.url(eid, f"/lembretes/{lid}")),
            ("DELETE", hub.url(eid, f"/lembretes/{lid}")),
        ]
        for method, url in calls:
            resp = hub.anon.request(method, url)
            assert resp.status_code == 401, f"{method} {url} -> {resp.status_code}"


class TestCrossOrgIsolation:
    def test_a_lembrete_from_another_org_is_a_404(self, lead_lembretes_hub):
        hub = lead_lembretes_hub
        eid = hub.new_entity()
        outro_org_lembrete = str(uuid4())
        row = hub.lembrete_row(outro_org_lembrete, eid)
        row["org_id"] = "11111111-1111-1111-1111-111111111111"
        hub.seed(hub.cfg.tables.lembretes, [row])
        resp = hub.client.get(hub.url(eid, "/lembretes"), headers=AUTH)
        assert resp.json()["total"] == 0
        assert ORG_ID != row["org_id"]
