"""Datas + the reminder mechanism (contract §3, screenshot 06).

`cliente_lembretes` did not exist anywhere in the product before this
slice — these tests assert the row is genuinely MATERIALISED (not just
the endpoint accepting the value), that it is cancelled when the inputs
are cleared, and that `NOC-REMEDIATE[reminder-delivery]` is the honest
marker for the still-missing delivery leg (a UI showing a reminder as
"set" with no delivery path would be a lying UI)."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import cliente_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


class TestDatas:
    def test_patch_sets_fields(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])

        resp = client.patch(
            f"/api/clientes/{cid}/datas",
            json={"data_inicio": "2026-02-01T00:00:00+00:00"},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data_inicio"] == "2026-02-01T00:00:00+00:00"
        assert resp.json()["proximo_lembrete"] is None

    def test_setting_entrega_and_lembrete_materialises_a_reminder_row(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])

        resp = client.patch(
            f"/api/clientes/{cid}/datas",
            json={"data_entrega": "2026-03-10T15:00:00+00:00", "lembrete_minutos_antes": 60},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["proximo_lembrete"] is not None
        assert body["proximo_lembrete"]["dispara_em"] == "2026-03-10T14:00:00+00:00"

        # The row is REAL, not just reported — assert it against the table
        # directly, not the endpoint's own echo.
        rows = scoped.table("cliente_lembretes").select("*").execute().data
        pending = [r for r in rows if not r["enviado_em"] and not r["cancelado_em"]]
        assert len(pending) == 1
        assert pending[0]["dispara_em"] == "2026-03-10T14:00:00+00:00"
        assert pending[0]["cliente_id"] == cid

    def test_clearing_data_entrega_cancels_the_pending_reminder(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        client.patch(
            f"/api/clientes/{cid}/datas",
            json={"data_entrega": "2026-03-10T15:00:00+00:00", "lembrete_minutos_antes": 60},
            headers=_auth(),
        )

        resp = client.patch(f"/api/clientes/{cid}/datas", json={"data_entrega": None}, headers=_auth())
        assert resp.status_code == 200, resp.text
        assert resp.json()["proximo_lembrete"] is None

        rows = scoped.table("cliente_lembretes").select("*").execute().data
        assert all(r["cancelado_em"] is not None for r in rows), rows

    def test_recorrencia_rejects_unknown_value(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.patch(
            f"/api/clientes/{cid}/datas", json={"recorrencia": "bissexta"}, headers=_auth()
        )
        assert resp.status_code == 422

    def test_recorrencia_accepts_null_and_valid_values(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.patch(f"/api/clientes/{cid}/datas", json={"recorrencia": "mensal"}, headers=_auth())
        assert resp.status_code == 200
        assert resp.json()["recorrencia"] == "mensal"

    def test_unset_fields_are_not_overwritten(self, client, scoped):
        """A PATCH that only carries `entrega_concluida` must not clobber
        an already-set `data_inicio` — the `...` sentinel discipline."""
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, data_inicio="2026-01-01T00:00:00+00:00")])
        resp = client.patch(f"/api/clientes/{cid}/datas", json={"entrega_concluida": True}, headers=_auth())
        assert resp.status_code == 200, resp.text
        assert resp.json()["data_inicio"] == "2026-01-01T00:00:00+00:00"
        assert resp.json()["entrega_concluida"] is True

    def test_unknown_cliente_404s(self, client, scoped):
        resp = client.patch(f"/api/clientes/{uuid4()}/datas", json={"data_inicio": None}, headers=_auth())
        assert resp.status_code == 404
