"""CRUD round-trip + the canonical filter set (§5.1) — multiple values of
ONE param OR together, different params AND together."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.leads.conftest import ORG_A, ORG_B, auth_headers


def _create_lead(client, **overrides):
    body = {"data_entrada": "2026-07-01", "cliente_nome": "Alice"}
    body.update(overrides)
    resp = client.post("/api/leads", json=body, headers=auth_headers())
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


class TestCRUD:
    def test_create_returns_201_with_envelope(self, http_client):
        data = _create_lead(http_client, cliente_nome="Bob")
        assert data["cliente_nome"] == "Bob"
        assert data["needs_review"] is False
        assert data["tipo_lead"] == "desconhecido"
        assert "id" in data

    def test_create_forbidden_fields_422(self, http_client):
        resp = http_client.post(
            "/api/leads",
            json={"data_entrada": "2026-07-01", "unknown_field": True},
            headers=auth_headers(),
        )
        assert resp.status_code == 422

    def test_get_by_id(self, http_client):
        created = _create_lead(http_client)
        resp = http_client.get(f"/api/leads/{created['id']}", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == created["id"]

    def test_get_nonexistent_404(self, http_client):
        resp = http_client.get(f"/api/leads/{uuid4()}", headers=auth_headers())
        assert resp.status_code == 404

    def test_update_field(self, http_client):
        created = _create_lead(http_client)
        resp = http_client.patch(
            f"/api/leads/{created['id']}",
            json={"cliente_nome": "Updated"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["cliente_nome"] == "Updated"

    def test_update_nonexistent_404(self, http_client):
        resp = http_client.patch(
            f"/api/leads/{uuid4()}", json={"cliente_nome": "X"}, headers=auth_headers()
        )
        assert resp.status_code == 404

    def test_delete_existing(self, http_client):
        created = _create_lead(http_client)
        resp = http_client.delete(f"/api/leads/{created['id']}", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["deleted_id"] == created["id"]

    def test_delete_nonexistent_404(self, http_client):
        resp = http_client.delete(f"/api/leads/{uuid4()}", headers=auth_headers())
        assert resp.status_code == 404

    def test_list_paginated_envelope(self, http_client):
        _create_lead(http_client)
        _create_lead(http_client)
        resp = http_client.get("/api/leads", headers=auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body and "pagination" in body
        assert body["pagination"]["total"] == 2
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 50


class TestFilters:
    def test_ano_or_within_dimension(self, http_client):
        _create_lead(http_client, data_entrada="2025-03-01", cliente_nome="OldYear")
        _create_lead(http_client, data_entrada="2026-07-01", cliente_nome="NewYear")
        _create_lead(http_client, data_entrada="2024-01-01", cliente_nome="Ancient")

        resp = http_client.get(
            "/api/leads", params=[("ano", 2025), ("ano", 2026)], headers=auth_headers()
        )
        assert resp.status_code == 200
        names = {r["cliente_nome"] for r in resp.json()["data"]}
        assert names == {"OldYear", "NewYear"}

    def test_tipo_and_tier_and_together(self, http_client):
        _create_lead(http_client, tipo_lead="novo", anuncio_tier="simples", cliente_nome="A")
        _create_lead(http_client, tipo_lead="novo", anuncio_tier="destaque", cliente_nome="B")
        _create_lead(http_client, tipo_lead="retorno", anuncio_tier="simples", cliente_nome="C")

        resp = http_client.get(
            "/api/leads",
            params={"tipo": "novo", "tier": "simples"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        names = {r["cliente_nome"] for r in resp.json()["data"]}
        assert names == {"A"}

    def test_de_ate_range(self, http_client):
        _create_lead(http_client, data_entrada="2026-01-01", cliente_nome="Before")
        _create_lead(http_client, data_entrada="2026-06-15", cliente_nome="Inside")
        _create_lead(http_client, data_entrada="2026-12-31", cliente_nome="After")

        resp = http_client.get(
            "/api/leads",
            params={"de": "2026-06-01", "ate": "2026-06-30"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200
        names = {r["cliente_nome"] for r in resp.json()["data"]}
        assert names == {"Inside"}

    def test_q_free_text_over_multiple_columns(self, http_client):
        _create_lead(http_client, cliente_nome="Zebra Corp", observacoes="nothing special")
        _create_lead(http_client, cliente_nome="Other", observacoes="mentions zebra here")
        _create_lead(http_client, cliente_nome="Unrelated", observacoes="nothing")

        resp = http_client.get("/api/leads", params={"q": "zebra"}, headers=auth_headers())
        assert resp.status_code == 200
        names = {r["cliente_nome"] for r in resp.json()["data"]}
        assert names == {"Zebra Corp", "Other"}

    def test_needs_review_filter(self, http_client):
        _create_lead(http_client, cliente_nome="Flagged")
        flagged_id = None
        resp = http_client.get("/api/leads", headers=auth_headers())
        for row in resp.json()["data"]:
            if row["cliente_nome"] == "Flagged":
                flagged_id = row["id"]
        http_client.patch(
            f"/api/leads/{flagged_id}", json={"needs_review": True}, headers=auth_headers()
        )
        _create_lead(http_client, cliente_nome="Clean")

        resp = http_client.get(
            "/api/leads", params={"needs_review": True}, headers=auth_headers()
        )
        assert resp.status_code == 200
        names = {r["cliente_nome"] for r in resp.json()["data"]}
        assert names == {"Flagged"}

    def test_unknown_param_ignored_not_422(self, http_client):
        resp = http_client.get(
            "/api/leads", params={"totally_unknown_param": "x"}, headers=auth_headers()
        )
        assert resp.status_code == 200


class TestBlankStringDateCoercion:
    """The FE form posts `""` for an empty date input — the fix is a
    `field_validator(mode="before")` coercing `""`/whitespace -> `None`
    (`schemas._blank_to_none`), tested here at the full HTTP boundary."""

    def test_create_with_blank_follow_up_data_is_not_422(self, http_client):
        resp = http_client.post(
            "/api/leads",
            json={"data_entrada": "2026-07-01", "follow_up_data": ""},
            headers=auth_headers(),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["data"]["follow_up_data"] is None

    def test_update_with_blank_data_entrada_is_not_422_and_ignored(self, http_client):
        """`data_entrada` is `NOT NULL` — a blank-coerced-to-None patch
        value has no valid applied state and is dropped (not a 422, not
        a DB constraint violation)."""
        created = _create_lead(http_client)
        resp = http_client.patch(
            f"/api/leads/{created['id']}",
            json={"data_entrada": "", "cliente_nome": "Still Works"},
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["cliente_nome"] == "Still Works"
        assert resp.json()["data"]["data_entrada"] == created["data_entrada"]

    def test_update_with_blank_follow_up_data_clears_it(self, http_client):
        created = _create_lead(http_client, follow_up_data="2026-08-01")
        resp = http_client.patch(
            f"/api/leads/{created['id']}",
            json={"follow_up_data": ""},
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["follow_up_data"] is None


class TestExplicitNullClear:
    """`PATCH` with an explicit `null` genuinely clears a nullable field
    now (dropping the old `is not None` filter) — un-assigning a
    corretor previously showed a false-success toast with nothing
    actually changed."""

    def test_explicit_null_unassigns_corretor(self, http_client):
        corretor_resp = http_client.post(
            "/api/leads/corretores", json={"nome": "Fulano"}, headers=auth_headers()
        )
        corretor_id = corretor_resp.json()["data"]["id"]
        created = _create_lead(http_client, corretor_id=corretor_id)
        assert created["corretor_id"] == corretor_id

        resp = http_client.patch(
            f"/api/leads/{created['id']}",
            json={"corretor_id": None},
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["corretor_id"] is None
        assert resp.json()["data"]["corretor"] is None


class TestNeedsReviewAutoClear:
    """Setting `origem_id` to a real value auto-clears `needs_review` —
    its only cause is an unrecognized/blank origem — regardless of
    whether `needs_review` is also present in the same payload."""

    def test_setting_origem_id_clears_needs_review(self, http_client):
        created = _create_lead(http_client)
        http_client.patch(
            f"/api/leads/{created['id']}", json={"needs_review": True}, headers=auth_headers()
        )
        source_resp = http_client.post(
            "/api/leads/sources", json={"label": "Alguma Origem"}, headers=auth_headers()
        )
        source_id = source_resp.json()["data"]["id"]

        resp = http_client.patch(
            f"/api/leads/{created['id']}",
            json={"origem_id": source_id},
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["needs_review"] is False

    def test_origem_id_clear_overrides_an_explicit_needs_review_true_in_the_same_payload(
        self, http_client
    ):
        created = _create_lead(http_client)
        source_resp = http_client.post(
            "/api/leads/sources", json={"label": "Outra Origem"}, headers=auth_headers()
        )
        source_id = source_resp.json()["data"]["id"]

        resp = http_client.patch(
            f"/api/leads/{created['id']}",
            json={"origem_id": source_id, "needs_review": True},
            headers=auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["needs_review"] is False


class TestOrgIsolation:
    def test_list_only_own_org(self, http_client, mock_db):
        from unittest.mock import MagicMock

        from noctusai_lib.testing import MockUser, MockUserResponse

        mock_db.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(org_id=ORG_B))
        )
        resp_b = http_client.post(
            "/api/leads", json={"data_entrada": "2026-07-01", "cliente_nome": "OrgB"},
            headers=auth_headers(),
        )
        assert resp_b.status_code == 201

        mock_db.auth.get_user = MagicMock(
            return_value=MockUserResponse(MockUser(org_id=ORG_A))
        )
        resp_a = http_client.get("/api/leads", headers=auth_headers())
        names = {r["cliente_nome"] for r in resp_a.json()["data"]}
        assert "OrgB" not in names


class TestCreateSchedulesPersonLayerSweep:
    """🔴 A created lead must become WORKABLE, not merely visible.

    Migration 034's trigger spawns the funil card on insert, but
    `atendimentos.cliente_id` is attached by `clientes_backfill` — and that
    was an interval job with no trigger and no on-demand path. So the card
    appeared and then `stage_gate` refused to move it, for up to
    `clientes_backfill_interval_hours`, while the operator looked at the name
    and phone they had just typed (found in prod 2026-08-31). Creating the
    lead now schedules the sweep.
    """

    def test_create_schedules_the_sweep(self, http_client):
        from app.main import app
        from app.modules.leads.routers.leads import get_person_layer_sweep

        ran: list = []
        app.dependency_overrides[get_person_layer_sweep] = lambda: (
            lambda: ran.append(True)
        )
        try:
            resp = http_client.post(
                "/api/leads",
                json={"data_entrada": "2026-07-01", "cliente_nome": "Zed"},
                headers=auth_headers(),
            )
        finally:
            app.dependency_overrides.pop(get_person_layer_sweep, None)

        assert resp.status_code == 201, resp.text
        # TestClient runs background tasks before returning, so by here the
        # sweep must have been invoked — scheduled, not merely constructed.
        assert ran == [True]

    def test_sweep_runs_after_the_response_not_before_it(self, http_client):
        """It is a BackgroundTask on purpose: lead creation must not wait on
        an org-wide sweep. If this ever became a blocking call, the 201 would
        start carrying the sweep's latency."""
        from app.main import app
        from app.modules.leads.routers.leads import get_person_layer_sweep

        order: list = []

        def _sweep_dep():
            def _run():
                order.append("sweep")
            return _run

        app.dependency_overrides[get_person_layer_sweep] = _sweep_dep
        try:
            resp = http_client.post(
                "/api/leads",
                json={"data_entrada": "2026-07-01", "cliente_nome": "Yan"},
                headers=auth_headers(),
            )
            order.append("response-built")
        finally:
            app.dependency_overrides.pop(get_person_layer_sweep, None)

        assert resp.status_code == 201, resp.text
        assert order == ["sweep", "response-built"], (
            "the sweep must run in the background task phase, i.e. after the "
            "handler returned its response body"
        )
