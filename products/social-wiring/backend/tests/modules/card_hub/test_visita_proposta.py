"""Visita → proposta → THE DEAL (migration 104).

THE FLOW THIS ENCODES, in the owner's words: a roteiro carries N candidate
imóveis; one of them generates a proposta; the proposta that gets ACCEPTED is
the imóvel that attaches to the atendimento and feeds the contract automation.

🔴 THE TWO CLASSES WORTH READING ARE `TestTheAxisIsOrthogonalToStatus` AND
`TestTheDealFollowsTheAcceptance`.

The first holds migration 104's central decision shut. `visitas.status` answers
"did the visit happen" and 082 gives it three values because "hasn't happened
yet" and "didn't happen" are different facts. Recording a proposta as a FOURTH
status value would overwrite the did-it-happen fact — and unrecoverably, since
nothing else in the row remembers it. So the contabilização would start
under-counting `realizada` by exactly the visits that went best.

The second holds the deliberate ASYMMETRY that the codebase otherwise forbids.
A lead's origin código is never copied into `atendimento_negociacao
.imovel_codigo` — no human asserted it. An accepted proposta is the opposite:
an operator has just explicitly said "this property, this deal". These two
rules look contradictory and are not; `TestTheDealFollowsTheAcceptance` and
`test_negociacao.py::TestTheLeadOriginIsNeverTheDeal` are the pair that pins
both halves so neither gets "fixed" into the other.
"""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import ORG_ID, cliente_row
from tests.modules.card_hub.test_agendamentos import atendimento_row
from tests.modules.card_hub.test_roteiros import imovel_row, registry_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _seed(scoped, *, codigos=("ONE9001", "ONE9002"), negociacoes=None):
    cid, aid = str(uuid4()), str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid)])
    scoped.set_table_data("atendimentos", [atendimento_row(aid, cid)])
    scoped.set_table_data("imovel_registry", [registry_row(c) for c in codigos])
    scoped.set_table_data("imoveis", [imovel_row(c) for c in codigos])
    scoped.set_table_data("imovel_dados", [])
    scoped.set_table_data("roteiros", [])
    scoped.set_table_data("visitas", [])
    scoped.set_table_data("atendimento_negociacao", negociacoes or [])
    scoped.set_table_data("negociacao_defaults", [])
    scoped.set_table_data("cliente_membros", [])
    scoped.set_table_data("lead_corretores", [])
    return cid, aid


def _criar_roteiro(client, cid, codigos) -> dict:
    resp = client.post(
        f"/api/clientes/{cid}/roteiros",
        json={"imoveis": list(codigos)},
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _proposta(client, cid, rid, vid, **body):
    return client.patch(
        f"/api/clientes/{cid}/roteiros/{rid}/visitas/{vid}/proposta",
        json=body,
        headers=_auth(),
    )


def _deal(scoped, aid) -> object:
    rows = (
        scoped.table("atendimento_negociacao")
        .select("*")
        .eq("org_id", ORG_ID)
        .eq("atendimento_id", aid)
        .execute()
    ).data or []
    return rows[0].get("imovel_codigo") if rows else None


class TestTheAxisIsOrthogonalToStatus:
    """🔴 Migration 104's central decision — see the module docstring."""

    def test_status_stays_at_its_three_values(self):
        from app.modules.card_hub.roteiros_service import STATUS_VALIDOS

        assert STATUS_VALIDOS == ("pendente", "realizada", "nao_realizada")

    def test_recording_a_proposta_does_not_touch_status(self, client, scoped):
        cid, _aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001"])
        rid, vid = roteiro["id"], roteiro["visitas"][0]["id"]

        client.patch(
            f"/api/clientes/{cid}/roteiros/{rid}/visitas/{vid}",
            json={"status": "realizada"},
            headers=_auth(),
        )
        out = _proposta(client, cid, rid, vid, proposta=True)

        assert out.status_code == 200, out.text
        # The visit still HAPPENED. That fact survives the proposta.
        assert out.json()["status"] == "realizada"
        assert out.json()["proposta_em"] is not None

    def test_a_visita_carries_both_facts_independently(self, client, scoped):
        cid, _aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001"])
        rid, vid = roteiro["id"], roteiro["visitas"][0]["id"]

        _proposta(client, cid, rid, vid, proposta=True)
        listagem = client.get(f"/api/clientes/{cid}/roteiros", headers=_auth()).json()
        visita = listagem["items"][0]["visitas"][0]

        # Still pendente as far as the contabilização is concerned — nobody
        # has said the visit happened, only that an offer came out of it.
        assert visita["status"] == "pendente"
        assert visita["proposta_em"] is not None
        assert listagem["items"][0]["contagem"]["pendentes"] == 1


class TestAcceptanceNeedsAnOffer:
    def test_accepting_without_a_proposta_is_refused_by_name(self, client, scoped):
        cid, _aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001"])
        rid, vid = roteiro["id"], roteiro["visitas"][0]["id"]

        out = _proposta(client, cid, rid, vid, aceita=True)

        assert out.status_code == 400, out.text
        assert "proposta" in out.text.lower()

    def test_the_db_check_says_the_same_thing(self):
        """The service raises a named 400; the CHECK is the backstop for every
        other writer. Both exist on purpose — same division of labour as
        `_validar_split`."""
        from pathlib import Path

        sql = (
            Path(__file__).resolve().parents[3]
            / "migrations"
            / "104_visita_proposta.sql"
        ).read_text()
        assert "proposta_aceita_em IS NULL OR proposta_em IS NOT NULL" in sql

    def test_proposta_and_acceptance_in_one_call_is_allowed(self, client, scoped):
        cid, _aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001"])
        rid, vid = roteiro["id"], roteiro["visitas"][0]["id"]

        out = _proposta(client, cid, rid, vid, proposta=True, aceita=True)

        assert out.status_code == 200, out.text
        assert out.json()["proposta_aceita_em"] is not None


class TestOneAcceptedPropostaPerAtendimento:
    """🔴 Not expressible as a unique index — the scope is the ATENDIMENTO and
    these rows are keyed to a ROTEIRO, two joins away. It lives in the service
    because that is the only place it can."""

    #: 🔴 ASSERTED BY MESSAGE, not merely by status. Two different guards can
    #: refuse a second acceptance with a 400 — this one, and the "the deal
    #: already names a different imóvel" check in `registrar_proposta`. A test
    #: that only asserted `400` passed with this guard DELETED (verified), which
    #: is the false-green shape `KB § PATTERNS/compliance/
    #: auth-boundary-false-green.md` describes one instance of. The phrase names
    #: which guard fired.
    ESTE_GUARDA = "já tem uma proposta aceita"

    def test_a_second_acceptance_on_the_same_atendimento_is_refused(
        self, client, scoped
    ):
        cid, _aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001", "ONE9002"])
        rid = roteiro["id"]
        primeira, segunda = roteiro["visitas"][0]["id"], roteiro["visitas"][1]["id"]

        _proposta(client, cid, rid, primeira, proposta=True, aceita=True)
        out = _proposta(client, cid, rid, segunda, proposta=True, aceita=True)

        assert out.status_code == 400, out.text
        assert self.ESTE_GUARDA in out.json()["error"]["message"], out.text
        assert "ONE9001" in out.text

    def test_it_refuses_even_when_the_deal_field_is_empty(self, client, scoped):
        """🔴 THE ISOLATING CASE. With the deal's `imovel_codigo` cleared by
        hand, the "already names a different imóvel" check cannot fire — so
        only the ATENDIMENTO-scoped rule stands between two accepted propostas.
        This is the test that goes red when it is removed."""
        cid, aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001", "ONE9002"])
        rid = roteiro["id"]
        primeira, segunda = roteiro["visitas"][0]["id"], roteiro["visitas"][1]["id"]

        _proposta(client, cid, rid, primeira, proposta=True, aceita=True)
        client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"imovel_codigo": None},
            headers=_auth(),
        )
        assert _deal(scoped, aid) is None

        out = _proposta(client, cid, rid, segunda, proposta=True, aceita=True)

        assert out.status_code == 400, out.text
        assert self.ESTE_GUARDA in out.json()["error"]["message"], out.text

    def test_it_reaches_across_roteiros_of_the_same_atendimento(
        self, client, scoped
    ):
        """Two roteiros, one deal. `atendimento_negociacao` holds exactly one
        `imovel_codigo`, so two acceptances would be two answers to "what is
        being sold" regardless of which route each came from.

        The deal field is cleared first for the same isolating reason as above:
        without that, this passes on the wrong guard."""
        cid, aid = _seed(scoped)
        r1 = _criar_roteiro(client, cid, ["ONE9001"])
        r2 = _criar_roteiro(client, cid, ["ONE9002"])

        _proposta(client, cid, r1["id"], r1["visitas"][0]["id"], proposta=True, aceita=True)
        client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"imovel_codigo": None},
            headers=_auth(),
        )

        out = _proposta(
            client, cid, r2["id"], r2["visitas"][0]["id"], proposta=True, aceita=True
        )

        assert out.status_code == 400, out.text
        assert self.ESTE_GUARDA in out.json()["error"]["message"], out.text

    def test_re_accepting_the_same_visita_is_a_no_op_not_a_refusal(
        self, client, scoped
    ):
        cid, _aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001"])
        rid, vid = roteiro["id"], roteiro["visitas"][0]["id"]

        _proposta(client, cid, rid, vid, proposta=True, aceita=True)
        out = _proposta(client, cid, rid, vid, aceita=True)

        assert out.status_code == 200, out.text

    def test_undoing_the_first_frees_the_second(self, client, scoped):
        cid, _aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001", "ONE9002"])
        rid = roteiro["id"]
        primeira, segunda = roteiro["visitas"][0]["id"], roteiro["visitas"][1]["id"]

        _proposta(client, cid, rid, primeira, proposta=True, aceita=True)
        _proposta(client, cid, rid, primeira, aceita=False)
        out = _proposta(client, cid, rid, segunda, proposta=True, aceita=True)

        assert out.status_code == 200, out.text


class TestTheDealFollowsTheAcceptance:
    """🔴 The one legitimate auto-write of `imovel_codigo` — see the module
    docstring for why it does not contradict the origin-is-never-the-deal rule."""

    def test_accepting_writes_the_atendimentos_imovel(self, client, scoped):
        cid, aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001", "ONE9002"])
        rid, vid = roteiro["id"], roteiro["visitas"][1]["id"]

        assert _deal(scoped, aid) is None
        _proposta(client, cid, rid, vid, proposta=True, aceita=True)

        assert _deal(scoped, aid) == "ONE9002"

    def test_it_shows_up_on_the_negociacao_endpoint(self, client, scoped):
        cid, _aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001"])
        _proposta(
            client, cid, roteiro["id"], roteiro["visitas"][0]["id"],
            proposta=True, aceita=True,
        )

        neg = client.get(f"/api/clientes/{cid}/negociacao", headers=_auth()).json()
        assert neg["imovel_codigo"] == "ONE9001"

    def test_merely_recording_a_proposta_writes_nothing(self, client, scoped):
        """An OFFER is not a sale. Only acceptance names the deal's property."""
        cid, aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001"])

        _proposta(client, cid, roteiro["id"], roteiro["visitas"][0]["id"], proposta=True)

        assert _deal(scoped, aid) is None

    def test_it_refuses_rather_than_silently_changing_an_existing_deal(
        self, client, scoped
    ):
        """The operator set the deal's imóvel by hand. Accepting a proposta on
        a different property would CHANGE which property the contract is about
        — a real decision, and it must be a visible act rather than a side
        effect of clicking a button on a second visita."""
        cid, aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001", "ONE9002"])
        client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"imovel_codigo": "ONE9001"},
            headers=_auth(),
        )

        out = _proposta(
            client, cid, roteiro["id"], roteiro["visitas"][1]["id"],
            proposta=True, aceita=True,
        )

        assert out.status_code == 400, out.text
        assert "ONE9001" in out.text and "ONE9002" in out.text
        assert _deal(scoped, aid) == "ONE9001"


class TestUndoing:
    def test_un_accepting_clears_the_deals_imovel(self, client, scoped):
        """Leaving it would keep a closed-deal property on a deal nobody has
        agreed — the stale answer this rule exists to refuse."""
        cid, aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001"])
        rid, vid = roteiro["id"], roteiro["visitas"][0]["id"]

        _proposta(client, cid, rid, vid, proposta=True, aceita=True)
        assert _deal(scoped, aid) == "ONE9001"

        out = _proposta(client, cid, rid, vid, aceita=False)

        assert out.status_code == 200, out.text
        assert out.json()["proposta_aceita_em"] is None
        # The offer itself survives — it was made, and un-accepting is not
        # un-offering.
        assert out.json()["proposta_em"] is not None
        assert _deal(scoped, aid) is None

    def test_withdrawing_the_proposta_withdraws_the_acceptance_with_it(
        self, client, scoped
    ):
        """The CHECK forbids an acceptance with no offer, so leaving
        `proposta_aceita_em` behind would be a constraint violation surfacing
        as a 500."""
        cid, aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001"])
        rid, vid = roteiro["id"], roteiro["visitas"][0]["id"]

        _proposta(client, cid, rid, vid, proposta=True, aceita=True)
        out = _proposta(client, cid, rid, vid, proposta=False)

        assert out.status_code == 200, out.text
        assert out.json()["proposta_em"] is None
        assert out.json()["proposta_aceita_em"] is None
        assert _deal(scoped, aid) is None

    def test_un_accepting_leaves_a_deal_imovel_somebody_else_set(
        self, client, scoped
    ):
        """When the deal names a DIFFERENT código, an operator put it there by
        hand and this un-accept has nothing to say about it."""
        cid, aid = _seed(scoped)
        roteiro = _criar_roteiro(client, cid, ["ONE9001"])
        rid, vid = roteiro["id"], roteiro["visitas"][0]["id"]

        _proposta(client, cid, rid, vid, proposta=True, aceita=True)
        client.patch(
            f"/api/clientes/{cid}/negociacao",
            json={"imovel_codigo": "ONE9002"},
            headers=_auth(),
        )

        _proposta(client, cid, rid, vid, aceita=False)

        assert _deal(scoped, aid) == "ONE9002"
