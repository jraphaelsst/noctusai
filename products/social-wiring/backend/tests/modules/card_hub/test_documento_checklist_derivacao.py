"""The checklist DERIVES from the data (migration 068).

WHAT THESE TESTS PIN
--------------------
Migration 067 shipped the checklist as stored tick-state, and 068 turned it
into a derived view of completeness with a human override on top. The design
claim is that a tick can never disagree with the data behind it, so:

- filling a cliente column ticks its item, with nothing notified and no hook;
- uploading a document ticks its item, and soft-deleting it unticks;
- a human override outranks the derivation in BOTH directions;
- clearing the override hands the item back.

The first two are what make ingestion-path coverage total. Meta leadgen, OLX,
ImovelWeb, Vista, the XLSX importer and the manual form all write the same
columns, so none of them needs to know this feature exists — and a seventh
channel added later is covered the day it lands.
"""
from __future__ import annotations

from uuid import uuid4

from app.modules.card_hub import documento_checklist_service as svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _seed(scoped, **cliente_extra) -> str:
    cid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid, **cliente_extra)])
    scoped.set_table_data("cliente_documento_checklist", [])
    scoped.set_table_data("cliente_documentos", [])
    return cid


def _doc(cid, tipo, *, deleted_at=None) -> dict:
    return {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "cliente_id": cid,
        "tipo_documento": tipo,
        "deleted_at": deleted_at,
    }


def _items(client, cid) -> dict:
    body = client.get(f"/api/clientes/{cid}/documento-checklist", headers=_auth()).json()
    return {i["key"]: i for i in body["items"]}


class TestDerivarIsPure:
    """The rule as a function — no DB, no org, no request."""

    def test_empty_client_satisfies_nothing(self):
        assert svc.derivar(None, frozenset()) == {k: False for k in svc.ITEM_KEYS}

    def test_a_filled_column_satisfies_its_item(self):
        out = svc.derivar({"data_nascimento": "1980-05-12"}, frozenset())
        assert out["data_nascimento"] is True
        assert out["email"] is False

    def test_an_uploaded_type_satisfies_its_item(self):
        out = svc.derivar({}, frozenset({"rg"}))
        assert out["rg"] is True
        assert out["cpf"] is False

    def test_whitespace_only_is_not_filled_in(self):
        """A name of "   " satisfies a NOT NULL check and satisfies nobody
        else; ticking it would claim work no human would accept."""
        assert svc.derivar({"nome_completo": "   "}, frozenset())["nome_completo"] is False

    def test_every_item_is_covered_by_exactly_one_rule(self):
        """No item may be silently underivable — that would be a checkbox
        nothing can ever tick except by hand."""
        for item in svc.ITENS:
            assert ("campo" in item) ^ ("documento" in item), item["key"]


class TestFieldsTickThemselves:
    def test_filling_columns_ticks_their_items_with_no_write_to_the_tick_table(
        self, client, scoped
    ):
        """🔴 The core claim. No hook ran; the tick is a read of the data."""
        cid = _seed(
            scoped,
            nome_completo="Ana Maria Silva",
            email="ana@example.com",
            data_nascimento="1980-05-12",
            genero="feminino",
        )
        items = _items(client, cid)
        assert [items[k]["concluido"] for k in
                ("nome_completo", "email", "data_nascimento", "genero")] == [True] * 4
        assert all(items[k]["origem"] == "derivado" for k in svc.ITEM_KEYS)
        assert scoped.table("cliente_documento_checklist").select("*").execute().data == []

    def test_patching_the_cliente_ticks_the_item(self, client, scoped):
        """"Checked upon editing the object with the data" — via the normal
        cliente PATCH, with no checklist call anywhere.

        Seeded through BOTH DI seams because this crosses two routers:
        `clientes_router.get_clientes_client` and
        `card_hub.deps.get_card_hub_client` are independently-keyed caches over
        the same mock, so a row seeded through one is invisible to the other
        (see the conftest docstring). That is a test-harness property, not a
        production one — in prod both resolve to the same Postgres schema.
        """
        from app.routers.clientes_router import get_clientes_client

        cid = _seed(scoped)
        clientes_scoped = get_clientes_client()
        clientes_scoped.set_table_data("clientes", [cliente_row(cid)])
        assert _items(client, cid)["data_nascimento"]["concluido"] is False

        r = client.patch(
            f"/api/clientes/{cid}",
            json={"data_nascimento": "1980-05-12"},
            headers=_auth(),
        )
        assert r.status_code == 200, r.text

        # Mirror the write back onto the card_hub-scoped view, which is the
        # same table in production.
        scoped.set_table_data(
            "clientes", clientes_scoped.table("clientes").select("*").execute().data
        )
        assert _items(client, cid)["data_nascimento"]["concluido"] is True

    def test_nome_completo_is_not_satisfied_by_the_channel_supplied_nome(
        self, client, scoped
    ):
        """🔴 `nome` is a WhatsApp push name / Meta `full_name` / OLX handle.
        Treating it as the legal full name would auto-tick this item for
        essentially every lead in the product."""
        cid = _seed(scoped, nome="Ana")
        assert _items(client, cid)["nome_completo"]["concluido"] is False


class TestDocumentsTickThemselves:
    def test_an_uploaded_rg_ticks_rg(self, client, scoped):
        cid = _seed(scoped)
        scoped.set_table_data("cliente_documentos", [_doc(cid, "rg")])
        items = _items(client, cid)
        assert items["rg"]["concluido"] is True
        assert items["cpf"]["concluido"] is False

    def test_a_soft_deleted_document_stops_satisfying_its_item(self, client, scoped):
        """A document the client asked us to delete cannot go on backing a
        requirement — otherwise the checklist claims we still hold it."""
        cid = _seed(scoped)
        scoped.set_table_data(
            "cliente_documentos", [_doc(cid, "rg", deleted_at="2026-08-22T00:00:00+00:00")]
        )
        assert _items(client, cid)["rg"]["concluido"] is False

    def test_another_clients_document_does_not_tick_this_one(self, client, scoped):
        cid = _seed(scoped)
        scoped.set_table_data("cliente_documentos", [_doc(str(uuid4()), "rg")])
        assert _items(client, cid)["rg"]["concluido"] is False


class TestManualOverride:
    def test_override_can_tick_an_item_the_data_cannot_prove(self, client, scoped):
        """The reason the override survives at all: a human may know
        something the record cannot show."""
        cid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/documento-checklist/genero",
            json={"concluido": True},
            headers=_auth(),
        )
        assert r.status_code == 200, r.text
        item = _items(client, cid)["genero"]
        assert item["concluido"] is True
        assert item["origem"] == "manual"
        assert item["derivado"] is False, "the derivation is still reported honestly"

    def test_override_can_untick_an_item_the_data_does_satisfy(self, client, scoped):
        cid = _seed(scoped, data_nascimento="1980-05-12")
        client.patch(
            f"/api/clientes/{cid}/documento-checklist/data_nascimento",
            json={"concluido": False},
            headers=_auth(),
        )
        item = _items(client, cid)["data_nascimento"]
        assert item["concluido"] is False
        assert item["origem"] == "manual"
        assert item["derivado"] is True

    def test_clearing_the_override_hands_the_item_back(self, client, scoped):
        """🔴 Without this, the first person to touch an item pins it forever,
        including pinning a `false` onto a client who later supplies the data —
        the stale-checklist bug, reintroduced by hand."""
        cid = _seed(scoped, email="ana@example.com")
        client.patch(
            f"/api/clientes/{cid}/documento-checklist/email",
            json={"concluido": False},
            headers=_auth(),
        )
        assert _items(client, cid)["email"]["concluido"] is False

        r = client.patch(
            f"/api/clientes/{cid}/documento-checklist/email",
            json={"concluido": None},
            headers=_auth(),
        )
        assert r.status_code == 200, r.text
        item = _items(client, cid)["email"]
        assert item["concluido"] is True
        assert item["origem"] == "derivado"

    def test_an_unknown_key_is_still_a_422(self, client, scoped):
        cid = _seed(scoped)
        r = client.patch(
            f"/api/clientes/{cid}/documento-checklist/altura",
            json={"concluido": True},
            headers=_auth(),
        )
        assert r.status_code == 422

    def test_concluidos_counts_the_effective_state(self, client, scoped):
        cid = _seed(scoped, email="ana@example.com", genero="feminino")
        scoped.set_table_data("cliente_documentos", [_doc(cid, "cpf")])
        body = client.get(
            f"/api/clientes/{cid}/documento-checklist", headers=_auth()
        ).json()
        assert body["concluidos"] == 3
