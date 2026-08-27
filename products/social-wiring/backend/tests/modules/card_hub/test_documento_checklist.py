"""The permanent document checklist (migration 067).

WHAT THESE TESTS PIN
--------------------
The design claim is that the ITEM LIST is canonical code and only the TICKS are
data. Every assertion here is a consequence of that:

- a client with no rows still gets every item (definition drives output);
- an unknown key is a 422, not a silently-written row nothing reads;
- the label can change without orphaning a tick, because `item_key` is the
  identity and the label is presentation.

If someone later "simplifies" this into one row per item per client, the first
and third break — which is the point.
"""
from __future__ import annotations

from uuid import uuid4

from app.modules.card_hub import documento_checklist_service as svc
from tests.modules.card_hub.conftest import ORG_ID, cliente_row, documento_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _seed(scoped) -> str:
    cid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid)])
    scoped.set_table_data("cliente_documento_checklist", [])
    return cid


class TestCanonicalList:
    def test_the_fields_the_user_asked_for_in_order(self, client, scoped):
        """🔴 The list, verbatim. It is a contract, not a default.

        The ORDER is part of it: this is the sequence an operator actually
        collects the details in, so the card read top-to-bottom shows the next
        thing to ask for. Alphabetising it would be a regression, not a tidy-up.
        """
        cid = _seed(scoped)
        body = client.get(f"/api/clientes/{cid}/documento-checklist", headers=_auth()).json()
        assert [i["label"] for i in body["items"]] == [
            "Nome Completo",
            "Celular",
            "Email",
            "Data de Nascimento",
            "Profissão",
            "Gênero",
            "RG",
            "CPF",
        ]

    def test_a_client_with_no_rows_still_gets_every_item_unticked(self, client, scoped):
        """The checklist is PERMANENT — it exists before anyone touches it.

        Nothing is created on read: a GET that writes would mean the first
        person to open a card silently authors a row per item on it.
        """
        cid = _seed(scoped)
        body = client.get(f"/api/clientes/{cid}/documento-checklist", headers=_auth()).json()
        assert body["total"] == len(svc.ITENS)
        assert body["concluidos"] == 0
        assert all(i["concluido"] is False for i in body["items"])
        assert scoped.table("cliente_documento_checklist").select("*").execute().data == []

    def test_every_card_gets_the_same_list(self, client, scoped):
        """Two clients, one definition — no per-card divergence to drift."""
        cid_a = _seed(scoped)
        cid_b = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid_a), cliente_row(cid_b)])
        a = client.get(f"/api/clientes/{cid_a}/documento-checklist", headers=_auth()).json()
        b = client.get(f"/api/clientes/{cid_b}/documento-checklist", headers=_auth()).json()
        assert [i["key"] for i in a["items"]] == [i["key"] for i in b["items"]]


class TestTicking:
    def test_tick_persists_and_counts(self, client, scoped):
        cid = _seed(scoped)
        resp = client.patch(
            f"/api/clientes/{cid}/documento-checklist/cpf",
            json={"concluido": True},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["concluido"] is True

        body = client.get(f"/api/clientes/{cid}/documento-checklist", headers=_auth()).json()
        assert body["concluidos"] == 1
        assert next(i for i in body["items"] if i["key"] == "cpf")["concluido"] is True
        # untouched items stay untouched
        assert next(i for i in body["items"] if i["key"] == "rg")["concluido"] is False

    def test_ticking_twice_does_not_create_a_second_row(self, client, scoped):
        """The unique index is the guarantee; this is the behaviour it buys."""
        cid = _seed(scoped)
        for _ in range(2):
            client.patch(
                f"/api/clientes/{cid}/documento-checklist/email",
                json={"concluido": True},
                headers=_auth(),
            )
        rows = scoped.table("cliente_documento_checklist").select("*").execute().data
        assert len([r for r in rows if r["item_key"] == "email"]) == 1

    def test_untick_clears_the_timestamp(self, client, scoped):
        """A `concluido_em` left on an unticked item reads as "done, once" —
        the opposite of what the untick just said."""
        cid = _seed(scoped)
        client.patch(
            f"/api/clientes/{cid}/documento-checklist/rg",
            json={"concluido": True},
            headers=_auth(),
        )
        resp = client.patch(
            f"/api/clientes/{cid}/documento-checklist/rg",
            json={"concluido": False},
            headers=_auth(),
        )
        assert resp.json()["concluido"] is False
        assert resp.json()["concluido_em"] is None

    def test_an_unknown_key_is_422_not_a_silent_write(self, client, scoped):
        cid = _seed(scoped)
        resp = client.patch(
            f"/api/clientes/{cid}/documento-checklist/numero_da_sorte",
            json={"concluido": True},
            headers=_auth(),
        )
        assert resp.status_code == 422, resp.text
        assert scoped.table("cliente_documento_checklist").select("*").execute().data == []


class TestDefinitionIsCode:
    def test_a_relabel_does_not_orphan_a_tick(self, client, scoped):
        """`item_key` is identity, `label` is presentation.

        Renaming an item must be a one-word edit every card picks up, with the
        existing ticks intact. That holds BY CONSTRUCTION, so this pins the
        construction instead of simulating a rename: the tick is stored under
        `item_key` with no label anywhere in the row, and every served label is
        read back out of :data:`svc.ITENS`. A relabel therefore cannot reach a
        stored tick — there is nothing in the row for it to invalidate.

        Six materialised rows per client would fail this: the label would be
        IN the row, and the rename would need a backfill.
        """
        cid = _seed(scoped)
        client.patch(
            f"/api/clientes/{cid}/documento-checklist/genero",
            json={"concluido": True},
            headers=_auth(),
        )

        rows = scoped.table("cliente_documento_checklist").select("*").execute().data
        assert [r["item_key"] for r in rows] == ["genero"], "the tick is keyed by key"
        labels = {i["label"] for i in svc.ITENS}
        assert not [
            (col, val)
            for row in rows
            for col, val in row.items()
            if isinstance(val, str) and val in labels
        ], "no label is persisted — that is exactly what makes a relabel free"

        body = client.get(f"/api/clientes/{cid}/documento-checklist", headers=_auth()).json()
        assert {i["key"]: i["label"] for i in body["items"]} == {
            i["key"]: i["label"] for i in svc.ITENS
        }, "every label served is read from the definition, never from the row"
        assert next(i for i in body["items"] if i["key"] == "genero")["concluido"] is True


class TestDocumentoOnDocumentSatisfiedItems:
    """A document-satisfied item NAMES the file behind its tick.

    The boolean alone could say only *that* an RG had been uploaded, so the card
    could render a tick but not a trash button — there was nothing to point it
    at, and an operator who noticed the wrong scan had to leave the checklist
    for the Documentos tab to delete it.
    """

    def test_an_uploaded_document_is_named_on_its_item(self, client, scoped):
        cid = _seed(scoped)
        did = str(uuid4())
        scoped.set_table_data(
            "cliente_documentos",
            [
                documento_row(
                    did, cid, tipo_documento="rg", categoria_lgpd="identidade"
                )
            ],
        )
        itens = {
            i["key"]: i
            for i in client.get(
                f"/api/clientes/{cid}/documento-checklist", headers=_auth()
            ).json()["items"]
        }
        assert itens["rg"]["concluido"] is True
        assert itens["rg"]["documento"] == {
            "id": did,
            "nome_original": "arquivo.pdf",
            "mime_type": "application/pdf",
            "tamanho_bytes": 1024,
            "created_at": "2026-01-01T00:00:00+00:00",
        }

    def test_a_document_item_with_no_upload_carries_a_null(self, client, scoped):
        cid = _seed(scoped)
        scoped.set_table_data("cliente_documentos", [])
        itens = {
            i["key"]: i
            for i in client.get(
                f"/api/clientes/{cid}/documento-checklist", headers=_auth()
            ).json()["items"]
        }
        assert itens["cpf"]["concluido"] is False
        assert itens["cpf"]["documento"] is None

    def test_typed_items_never_carry_a_documento(self, client, scoped):
        """A typed item is satisfied by a COLUMN — there is no file to name.

        The key is still emitted, so the card renders one row shape rather than
        branching on its presence.
        """
        cid = _seed(scoped)
        scoped.set_table_data(
            "clientes", [cliente_row(cid, nome="Ana Maria Souza", profissao="Corretora")]
        )
        scoped.set_table_data("cliente_documentos", [])
        itens = {
            i["key"]: i
            for i in client.get(
                f"/api/clientes/{cid}/documento-checklist", headers=_auth()
            ).json()["items"]
        }
        assert itens["profissao"]["concluido"] is True
        assert all(
            "documento" in i for i in itens.values()
        ), "every item carries the key — one row shape, not two"
        assert all(
            itens[key]["documento"] is None
            for key in ("nome_completo", "celular", "email", "data_nascimento",
                        "profissao", "genero")
        )

    def test_a_soft_deleted_document_is_not_named_and_does_not_tick(
        self, client, scoped
    ):
        """A document the client asked us to delete cannot go on satisfying a
        requirement it no longer backs — and must not be offered for deletion a
        second time."""
        cid = _seed(scoped)
        scoped.set_table_data(
            "cliente_documentos",
            [
                documento_row(
                    str(uuid4()),
                    cid,
                    tipo_documento="rg",
                    deleted_at="2026-03-01T00:00:00+00:00",
                )
            ],
        )
        itens = {
            i["key"]: i
            for i in client.get(
                f"/api/clientes/{cid}/documento-checklist", headers=_auth()
            ).json()["items"]
        }
        assert itens["rg"]["concluido"] is False
        assert itens["rg"]["documento"] is None

    def test_the_most_recent_upload_wins(self, client, scoped):
        """Two RGs on file: the one named is the one the card is showing, which
        is also the one a per-row trash button must discard."""
        cid = _seed(scoped)
        antigo, novo = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "cliente_documentos",
            [
                documento_row(
                    antigo, cid, tipo_documento="rg",
                    created_at="2026-01-01T00:00:00+00:00",
                ),
                documento_row(
                    novo, cid, tipo_documento="rg",
                    created_at="2026-05-05T00:00:00+00:00",
                ),
            ],
        )
        itens = {
            i["key"]: i
            for i in client.get(
                f"/api/clientes/{cid}/documento-checklist", headers=_auth()
            ).json()["items"]
        }
        assert itens["rg"]["documento"]["id"] == novo

    def test_the_patch_response_carries_the_same_shape_as_the_get(
        self, client, scoped
    ):
        """The card writes the PATCH response straight back into its list, so a
        narrower shape here would blank the trash button until the next
        refetch."""
        cid = _seed(scoped)
        did = str(uuid4())
        scoped.set_table_data(
            "cliente_documentos", [documento_row(did, cid, tipo_documento="cpf")]
        )
        resp = client.patch(
            f"/api/clientes/{cid}/documento-checklist/cpf",
            json={"concluido": True},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["documento"]["id"] == did
