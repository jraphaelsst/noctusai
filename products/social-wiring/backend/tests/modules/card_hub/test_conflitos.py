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

    def test_listing_resolves_a_settleable_conflict_on_read(self, client, scoped):
        """Owner directive, 2026-09-29 follow-up: a real trigger for the
        backfill, not only an ad-hoc script — GET `/conflitos` re-consults
        `divergencia_resolucao` before listing. cnh (100%) outranks
        certidao_casamento (67%) for cpf — resolved automatically, never
        shown as `pendente`."""
        cid = _seed(scoped, cliente={"cpf": "303.102.653-55", "cpf_origem": "certidao_casamento"})
        conflito = _conflito_row(
            cid, campo="cpf",
            valor_anterior="303.102.653-55", origem_anterior="certidao_casamento",
            valor_proposto="412.954.238-98", origem_proposto="cnh",
        )
        scoped.set_table_data("cliente_campo_conflitos", [conflito])

        r = client.get("/api/clientes/conflitos", headers=_auth())

        assert r.status_code == 200, r.text
        assert r.json() == []
        assert _cliente(scoped, cid)["cpf"] == "412.954.238-98"
        (c,) = scoped.table("cliente_campo_conflitos").select("*").execute().data
        assert c["status"] == "resolvido_automatico"

    def test_listing_leaves_a_still_ambiguous_conflict_pending(self, client, scoped):
        """A same-tier disagreement (nacionalidade: cnh 100% vs matricula
        100%) is untouched by the resolve-on-read sweep — still listed."""
        cid = _seed(
            scoped, cliente={"nacionalidade": "italiano", "nacionalidade_origem": "matricula"}
        )
        conflito = _conflito_row(
            cid, campo="nacionalidade",
            valor_anterior="italiano", origem_anterior="matricula",
            valor_proposto="brasileiro", origem_proposto="cnh",
        )
        scoped.set_table_data("cliente_campo_conflitos", [conflito])

        r = client.get("/api/clientes/conflitos", headers=_auth())

        assert r.status_code == 200, r.text
        assert [c["id"] for c in r.json()] == [conflito["id"]]
        assert _cliente(scoped, cid)["nacionalidade"] == "italiano"


class TestBackfillRoute:
    """`POST /conflitos/resolver-automaticamente` — the owner directive's
    "authed POST route [...] so the tech lead can run it once after deploy
    through the API." Org-scoped, admin-gated (writes onto `clientes`
    exactly like a manual accept, same posture `decidir_conflito_route`
    takes)."""

    def test_requires_auth(self, anon_client):
        r = anon_client.post("/api/clientes/conflitos/resolver-automaticamente")
        assert r.status_code == 401, (
            f"POST /api/clientes/conflitos/resolver-automaticamente -> "
            f"{r.status_code} (expected a strict 401)"
        )

    def test_a_member_cannot_run_it(self, client, scoped):
        cid = _seed(scoped, cliente={"estado_civil": "divorciado", "estado_civil_origem": "manual"})
        scoped.set_table_data("cliente_campo_conflitos", [_conflito_row(cid)])

        r = client.post("/api/clientes/conflitos/resolver-automaticamente", headers=_auth())

        assert r.status_code == 403
        assert _cliente(scoped, cid)["estado_civil"] == "divorciado"

    def test_an_admin_resolves_settleable_conflicts_org_wide(self, client, scoped):
        _make_admin(client)
        cid = _seed(scoped, cliente={"cpf": "303.102.653-55", "cpf_origem": "certidao_casamento"})
        conflito = _conflito_row(
            cid, campo="cpf",
            valor_anterior="303.102.653-55", origem_anterior="certidao_casamento",
            valor_proposto="412.954.238-98", origem_proposto="cnh",
        )
        scoped.set_table_data("cliente_campo_conflitos", [conflito])

        r = client.post("/api/clientes/conflitos/resolver-automaticamente", headers=_auth())

        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["resolvidos"]) == 1
        assert body["ainda_pendentes"] == []
        assert _cliente(scoped, cid)["cpf"] == "412.954.238-98"

    def test_an_admin_leaves_a_still_ambiguous_conflict_pending(self, client, scoped):
        _make_admin(client)
        cid = _seed(
            scoped, cliente={"nacionalidade": "italiano", "nacionalidade_origem": "matricula"}
        )
        conflito = _conflito_row(
            cid, campo="nacionalidade",
            valor_anterior="italiano", origem_anterior="matricula",
            valor_proposto="brasileiro", origem_proposto="cnh",
        )
        scoped.set_table_data("cliente_campo_conflitos", [conflito])

        r = client.post("/api/clientes/conflitos/resolver-automaticamente", headers=_auth())

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["resolvidos"] == []
        assert len(body["ainda_pendentes"]) == 1
        assert _cliente(scoped, cid)["nacionalidade"] == "italiano"


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
