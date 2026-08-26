"""Corretores CRUD + alias map — /api/leads/corretores/*. Mirrors
``test_sources_router.py``; extra coverage for ``lead_count`` (§5.2)."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.leads.conftest import ORG_A, auth_headers


def _create_corretor(client, **overrides):
    body = {"nome": "Fulano"}
    body.update(overrides)
    resp = client.post("/api/leads/corretores", json=body, headers=auth_headers())
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestCorretoresCRUD:
    def test_list_empty(self, http_client):
        resp = http_client.get("/api/leads/corretores", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_lead_count_comes_from_the_grouped_view(self, http_client, leads_client):
        """`lead_count` is read from `vw_lead_corretor_contagem` (080), one
        query for every broker, not one COUNT each.

        🔴 THIS TEST IS WEAKER THAN THE ONE IT REPLACES, AND THE REASON IS
        WORTH STATING. It used to create a real lead and assert the count
        followed. Since 080 the aggregation happens in a database VIEW, and the
        test double cannot evaluate SQL — so the view's rows are seeded here
        and this asserts only that the endpoint JOINS them onto the right
        broker. That the view's own SQL is correct was verified against the
        live database when 080 was applied, which is the only place it can
        honestly be checked.

        What this still catches, and what actually broke in the rewrite: the
        id-type mismatch. `corretor_id` arrives from PostgREST as a string and
        `r["id"]` may not be — a dict keyed on one and looked up with the other
        silently reports 0 for every broker.
        """
        created = _create_corretor(http_client)
        leads_client.set_table_data(
            "vw_lead_corretor_contagem",
            [{"corretor_id": created["id"], "org_id": ORG_A, "lead_count": 7}],
        )

        resp = http_client.get("/api/leads/corretores", headers=auth_headers())

        assert resp.json()["data"][0]["lead_count"] == 7

    def test_a_broker_absent_from_the_view_reports_zero_not_missing(
        self, http_client, leads_client
    ):
        """The view LEFT JOINs, so this should not happen — but if it ever
        does, a broker with a wrong count is a much smaller failure than a
        broker that disappears from the list."""
        _create_corretor(http_client)
        leads_client.set_table_data("vw_lead_corretor_contagem", [])

        data = http_client.get(
            "/api/leads/corretores", headers=auth_headers()
        ).json()["data"]

        assert len(data) == 1
        assert data[0]["lead_count"] == 0

    def test_update_nome(self, http_client):
        created = _create_corretor(http_client)
        resp = http_client.patch(
            f"/api/leads/corretores/{created['id']}",
            json={"nome": "Renamed"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["nome"] == "Renamed"
        assert resp.json()["data"]["nome_norm"] == "RENAMED"

    def test_update_nonexistent_404(self, http_client):
        resp = http_client.patch(
            f"/api/leads/corretores/{uuid4()}", json={"nome": "X"}, headers=auth_headers()
        )
        assert resp.status_code == 404

    def test_delete_referenced_409_then_reassign(self, http_client):
        a = _create_corretor(http_client, nome="A")
        b = _create_corretor(http_client, nome="B")
        lead = http_client.post(
            "/api/leads",
            json={"data_entrada": "2026-07-01", "corretor_id": a["id"]},
            headers=auth_headers(),
        ).json()["data"]

        blocked = http_client.delete(f"/api/leads/corretores/{a['id']}", headers=auth_headers())
        assert blocked.status_code == 409

        reassigned = http_client.delete(
            f"/api/leads/corretores/{a['id']}",
            params={"reassign_to": b["id"]},
            headers=auth_headers(),
        )
        assert reassigned.status_code == 200

        refreshed = http_client.get(f"/api/leads/{lead['id']}", headers=auth_headers()).json()["data"]
        assert refreshed["corretor_id"] == b["id"]


class TestCorretorAliases:
    def test_create_and_list_alias(self, http_client):
        corretor = _create_corretor(http_client)
        resp = http_client.post(
            "/api/leads/corretores/aliases",
            json={"alias": "FULANO TYPO", "corretor_id": corretor["id"]},
            headers=auth_headers(),
        )
        assert resp.status_code == 201
        listed = http_client.get("/api/leads/corretores/aliases", headers=auth_headers())
        assert len(listed.json()["data"]) == 1

    def test_create_alias_unknown_corretor_404(self, http_client):
        resp = http_client.post(
            "/api/leads/corretores/aliases",
            json={"alias": "X", "corretor_id": str(uuid4())},
            headers=auth_headers(),
        )
        assert resp.status_code == 404

    def test_delete_alias_nonexistent_404(self, http_client):
        resp = http_client.delete(
            f"/api/leads/corretores/aliases/{uuid4()}", headers=auth_headers()
        )
        assert resp.status_code == 404
