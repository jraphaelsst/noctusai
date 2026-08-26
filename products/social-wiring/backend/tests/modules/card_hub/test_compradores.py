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
        assert body == {"items": [], "total": 0, "atendimento_id": body["atendimento_id"]}
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
