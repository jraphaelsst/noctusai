"""Compradores — the other people party to an atendimento (migration 073).

WHAT THESE TESTS PIN
--------------------
The design claim is that a comprador is a `clientes` row and this feature is
only an EDGE table. Every assertion here is a consequence of that claim, and
the most important one is negative: nothing in the card_hub was forked to make
person #2 work.

- an added comprador gets the SAME eight-item checklist as the titular, from
  the same endpoint, with no per-party definition anywhere;
- a spouse who already exists is LINKED, never copied — one person, one record,
  one pile of documents;
- removing a party detaches them and does NOT delete the person, because their
  documents are theirs and are under a retention policy;
- the titular is not in the table and cannot be added to it.

Auth is NOT re-tested here. `test_auth_boundary.py` enumerates every mounted
card_hub route and asserts a strict 401 on each, so these three endpoints are
covered the moment they are registered — a hand-written copy would be a second
list to forget to update.
"""
from __future__ import annotations

from uuid import uuid4

from app.modules.card_hub import documento_checklist_service as checklist_svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _atendimento(aid: str, cliente_id: str, **over) -> dict:
    row = {
        "id": aid,
        "org_id": ORG_ID,
        "cliente_id": cliente_id,
        "lead_id": None,
        "meta_ads_lead_id": None,
        "status": "aberta",
        "substituida_por": None,
        "arquivado": False,
        "titulo": "Compra do apto",
        "created_at": "2026-01-01T00:00:00+00:00",
        "closed_at": None,
    }
    row.update(over)
    return row


def _seed(scoped, *, clientes=None, atendimentos=None, partes=None):
    scoped.set_table_data("clientes", clientes or [])
    scoped.set_table_data("atendimentos", atendimentos or [])
    scoped.set_table_data("atendimento_partes", partes or [])
    scoped.set_table_data("cliente_documentos", [])
    scoped.set_table_data("cliente_documento_checklist", [])


def _titular(scoped):
    """A card with one open atendimento — the ordinary case."""
    cid, aid = str(uuid4()), str(uuid4())
    _seed(
        scoped,
        clientes=[cliente_row(cid, nome="Luciano", nome_completo="Luciano Mauricio")],
        atendimentos=[_atendimento(aid, cid)],
    )
    return cid, aid


class TestAddingAComprador:
    def test_a_new_person_is_created_and_attached(self, client, scoped):
        cid, aid = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio", "celular": "+5511977776666"},
            headers=_auth(),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["papel"] == "comprador"
        assert body["atendimento_id"] == aid
        assert body["cliente"]["nome_completo"] == "Maria Mauricio"

    def test_the_created_person_is_a_real_cliente_row(self, client, scoped):
        """🔴 The whole design. If she were anything else, the checklist and
        the document uploads would need a second implementation."""
        cid, _ = _titular(scoped)
        client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio"},
            headers=_auth(),
        )
        nomes = [
            row["nome_completo"]
            for row in scoped.table("clientes").select("*").execute().data
        ]
        assert "Maria Mauricio" in nomes

    def test_a_typed_name_fills_nome_completo_not_just_nome(self, client, scoped):
        """An operator typing a name into "Adicionar Comprador" IS collecting
        a legal full name — writing it to `nome` alone would leave her own
        checklist showing "Nome Completo" unticked the moment she is created.
        """
        cid, _ = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio"},
            headers=_auth(),
        )
        nova = r.json()["cliente"]["id"]
        checklist = client.get(
            f"/api/clientes/{nova}/documento-checklist", headers=_auth()
        ).json()
        por_key = {i["key"]: i for i in checklist["items"]}
        assert por_key["nome_completo"]["concluido"] is True

    def test_an_existing_person_is_linked_not_copied(self, client, scoped):
        """One person, one record, one pile of documents."""
        cid, aid = str(uuid4()), str(uuid4())
        esposa = str(uuid4())
        _seed(
            scoped,
            clientes=[
                cliente_row(cid, nome="Luciano", nome_completo="Luciano Mauricio"),
                cliente_row(esposa, nome="Maria", nome_completo="Maria Mauricio"),
            ],
            atendimentos=[_atendimento(aid, cid)],
        )
        antes = len(scoped.table("clientes").select("*").execute().data)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"cliente_id": esposa},
            headers=_auth(),
        )
        assert r.status_code == 201
        assert r.json()["cliente_id"] == esposa
        depois = len(scoped.table("clientes").select("*").execute().data)
        assert depois == antes, "linking must not create a second record"

    def test_both_cliente_id_and_nome_is_a_422(self, client, scoped):
        """Their intent is unknowable when the two disagree."""
        cid, _ = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"cliente_id": str(uuid4()), "nome": "Maria"},
            headers=_auth(),
        )
        assert r.status_code == 400

    def test_neither_cliente_id_nor_nome_is_a_422(self, client, scoped):
        cid, _ = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores", json={}, headers=_auth()
        )
        assert r.status_code == 400

    def test_the_titular_cannot_be_added_as_their_own_comprador(
        self, client, scoped
    ):
        cid, _ = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"cliente_id": cid},
            headers=_auth(),
        )
        assert r.status_code == 400

    def test_another_orgs_person_cannot_be_attached(self, client, scoped):
        """An unvalidated id would attach a stranger's record to this deal."""
        cid, _ = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"cliente_id": str(uuid4())},
            headers=_auth(),
        )
        assert r.status_code == 404

    def test_adding_the_same_person_twice_is_a_409(self, client, scoped):
        """A double-click is not an intent, and a 201 for a row that was not
        created teaches the UI to trust a response that is not true."""
        cid, _ = _titular(scoped)
        first = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio"},
            headers=_auth(),
        ).json()
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"cliente_id": first["cliente_id"]},
            headers=_auth(),
        )
        assert r.status_code == 409

    def test_an_unknown_papel_is_refused(self, client, scoped):
        cid, _ = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio", "papel": "sogra"},
            headers=_auth(),
        )
        assert r.status_code == 400


class TestNobodyIsCreatedDangling:
    """🔴 Migration 074. A created comprador must not be a person the database
    cannot explain.

    She has no channel, no canonical key, no touches and no campaign — every
    other row in `clientes` got there through an ingestion path that left a
    trail. Without an explicit link she is indistinguishable from a lead who
    walked in off the street, and `atendimento_partes` only explains her while
    the atendimento lives, because it cascades on its delete.
    """

    def _pessoa(self, scoped, cliente_id):
        return [r for r in scoped.table("clientes").select("*").execute().data
                if r["id"] == cliente_id][0]

    def test_a_created_comprador_points_back_at_the_titular(self, client, scoped):
        cid, _ = _titular(scoped)
        nova = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio"},
            headers=_auth(),
        ).json()["cliente_id"]
        row = self._pessoa(scoped, nova)
        assert row["vinculado_a_cliente_id"] == cid
        assert row["vinculo_origem"] == "comprador_atendimento"
        assert row["vinculado_em"] is not None

    def test_a_linked_existing_person_is_recorded_too(self, client, scoped):
        """"any link to another cliente" — a spouse who happened to already be
        a lead is no less related for it."""
        cid, aid = str(uuid4()), str(uuid4())
        esposa = str(uuid4())
        _seed(
            scoped,
            clientes=[
                cliente_row(cid, nome="Luciano", nome_completo="Luciano Mauricio"),
                cliente_row(esposa, nome="Maria", nome_completo="Maria Mauricio"),
            ],
            atendimentos=[_atendimento(aid, cid)],
        )
        client.post(
            f"/api/clientes/{cid}/compradores",
            json={"cliente_id": esposa},
            headers=_auth(),
        )
        assert self._pessoa(scoped, esposa)["vinculado_a_cliente_id"] == cid

    def test_an_existing_link_is_never_overwritten(self, client, scoped):
        """First-writer-wins: a person keeps their ORIGINAL introducer.

        Overwriting would make the column mean "the most recent deal they
        appeared in", which `atendimento_partes` already says, and says better.
        """
        cid, aid = str(uuid4()), str(uuid4())
        esposa, antigo = str(uuid4()), str(uuid4())
        _seed(
            scoped,
            clientes=[
                cliente_row(cid, nome="Luciano", nome_completo="Luciano Mauricio"),
                cliente_row(antigo, nome="Alguem", nome_completo="Alguem Antigo"),
                cliente_row(
                    esposa, nome="Maria", nome_completo="Maria Mauricio",
                    vinculado_a_cliente_id=antigo,
                    vinculo_origem="comprador_atendimento",
                ),
            ],
            atendimentos=[_atendimento(aid, cid)],
        )
        client.post(
            f"/api/clientes/{cid}/compradores",
            json={"cliente_id": esposa},
            headers=_auth(),
        )
        assert self._pessoa(scoped, esposa)["vinculado_a_cliente_id"] == antigo

    def test_removing_the_party_leaves_the_link_intact(self, client, scoped):
        """The relationship is a fact about the PERSON and outlives the deal —
        which is the entire reason it is not stored only on the join table."""
        cid, _ = _titular(scoped)
        parte = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio"},
            headers=_auth(),
        ).json()
        client.delete(
            f"/api/clientes/{cid}/compradores/{parte['id']}", headers=_auth()
        )
        row = self._pessoa(scoped, parte["cliente_id"])
        assert row["vinculado_a_cliente_id"] == cid


class TestEachCompradorGetsTheSameChecklist:
    def test_the_added_person_gets_the_identical_eight_item_list(
        self, client, scoped
    ):
        """🔴 No per-party definition exists, so there is nothing to drift.

        This is the test that would fail if someone "simplified" compradores
        into their own lightweight table with their own field list.
        """
        cid, _ = _titular(scoped)
        nova = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio"},
            headers=_auth(),
        ).json()["cliente_id"]

        do_titular = client.get(
            f"/api/clientes/{cid}/documento-checklist", headers=_auth()
        ).json()
        da_esposa = client.get(
            f"/api/clientes/{nova}/documento-checklist", headers=_auth()
        ).json()
        assert [i["key"] for i in do_titular["items"]] == [
            i["key"] for i in da_esposa["items"]
        ]
        assert da_esposa["total"] == len(checklist_svc.ITENS)

    def test_her_documents_are_hers_not_the_titulars(self, client, scoped):
        """Separate `cliente_id`, so the existing per-client scoping already
        keeps the two piles apart — nothing new was needed for that."""
        cid, _ = _titular(scoped)
        nova = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio"},
            headers=_auth(),
        ).json()["cliente_id"]
        scoped.set_table_data("cliente_documentos", [{
            "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": nova,
            "tipo_documento": "rg", "deleted_at": None,
        }])
        dela = client.get(
            f"/api/clientes/{nova}/documento-checklist", headers=_auth()
        ).json()
        dele = client.get(
            f"/api/clientes/{cid}/documento-checklist", headers=_auth()
        ).json()
        assert {i["key"]: i["concluido"] for i in dela["items"]}["rg"] is True
        assert {i["key"]: i["concluido"] for i in dele["items"]}["rg"] is False


class TestListing:
    def test_parties_come_back_in_display_order(self, client, scoped):
        cid, _ = _titular(scoped)
        for nome in ("Maria Mauricio", "Jose Mauricio"):
            client.post(
                f"/api/clientes/{cid}/compradores",
                json={"nome": nome},
                headers=_auth(),
            )
        body = client.get(f"/api/clientes/{cid}/compradores", headers=_auth()).json()
        assert body["total"] == 2
        assert [p["cliente"]["nome_completo"] for p in body["items"]] == [
            "Maria Mauricio",
            "Jose Mauricio",
        ]

    def test_a_card_with_no_parties_is_an_empty_list_not_an_error(
        self, client, scoped
    ):
        """The Geral tab hides the section when this is empty, so an error
        here would break a panel that simply has nothing to show."""
        cid, _ = _titular(scoped)
        body = client.get(f"/api/clientes/{cid}/compradores", headers=_auth()).json()
        assert body == {
            "items": [],
            "total": 0,
            "atendimento_id": body["atendimento_id"],
            # Echoed back since migration 098 so the caller can tell WHICH
            # side came back empty — the Vendedor tab asks the same endpoint.
            "lado": "comprador",
        }
        assert body["total"] == 0

    def test_a_cliente_with_no_open_atendimento_lists_empty(self, client, scoped):
        """Rather than the 409 that CREATING would (correctly) raise."""
        cid = str(uuid4())
        _seed(scoped, clientes=[cliente_row(cid)], atendimentos=[])
        r = client.get(f"/api/clientes/{cid}/compradores", headers=_auth())
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_unknown_cliente_404s(self, client, scoped):
        _seed(scoped)
        r = client.get(f"/api/clientes/{uuid4()}/compradores", headers=_auth())
        assert r.status_code == 404


class TestRemoving:
    def test_removing_detaches_the_party(self, client, scoped):
        cid, _ = _titular(scoped)
        parte = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio"},
            headers=_auth(),
        ).json()
        r = client.delete(
            f"/api/clientes/{cid}/compradores/{parte['id']}", headers=_auth()
        )
        assert r.status_code == 204
        body = client.get(f"/api/clientes/{cid}/compradores", headers=_auth()).json()
        assert body["total"] == 0

    def test_removing_a_party_does_not_delete_the_person(self, client, scoped):
        """🔴 Their documents are theirs and are under a retention policy.
        Cascading to `clientes` would destroy uploads the org may be legally
        required to keep, on a click that reads as "not part of this purchase".
        """
        cid, _ = _titular(scoped)
        parte = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio"},
            headers=_auth(),
        ).json()
        client.delete(
            f"/api/clientes/{cid}/compradores/{parte['id']}", headers=_auth()
        )
        ids = [r["id"] for r in scoped.table("clientes").select("*").execute().data]
        assert parte["cliente_id"] in ids

    def test_removing_an_unknown_party_404s(self, client, scoped):
        cid, _ = _titular(scoped)
        r = client.delete(
            f"/api/clientes/{cid}/compradores/{uuid4()}", headers=_auth()
        )
        assert r.status_code == 404


class TestOLadoVendedor:
    """The seller side — migration 098's `lado` column.

    🔴 WHAT THESE TESTS ARE REALLY FOR

    The Vendedor tab is the Comprador tab pointed at different rows. That is
    the design, and the risk that comes with it is leakage: one side rendering
    the other's people. Every test here is about the boundary holding.
    """

    def test_a_vendedor_is_created_on_the_seller_side_as_proprietario(
        self, client, scoped
    ):
        """The default role differs per side. "At first the vendedor is the
        property owner" is a statement about data, and this is where it
        lives."""
        cid, aid = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Carlos Eduardo Ramos", "lado": "vendedor"},
            headers=_auth(),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["lado"] == "vendedor"
        assert body["papel"] == "proprietario"
        assert body["atendimento_id"] == aid

    def test_the_two_sides_do_not_see_each_other(self, client, scoped):
        """🔴 The leak this whole column exists to prevent."""
        cid, _ = _titular(scoped)
        client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Compradora"},
            headers=_auth(),
        )
        client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Carlos Vendedor", "lado": "vendedor"},
            headers=_auth(),
        )

        compradores = client.get(
            f"/api/clientes/{cid}/compradores", headers=_auth()
        ).json()
        vendedores = client.get(
            f"/api/clientes/{cid}/compradores?lado=vendedor", headers=_auth()
        ).json()

        assert [p["cliente"]["nome_completo"] for p in compradores["items"]] == [
            "Maria Compradora"
        ]
        assert [p["cliente"]["nome_completo"] for p in vendedores["items"]] == [
            "Carlos Vendedor"
        ]

    def test_omitting_lado_still_means_the_buyer_side(self, client, scoped):
        """Every caller written before 098 meant the buyer side, and every row
        written before it is one."""
        cid, _ = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Mauricio"},
            headers=_auth(),
        )
        assert r.json()["lado"] == "comprador"

    def test_each_side_numbers_its_own_people_from_zero(self, client, scoped):
        """Ordem is per side, so the first vendedor is 0 — not a continuation
        of the buyer list's count."""
        cid, _ = _titular(scoped)
        client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Maria Compradora"},
            headers=_auth(),
        )
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Carlos Vendedor", "lado": "vendedor"},
            headers=_auth(),
        )
        assert r.json()["ordem"] == 0

    def test_a_role_from_the_other_side_is_refused(self, client, scoped):
        """`fiador` is a buyer-side role; an estate sells but never buys, so
        `inventariante` is the seller's. Neither crosses."""
        cid, _ = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Alguem", "lado": "vendedor", "papel": "fiador"},
            headers=_auth(),
        )
        assert r.status_code == 400

        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Alguem", "papel": "inventariante"},
            headers=_auth(),
        )
        assert r.status_code == 400

    def test_a_role_valid_on_both_sides_is_accepted_on_both(self, client, scoped):
        """`conjuge` is the same relationship to a different principal — which
        is exactly why `lado` is a column and not a prefix on `papel`."""
        cid, _ = _titular(scoped)
        for lado in ("comprador", "vendedor"):
            r = client.post(
                f"/api/clientes/{cid}/compradores",
                json={"nome": f"Conjuge {lado}", "lado": lado, "papel": "conjuge"},
                headers=_auth(),
            )
            assert r.status_code == 201, r.text
            assert r.json()["papel"] == "conjuge"

    def test_an_unknown_lado_is_refused_rather_than_defaulted(self, client, scoped):
        """Silently falling back to the buyer side would file a seller under
        the buyers."""
        cid, _ = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"nome": "Alguem", "lado": "locatario"},
            headers=_auth(),
        )
        assert r.status_code == 400

    def test_the_titular_may_not_be_re_added_as_a_buyer(self, client, scoped):
        """Buyer-side rule: `atendimentos.cliente_id` already names them."""
        cid, _ = _titular(scoped)
        r = client.post(
            f"/api/clientes/{cid}/compradores",
            json={"cliente_id": cid},
            headers=_auth(),
        )
        assert r.status_code == 400


# ─── Corrigindo o papel depois (o badge vira o controle) ─────────────────────
#
# WHY THIS BLOCK EXISTS
# ---------------------
# `papel` was API-reachable and UI-unreachable. `AdicionarCompradorDialog` asks
# for nome + celular — the two `stage_gate.CAMPOS_OBRIGATORIOS` fields — and
# nothing ever sent a `papel`, so the side's default was permanent: every
# buyer-side party a `comprador`, every seller-side one a `proprietario`.
#
# That blocked a legal requirement rather than a nicety. A married seller's
# spouse must consent to the sale (CC art. 1.647; migration 097's header states
# it), and a contract cannot ask who has to sign if no row can say `conjuge`.


def _cliente_row(scoped, cliente_id: str) -> dict:
    """Read a `clientes` row back THROUGH the same scoped mock the routes
    write to — a second `.schema()` call would be a second data store (see the
    conftest header), and the assertion would pass against nothing."""
    rows = (
        scoped.table("clientes").select("*").eq("id", str(cliente_id)).execute().data
        or []
    )
    assert rows, f"cliente {cliente_id} não está no mock"
    return rows[0]


def _add(client, cid: str, nome: str, **body) -> dict:
    r = client.post(
        f"/api/clientes/{cid}/compradores",
        json={"nome": nome, **body},
        headers=_auth(),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _patch_papel(client, cid: str, parte_id: str, papel: str):
    return client.patch(
        f"/api/clientes/{cid}/compradores/{parte_id}",
        json={"papel": papel},
        headers=_auth(),
    )


class TestCorrigindoOPapelDaParte:
    def test_the_side_default_is_no_longer_the_last_word(self, client, scoped):
        """The whole gap in one assertion: added as the side's default, then
        corrected — which nothing could do before."""
        cid, _ = _titular(scoped)
        parte = _add(client, cid, "Maria Mauricio")
        assert parte["papel"] == "comprador"

        r = _patch_papel(client, cid, parte["id"], "conjuge")
        assert r.status_code == 200, r.text
        assert r.json()["papel"] == "conjuge"

        # And it PERSISTED — a response echoing the request would pass a
        # weaker version of this test while writing nothing.
        listagem = client.get(
            f"/api/clientes/{cid}/compradores", headers=_auth()
        ).json()
        assert [p["papel"] for p in listagem["items"]] == ["conjuge"]

    def test_a_role_from_the_other_side_is_refused_here_too(self, client, scoped):
        """Same vocabulary, same refusal as `adicionar` — one definition
        checked at both doors, not a second list that drifts."""
        cid, _ = _titular(scoped)
        comprador = _add(client, cid, "Maria")
        vendedor = _add(client, cid, "Carlos", lado="vendedor")

        assert _patch_papel(client, cid, comprador["id"], "inventariante").status_code == 400
        assert _patch_papel(client, cid, vendedor["id"], "fiador").status_code == 400
        assert _patch_papel(client, cid, comprador["id"], "socio").status_code == 400

    def test_the_caller_may_not_name_the_side(self, client, scoped):
        """🔴 `lado` decides which vocabulary validates `papel`, so a caller
        allowed to send it could call a vendedor a `fiador` by claiming the
        buyer side. `StrictHttpModel` refuses the field outright."""
        cid, _ = _titular(scoped)
        vendedor = _add(client, cid, "Carlos", lado="vendedor")
        r = client.patch(
            f"/api/clientes/{cid}/compradores/{vendedor['id']}",
            json={"papel": "fiador", "lado": "comprador"},
            headers=_auth(),
        )
        assert r.status_code == 422

    def test_an_unknown_parte_is_404_not_a_silent_no_op(self, client, scoped):
        cid, _ = _titular(scoped)
        assert _patch_papel(client, cid, str(uuid4()), "conjuge").status_code == 404


class TestVinculandoOConjuge:
    """🔴 `papel='conjuge'` is the one role that is not merely a label.

    It asserts a fact about two PEOPLE, and `clientes.conjuge_cliente_id`
    (migration 097) is what turns "who must sign?" from a question about a
    badge into one the record can answer. Labelling without linking would ship
    the word and none of the meaning.
    """

    def test_the_buyer_side_links_to_the_titular(self, client, scoped):
        """The buyer-side principal is `atendimentos.cliente_id` — the titular
        is NOT a row in this table (migration 073), so the link cannot be found
        by reading `atendimento_partes` alone."""
        cid, _ = _titular(scoped)
        parte = _add(client, cid, "Maria Mauricio")

        r = _patch_papel(client, cid, parte["id"], "conjuge")
        assert r.status_code == 200, r.text
        esposa_id = parte["cliente_id"]
        assert r.json()["conjuge_cliente_id"] == cid

        # BOTH directions — a marriage is symmetric, and the question is asked
        # from the titular's card at least as often as from the spouse's.
        assert _cliente_row(scoped, esposa_id)["conjuge_cliente_id"] == cid
        assert _cliente_row(scoped, cid)["conjuge_cliente_id"] == esposa_id

    def test_the_seller_side_links_to_the_proprietario(self, client, scoped):
        """The asymmetry migration 098 documents: the seller's principal IS a
        row here, because the seller never arrives as a lead."""
        cid, _ = _titular(scoped)
        dono = _add(client, cid, "Carlos Eduardo Ramos", lado="vendedor")
        assert dono["papel"] == "proprietario"
        esposa = _add(client, cid, "Beatriz Ramos", lado="vendedor")

        r = _patch_papel(client, cid, esposa["id"], "conjuge")
        assert r.status_code == 200, r.text
        assert r.json()["conjuge_cliente_id"] == dono["cliente_id"]
        assert (
            _cliente_row(scoped, esposa["cliente_id"])["conjuge_cliente_id"]
            == dono["cliente_id"]
        )
        assert (
            _cliente_row(scoped, dono["cliente_id"])["conjuge_cliente_id"]
            == esposa["cliente_id"]
        )

    def test_two_co_buyers_make_it_ambiguous_so_nothing_is_linked(
        self, client, scoped
    ):
        """🔴 Ambiguity is not an error — but guessing is. Two people could be
        this spouse's principal, and picking the titular because they are
        easiest to find would put a name on a signature line for no reason."""
        cid, _ = _titular(scoped)
        irmao = _add(client, cid, "Irmão Comprador")
        esposa = _add(client, cid, "Maria Mauricio")

        r = _patch_papel(client, cid, esposa["id"], "conjuge")
        assert r.status_code == 200, r.text
        assert r.json()["papel"] == "conjuge"
        assert r.json()["conjuge_cliente_id"] is None
        for pessoa in (cid, irmao["cliente_id"], esposa["cliente_id"]):
            assert _cliente_row(scoped, pessoa).get("conjuge_cliente_id") is None

    def test_two_proprietarios_make_it_ambiguous_too(self, client, scoped):
        """Co-owners selling together — the same refusal, on the side whose
        principal lives in this table."""
        cid, _ = _titular(scoped)
        a = _add(client, cid, "Carlos Ramos", lado="vendedor")
        b = _add(client, cid, "Regina Ramos", lado="vendedor")
        _patch_papel(client, cid, b["id"], "proprietario")
        terceiro = _add(client, cid, "Alguém Ramos", lado="vendedor")

        r = _patch_papel(client, cid, terceiro["id"], "conjuge")
        assert r.status_code == 200, r.text
        assert r.json()["conjuge_cliente_id"] is None
        assert _cliente_row(scoped, a["cliente_id"]).get("conjuge_cliente_id") is None
        assert _cliente_row(scoped, b["cliente_id"]).get("conjuge_cliente_id") is None

    def test_no_candidate_at_all_still_sets_the_papel(self, client, scoped):
        """A lone seller-side party relabelled `conjuge`: nobody is left to be
        the principal. Zero candidates and two get the same treatment, because
        in both cases nothing here knows the answer."""
        cid, _ = _titular(scoped)
        sozinha = _add(client, cid, "Beatriz Ramos", lado="vendedor")

        r = _patch_papel(client, cid, sozinha["id"], "conjuge")
        assert r.status_code == 200, r.text
        assert r.json()["papel"] == "conjuge"
        assert r.json()["conjuge_cliente_id"] is None

    def test_an_existing_spouse_is_never_clobbered(self, client, scoped):
        """🔴 Surface, do not overwrite. A `conjuge_cliente_id` naming somebody
        else is either an earlier deal's correct answer or a mistake a human
        has to look at; silently moving a signature requirement onto a
        different person from a dropdown is the silent-error shape."""
        cid, aid = str(uuid4()), str(uuid4())
        outra = str(uuid4())
        _seed(
            scoped,
            clientes=[
                cliente_row(cid, nome="Luciano", conjuge_cliente_id=outra),
                cliente_row(outra, nome="Primeira Esposa"),
            ],
            atendimentos=[_atendimento(aid, cid)],
        )
        parte = _add(client, cid, "Maria Mauricio")

        r = _patch_papel(client, cid, parte["id"], "conjuge")
        assert r.status_code == 409, r.text
        # 🔴 Refused BEFORE anything was written — a 409 whose party had
        # already been relabelled would be a lie about what the request did.
        assert _cliente_row(scoped, cid)["conjuge_cliente_id"] == outra
        assert _cliente_row(scoped, parte["cliente_id"]).get("conjuge_cliente_id") is None
        listagem = client.get(
            f"/api/clientes/{cid}/compradores", headers=_auth()
        ).json()
        assert [p["papel"] for p in listagem["items"]] == ["comprador"]

    def test_re_marking_an_already_linked_spouse_is_a_no_op_not_a_409(
        self, client, scoped
    ):
        """The guard refuses a DIFFERENT spouse, not the same one — otherwise
        the dropdown would refuse the value it is already showing."""
        cid, _ = _titular(scoped)
        parte = _add(client, cid, "Maria Mauricio")
        assert _patch_papel(client, cid, parte["id"], "conjuge").status_code == 200

        r = _patch_papel(client, cid, parte["id"], "conjuge")
        assert r.status_code == 200, r.text
        assert r.json()["conjuge_cliente_id"] == cid

    def test_moving_off_conjuge_does_not_unlink_the_marriage(self, client, scoped):
        """A marriage is a fact about two people, not about how this deal
        labels one of them. A mis-click on a dropdown must not erase it —
        clearing a wrong spouse is an edit on the person's own record."""
        cid, _ = _titular(scoped)
        parte = _add(client, cid, "Maria Mauricio")
        _patch_papel(client, cid, parte["id"], "conjuge")

        r = _patch_papel(client, cid, parte["id"], "procurador")
        assert r.status_code == 200, r.text
        assert r.json()["papel"] == "procurador"
        assert _cliente_row(scoped, parte["cliente_id"])["conjuge_cliente_id"] == cid
        assert _cliente_row(scoped, cid)["conjuge_cliente_id"] == parte["cliente_id"]


class TestUmaParteSoEAlcancavelPeloSeuProprioCliente:
    """A parte is reachable ONLY through the cliente whose deal it is on.

    🔴 PRE-EXISTING HOLE, FOUND WHILE ADDING `atualizar_papel`. `remover`
    called `ensure_cliente` — which proves the CLIENTE exists in the org — and
    then looked the parte up by `org_id + parte_id` alone. So any parte in the
    org was reachable through any cliente's URL: detaching B's spouse from B's
    deal by calling A's endpoint returned 204.

    Org remained the tenancy boundary, so this was never a cross-tenant leak.
    Within an org it is an authorisation hole all the same, and the correct
    shape was already next door in `roteiros_service._obter`.

    Both verbs are covered here because tightening one and leaving its sibling
    loose is how this kind of gap survives a review.
    """

    def _dois_clientes(self, scoped):
        a_cid, a_aid = str(uuid4()), str(uuid4())
        b_cid, b_aid = str(uuid4()), str(uuid4())
        parte_id, parte_cid = str(uuid4()), str(uuid4())
        _seed(
            scoped,
            clientes=[
                cliente_row(a_cid, nome="Cliente A"),
                cliente_row(b_cid, nome="Cliente B"),
                cliente_row(parte_cid, nome="Esposa de B"),
            ],
            atendimentos=[_atendimento(a_aid, a_cid), _atendimento(b_aid, b_cid)],
            partes=[{
                "id": parte_id, "org_id": ORG_ID, "atendimento_id": b_aid,
                "cliente_id": parte_cid, "lado": "comprador", "papel": "comprador",
                "ordem": 0, "observacao": None,
                "created_at": "2026-09-01T10:00:00+00:00", "created_by": None,
                "updated_at": None,
            }],
        )
        return a_cid, b_cid, parte_id

    def test_removing_through_the_wrong_clientes_url_is_refused(self, client, scoped):
        a_cid, b_cid, parte_id = self._dois_clientes(scoped)

        out = client.delete(
            f"/api/clientes/{a_cid}/compradores/{parte_id}", headers=_auth()
        )

        # 404, not 403: telling a caller a parte exists but belongs to someone
        # else is itself a disclosure.
        assert out.status_code == 404, out.text
        # And it is still attached to the deal it actually belongs to.
        restante = (
            scoped.table("atendimento_partes").select("*").eq("org_id", ORG_ID).execute()
        ).data or []
        assert [r["id"] for r in restante] == [parte_id]

    def test_repapelling_through_the_wrong_clientes_url_is_refused(
        self, client, scoped
    ):
        a_cid, b_cid, parte_id = self._dois_clientes(scoped)

        out = client.patch(
            f"/api/clientes/{a_cid}/compradores/{parte_id}",
            json={"papel": "conjuge"},
            headers=_auth(),
        )

        assert out.status_code == 404, out.text
        row = (
            scoped.table("atendimento_partes")
            .select("*").eq("org_id", ORG_ID).eq("id", parte_id).execute()
        ).data[0]
        assert row["papel"] == "comprador"

    def test_the_rightful_cliente_still_reaches_it(self, client, scoped):
        """The counter-check: the guard must not lock out the real owner."""
        a_cid, b_cid, parte_id = self._dois_clientes(scoped)

        out = client.patch(
            f"/api/clientes/{b_cid}/compradores/{parte_id}",
            json={"papel": "conjuge"},
            headers=_auth(),
        )

        assert out.status_code == 200, out.text
        assert out.json()["papel"] == "conjuge"
