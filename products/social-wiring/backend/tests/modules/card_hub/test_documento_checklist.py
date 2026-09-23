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
            # ONE item for both numbers (owner directive, 2026-09-23).
            "Documento de identidade (RG e CPF)",
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
            f"/api/clientes/{cid}/documento-checklist/identidade",
            json={"concluido": True},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["concluido"] is True

        body = client.get(f"/api/clientes/{cid}/documento-checklist", headers=_auth()).json()
        assert body["concluidos"] == 1
        assert next(i for i in body["items"] if i["key"] == "identidade")["concluido"] is True
        # untouched items stay untouched
        assert next(i for i in body["items"] if i["key"] == "genero")["concluido"] is False

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
            f"/api/clientes/{cid}/documento-checklist/identidade",
            json={"concluido": True},
            headers=_auth(),
        )
        resp = client.patch(
            f"/api/clientes/{cid}/documento-checklist/identidade",
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

    def test_the_retired_rg_and_cpf_keys_are_422(self, client, scoped):
        """`rg`/`cpf` collapsed into `identidade` — a stale client still
        PATCHing the old keys must be told, not silently write a row the
        derivation never reads again."""
        cid = _seed(scoped)
        for key in ("rg", "cpf"):
            resp = client.patch(
                f"/api/clientes/{cid}/documento-checklist/{key}",
                json={"concluido": True},
                headers=_auth(),
            )
            assert resp.status_code == 422, resp.text


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


class TestIdentidadeItem:
    """The ONE identity item (owner directive, 2026-09-23): two upload slots
    (CIN, CNH), satisfied by the RG and CPF VALUES, naming what is missing."""

    def _itens(self, client, cid) -> dict:
        return {
            i["key"]: i
            for i in client.get(
                f"/api/clientes/{cid}/documento-checklist", headers=_auth()
            ).json()["items"]
        }

    def test_offers_a_cin_and_a_cnh_slot_with_the_one_of_two_hint(self, client, scoped):
        cid = _seed(scoped)
        scoped.set_table_data("cliente_documentos", [])
        item = self._itens(client, cid)["identidade"]
        assert [(s["tipo_documento"], s["rotulo"], s["upload"]) for s in item["documentos"]] == [
            ("cin", "CIN", True),
            ("cnh", "CNH", True),
        ]
        assert all(s["documento"] is None for s in item["documentos"])
        assert "Basta um dos dois" in item["dica"]
        # The item-level single-file key stays null — the slots name the files.
        assert item["documento"] is None

    def test_an_uploaded_cnh_is_named_in_its_slot(self, client, scoped):
        cid = _seed(scoped)
        did = str(uuid4())
        scoped.set_table_data(
            "cliente_documentos",
            [documento_row(did, cid, tipo_documento="cnh", categoria_lgpd="identidade")],
        )
        slots = {s["tipo_documento"]: s for s in self._itens(client, cid)["identidade"]["documentos"]}
        assert slots["cnh"]["documento"] == {
            "id": did,
            "nome_original": "arquivo.pdf",
            "mime_type": "application/pdf",
            "tamanho_bytes": 1024,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        assert slots["cin"]["documento"] is None

    def test_a_file_alone_does_not_satisfy_it_and_both_numbers_are_named(self, client, scoped):
        """An unread CIN (never extracted) or a CNH whose numbers were not
        confirmed yet satisfies nothing — the item says which are missing."""
        cid = _seed(scoped)
        scoped.set_table_data(
            "cliente_documentos", [documento_row(str(uuid4()), cid, tipo_documento="cin")]
        )
        item = self._itens(client, cid)["identidade"]
        assert item["concluido"] is False
        assert item["faltando"] == ["rg", "cpf"]
        assert item["faltando_rotulos"] == ["RG", "CPF"]

    def test_only_the_missing_number_is_named(self, client, scoped):
        cid = _seed(scoped)
        scoped.set_table_data("clientes", [cliente_row(cid, cpf="412.954.238-98")])
        scoped.set_table_data("cliente_documentos", [])
        item = self._itens(client, cid)["identidade"]
        assert item["concluido"] is False
        assert item["faltando"] == ["rg"]

    def test_both_numbers_satisfy_it(self, client, scoped):
        cid = _seed(scoped)
        scoped.set_table_data(
            "clientes", [cliente_row(cid, cpf="412.954.238-98", rg="52.179.965-X")]
        )
        scoped.set_table_data("cliente_documentos", [])
        item = self._itens(client, cid)["identidade"]
        assert item["concluido"] is True
        assert item["faltando"] == []

    def test_a_cin_whose_rg_equals_its_cpf_is_satisfied(self, client, scoped):
        """A CIN prints the CPF as the identity number — valid, never flagged."""
        cid = _seed(scoped)
        scoped.set_table_data(
            "clientes",
            [cliente_row(cid, cpf="448.864.938-66", rg="448.864.938-66")],
        )
        scoped.set_table_data(
            "cliente_documentos", [documento_row(str(uuid4()), cid, tipo_documento="cin")]
        )
        item = self._itens(client, cid)["identidade"]
        assert item["concluido"] is True
        assert item["faltando"] == []

    def test_a_legacy_rg_typed_file_is_listed_read_only(self, client, scoped):
        """A CNH filed as `rg` before `cnh` existed (migration 142) stays
        visible — never retyped, never offered as an upload target."""
        cid = _seed(scoped)
        did = str(uuid4())
        scoped.set_table_data(
            "clientes", [cliente_row(cid, cpf="412.954.238-98", rg="52.179.965-X")]
        )
        scoped.set_table_data(
            "cliente_documentos", [documento_row(did, cid, tipo_documento="rg")]
        )
        item = self._itens(client, cid)["identidade"]
        legado = [s for s in item["documentos"] if not s["upload"]]
        assert [(s["tipo_documento"], s["rotulo"]) for s in legado] == [("rg", "Arquivado como RG")]
        assert legado[0]["documento"]["id"] == did
        assert item["concluido"] is True
        assert scoped.table("cliente_documentos").select("*").execute().data[0]["tipo_documento"] == "rg"

    def test_a_soft_deleted_file_is_not_named(self, client, scoped):
        cid = _seed(scoped)
        scoped.set_table_data(
            "cliente_documentos",
            [
                documento_row(
                    str(uuid4()), cid, tipo_documento="cnh",
                    deleted_at="2026-03-01T00:00:00+00:00",
                )
            ],
        )
        slots = {s["tipo_documento"]: s for s in self._itens(client, cid)["identidade"]["documentos"]}
        assert slots["cnh"]["documento"] is None

    def test_the_most_recent_upload_wins(self, client, scoped):
        cid = _seed(scoped)
        antigo, novo = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "cliente_documentos",
            [
                documento_row(antigo, cid, tipo_documento="cnh", created_at="2026-01-01T00:00:00+00:00"),
                documento_row(novo, cid, tipo_documento="cnh", created_at="2026-05-05T00:00:00+00:00"),
            ],
        )
        slots = {s["tipo_documento"]: s for s in self._itens(client, cid)["identidade"]["documentos"]}
        assert slots["cnh"]["documento"]["id"] == novo

    def test_the_patch_response_carries_the_same_shape_as_the_get(self, client, scoped):
        """The card writes the PATCH response straight back into its list, so a
        narrower shape here would blank the slots until the next refetch."""
        cid = _seed(scoped)
        did = str(uuid4())
        scoped.set_table_data(
            "cliente_documentos", [documento_row(did, cid, tipo_documento="cin")]
        )
        resp = client.patch(
            f"/api/clientes/{cid}/documento-checklist/identidade",
            json={"concluido": True},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        slots = {s["tipo_documento"]: s for s in resp.json()["documentos"]}
        assert slots["cin"]["documento"]["id"] == did
        assert resp.json()["faltando"] == ["rg", "cpf"]

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
        itens = self._itens(client, cid)
        assert itens["profissao"]["concluido"] is True
        assert all(
            "documento" in i for i in itens.values()
        ), "every item carries the key — one row shape, not two"
        assert all(i["documento"] is None for i in itens.values())
        assert all(
            "documentos" not in itens[key]
            for key in ("nome_completo", "celular", "email", "data_nascimento",
                        "profissao", "genero")
        )
