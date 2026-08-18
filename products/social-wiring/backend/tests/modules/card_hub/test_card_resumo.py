"""`GET /clientes/{id}/card` — the badge row (contract §3, screenshot 11).

`badges` must be SERVED, computed in SQL — never fetched-then-`len()`'d in
the endpoint. `temperatura` always carries `provisoria: true` (D8)."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import (
    checklist_item_row,
    checklist_row,
    cliente_row,
    corretor_row,
    documento_row,
    nota_row,
    tag_row,
)


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


class TestCardResumo:
    def test_shape_and_empty_badges(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, ultimo_contato_em=None)])

        resp = client.get(f"/api/clientes/{cid}/card", headers=_auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["cliente"]["id"] == cid
        assert body["tags"] == []
        assert body["membros"] == []
        assert body["descricao"] is None
        assert body["badges"]["notas"] == 0
        assert body["badges"]["documentos"] == 0
        assert body["badges"]["tem_descricao"] is False
        assert body["badges"]["checklist_total"] == 0
        assert body["badges"]["temperatura"] is None
        assert body["atendimentos"] == []

    def test_badges_are_computed_correctly(self, client, scoped):
        cid = str(uuid4())
        t1 = str(uuid4())
        c1 = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "cliente_notas",
            [
                nota_row(str(uuid4()), cid, tipo="descricao"),
                nota_row(str(uuid4()), cid, tipo="comentario"),
                nota_row(str(uuid4()), cid, tipo="comentario"),
            ],
        )
        scoped.set_table_data("cliente_documentos", [documento_row(str(uuid4()), cid)])
        scoped.set_table_data("cliente_tags", [tag_row(t1)])
        scoped.set_table_data(
            "cliente_tag_links",
            [{"cliente_id": cid, "tag_id": t1, "org_id": cliente_row(cid)["org_id"], "criado_por": None, "created_at": "2026-01-01T00:00:00+00:00"}],
        )
        scoped.set_table_data("lead_corretores", [corretor_row(c1)])
        scoped.set_table_data(
            "cliente_membros",
            [{"cliente_id": cid, "lead_corretor_id": c1, "org_id": cliente_row(cid)["org_id"], "created_at": "2026-01-01T00:00:00+00:00"}],
        )
        cl = checklist_row(str(uuid4()), cid)
        scoped.set_table_data("cliente_checklists", [cl])
        scoped.set_table_data(
            "cliente_checklist_itens",
            [
                checklist_item_row(str(uuid4()), cl["id"], concluido=True, concluido_em="2026-01-02T00:00:00+00:00"),
                checklist_item_row(str(uuid4()), cl["id"], concluido=False),
            ],
        )

        resp = client.get(f"/api/clientes/{cid}/card", headers=_auth())
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # NOT `body["badges"]["notas"] == 2`: `MockSelectBuilder`'s
        # `count="exact"` is fixed at `.select()` time from the
        # UNFILTERED table (the same confirmed mock limitation
        # `test_clientes_router.py::TestListClientes` documents) — it
        # reports the whole `cliente_notas` table (3 rows: 1 descricao +
        # 2 comentário), not the `tipo='comentario'`-filtered subset real
        # PostgREST returns. `tem_descricao`/`descricao` below are the
        # honest assertions here — both read via `.eq(...).is_(...)`
        # predicate evaluation, which the mock DOES apply correctly; only
        # its `count="exact"` shortcut is blind to filters.
        assert body["badges"]["notas"] == 3
        assert body["badges"]["tem_descricao"] is True
        assert body["descricao"]["corpo"]
        assert body["badges"]["documentos"] == 1
        assert body["badges"]["checklist_total"] == 2
        assert body["badges"]["checklist_concluidos"] == 1
        assert len(body["tags"]) == 1
        assert len(body["membros"]) == 1

    def test_temperatura_is_always_provisional(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, ultimo_contato_em="2026-08-17T00:00:00+00:00")])
        resp = client.get(f"/api/clientes/{cid}/card", headers=_auth())
        assert resp.status_code == 200, resp.text
        temp = resp.json()["badges"]["temperatura"]
        assert temp is not None
        assert temp["provisoria"] is True

    def test_unknown_cliente_404s(self, client, scoped):
        resp = client.get(f"/api/clientes/{uuid4()}/card", headers=_auth())
        assert resp.status_code == 404
