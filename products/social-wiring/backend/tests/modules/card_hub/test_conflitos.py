"""Admin adjudication of `cliente_campo_conflitos` (migration 138), through
HTTP — the backend surface a notifications panel's approve/deny buttons
call into. See `identidade_extracao_service.resolver_conflito` for the
service-level unit tests (accept/reject/idempotency)."""
from __future__ import annotations

from uuid import uuid4

from noctusai_lib.testing import TEST_USER_ID

from tests.modules.card_hub.conftest import ORG_ID, cliente_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _make_admin(client) -> None:
    """`PUT .../decidir` is owner/admin only (the TRUSTED `noctus_users`
    row — see `router.decidir_conflito_route`'s own docstring for the
    exact spoof this closes). The shared `client` fixture carries no role
    at all by default; seed the row it actually reads."""
    client.mock_supabase.set_table_data(
        "noctus_users",
        [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "owner"}],
    )


def _cliente(scoped, cid) -> dict:
    return [r for r in scoped.table("clientes").select("*").execute().data
            if r["id"] == cid][0]


def _conflito_row(cid: str, **over) -> dict:
    base = {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "cliente_id": cid,
        "campo": "estado_civil",
        "valor_anterior": "divorciado",
        "origem_anterior": "manual",
        "valor_proposto": "casado",
        "origem_proposto": "matricula",
        "confianca_proposta": "alta",
        "fonte_tabela": "matricula_qualificacoes",
        "fonte_id": str(uuid4()),
        "status": "pendente",
        "notificado_em": None,
        "decidido_por": None,
        "decidido_em": None,
    }
    return {**base, **over}


def _seed(scoped, *, cliente=None, conflitos=()) -> str:
    cid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, **(cliente or {}))])
    scoped.set_table_data("cliente_campo_conflitos", list(conflitos))
    return cid


class TestListingConflicts:
    def test_lists_only_pending_conflicts(self, client, scoped):
        cid = _seed(scoped)
        pendente = _conflito_row(cid)
        decidido = _conflito_row(cid, status="aceito", campo="rg")
        scoped.set_table_data("cliente_campo_conflitos", [pendente, decidido])

        r = client.get("/api/clientes/conflitos", headers=_auth())

        assert r.status_code == 200, r.text
        body = r.json()
        assert [c["id"] for c in body] == [pendente["id"]]
        assert body[0]["valor_anterior"] == "divorciado"
        assert body[0]["valor_proposto"] == "casado"

    def test_listing_is_not_admin_gated(self, client, scoped):
        """Read-only — seeing what's pending is not the sensitive half,
        deciding it is (`TestOnlyAdminsCanDecide` below)."""
        cid = _seed(scoped)
        scoped.set_table_data("cliente_campo_conflitos", [_conflito_row(cid)])
        r = client.get("/api/clientes/conflitos", headers=_auth())
        assert r.status_code == 200, r.text

    def test_cliente_id_scopes_to_one_persons_pending_conflicts(self, client, scoped):
        """`DadosPessoaisForm`'s durable pending-state read — the card's
        own admin-confirmation notice, not the org-wide admin queue."""
        cid1 = _seed(scoped)
        cid2 = str(uuid4())
        scoped.set_table_data(
            "clientes",
            scoped.table("clientes").select("*").execute().data
            + [cliente_row(cid2)],
        )
        c1 = _conflito_row(cid1)
        c2 = _conflito_row(cid2, campo="cpf")
        scoped.set_table_data("cliente_campo_conflitos", [c1, c2])

        r = client.get(
            "/api/clientes/conflitos", params={"cliente_id": cid1}, headers=_auth()
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert [c["id"] for c in body] == [c1["id"]]


class TestOnlyAdminsCanDecide:
    """🔴 The provenance directive's "admin confirmation" is meaningless if
    any authenticated org member can decide a conflict — the gate this
    class exists to pin. Strict `== 403`, per
    `KB § PATTERNS/compliance/auth-boundary-false-green.md`."""

    def test_a_member_cannot_decide(self, client, scoped):
        cid = _seed(scoped, cliente={"estado_civil": "divorciado", "estado_civil_origem": "manual"})
        conflito = _conflito_row(cid)
        scoped.set_table_data("cliente_campo_conflitos", [conflito])

        r = client.put(
            f"/api/clientes/conflitos/{conflito['id']}/decidir",
            json={"aceitar": True},
            headers=_auth(),
        )

        assert r.status_code == 403, r.text
        assert _cliente(scoped, cid)["estado_civil"] == "divorciado"

    def test_a_jwt_claiming_admin_does_not_bypass_the_gate(self, client, scoped):
        """The spoof `noctusai_lib.api.auth.session.is_org_admin` closes —
        only the TRUSTED `noctus_users` row counts."""
        client.mock_supabase.auth.get_user.return_value.user.user_metadata[
            "org_role"
        ] = "admin"
        cid = _seed(scoped, cliente={"estado_civil": "divorciado", "estado_civil_origem": "manual"})
        conflito = _conflito_row(cid)
        scoped.set_table_data("cliente_campo_conflitos", [conflito])

        r = client.put(
            f"/api/clientes/conflitos/{conflito['id']}/decidir",
            json={"aceitar": True},
            headers=_auth(),
        )

        assert r.status_code == 403, r.text


class TestDecidingAConflict:
    def test_accepting_overwrites_and_keeps_the_prior_value(self, client, scoped):
        _make_admin(client)
        cid = _seed(scoped, cliente={"estado_civil": "divorciado", "estado_civil_origem": "manual"})
        conflito = _conflito_row(cid)
        scoped.set_table_data("cliente_campo_conflitos", [conflito])

        r = client.put(
            f"/api/clientes/conflitos/{conflito['id']}/decidir",
            json={"aceitar": True},
            headers=_auth(),
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "aceito"
        assert body["valor_anterior"] == "divorciado"  # the way back, untouched

        cliente = _cliente(scoped, cid)
        assert cliente["estado_civil"] == "casado"
        assert cliente["estado_civil_origem"] == "matricula"
        assert cliente["estado_civil_confirmado_por"] is not None

    def test_rejecting_leaves_the_human_value_in_place(self, client, scoped):
        _make_admin(client)
        cid = _seed(scoped, cliente={"estado_civil": "divorciado", "estado_civil_origem": "manual"})
        conflito = _conflito_row(cid)
        scoped.set_table_data("cliente_campo_conflitos", [conflito])

        r = client.put(
            f"/api/clientes/conflitos/{conflito['id']}/decidir",
            json={"aceitar": False},
            headers=_auth(),
        )

        assert r.status_code == 200, r.text
        assert r.json()["status"] == "rejeitado"
        assert _cliente(scoped, cid)["estado_civil"] == "divorciado"

    def test_deciding_twice_is_a_400_first_decision_wins(self, client, scoped):
        _make_admin(client)
        cid = _seed(scoped, cliente={"estado_civil": "divorciado", "estado_civil_origem": "manual"})
        conflito = _conflito_row(cid)
        scoped.set_table_data("cliente_campo_conflitos", [conflito])
        client.put(
            f"/api/clientes/conflitos/{conflito['id']}/decidir",
            json={"aceitar": True},
            headers=_auth(),
        )

        r = client.put(
            f"/api/clientes/conflitos/{conflito['id']}/decidir",
            json={"aceitar": False},
            headers=_auth(),
        )

        assert r.status_code == 400
        assert _cliente(scoped, cid)["estado_civil"] == "casado"  # first decision stands

    def test_an_unknown_conflito_is_a_404(self, client, scoped):
        _make_admin(client)
        _seed(scoped)
        r = client.put(
            f"/api/clientes/conflitos/{uuid4()}/decidir",
            json={"aceitar": True},
            headers=_auth(),
        )
        assert r.status_code == 404
