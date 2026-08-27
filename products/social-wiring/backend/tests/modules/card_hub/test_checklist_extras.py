"""Operator-authored checklist lines (migration 083).

WHAT THESE TESTS PIN
--------------------
The design claim is that a line is a REQUEST and a document is only its current
ANSWER. Every assertion here is a consequence of that:

- `concluido` is derived, so it follows the data and can never be stored stale;
- uploading twice REPLACES (the request did not change, its answer did);
- deleting the file KEEPS the line (you are discarding the answer, not
  withdrawing the request);
- a crossed write is a 422, never a 200 that silently drops the value.

If someone later adds a `concluido` column, the derivation tests break — which
is the point.
"""
from __future__ import annotations

from uuid import uuid4

from app.modules.card_hub import checklist_extras_service as svc
from tests.modules.card_hub.conftest import (
    ORG_ID,
    checklist_extra_row,
    cliente_row,
    documento_row,
    documento_tipo_row,
    retencao_politica_row,
)


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def _seed(scoped, *, extras=None, documentos=None) -> str:
    """A client with an empty extras table.

    The tables are seeded to `[]` rather than left unset: an unset table in the
    mock has `None` data, which reads as "no rows" but does not accept inserts —
    a test that skipped this would pass its GET and silently lose its POST.
    """
    cid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(cid)])
    scoped.set_table_data("cliente_checklist_extras", list(extras or []))
    scoped.set_table_data("cliente_documentos", list(documentos or []))
    return cid


def _seed_upload_catalogue(scoped) -> None:
    """The document-type catalogue + retention policy an upload needs.

    `outro` specifically — `checklist_extras_service.TIPO_DOCUMENTO`. An
    operator-authored line has no taxonomy behind it by definition, and the
    catalogue's own answer for that is `outro`.
    """
    scoped.set_table_data(
        "cliente_documento_tipos",
        [documento_tipo_row(svc.TIPO_DOCUMENTO, categoria="nao_classificado")],
    )
    scoped.set_table_data(
        "documento_retencao_politicas",
        [retencao_politica_row(svc.TIPO_DOCUMENTO, dias=365)],
    )


def _listar(client, cid) -> list[dict]:
    resp = client.get(f"/api/clientes/{cid}/checklist-extras", headers=_auth())
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _criar(client, cid, *, label="Convenção", tipo="texto") -> dict:
    resp = client.post(
        f"/api/clientes/{cid}/checklist-extras",
        json={"label": label, "tipo": tipo},
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload(client, cid, extra_id, *, nome="scan.pdf", conteudo=b"%PDF-1.4 x"):
    return client.post(
        f"/api/clientes/{cid}/checklist-extras/{extra_id}/documento",
        files={"file": (nome, conteudo, "application/pdf")},
        headers=_auth(),
    )


# ─── CRUD ────────────────────────────────────────────────────────────────


class TestCrud:
    def test_a_new_client_has_no_extras(self, client, scoped):
        """Nothing is materialised per client. Unlike the mandatory list, these
        lines exist only because someone wrote them."""
        cid = _seed(scoped)
        body = client.get(
            f"/api/clientes/{cid}/checklist-extras", headers=_auth()
        ).json()
        assert body == {"items": [], "total": 0}

    def test_create_returns_the_full_row_shape(self, client, scoped):
        """🔴 The response contract the frontend is built against, verbatim."""
        cid = _seed(scoped)
        criado = _criar(client, cid, label="Convenção do condomínio")
        assert set(criado) == {
            "id",
            "label",
            "tipo",
            "valor_texto",
            "documento",
            "concluido",
            "ordem",
        }
        assert criado["label"] == "Convenção do condomínio"
        assert criado["tipo"] == "texto"
        assert criado["valor_texto"] is None
        assert criado["documento"] is None
        assert criado["concluido"] is False

    def test_create_persists_and_lists(self, client, scoped):
        cid = _seed(scoped)
        criado = _criar(client, cid)
        items = _listar(client, cid)
        assert [i["id"] for i in items] == [criado["id"]]

    def test_label_is_trimmed_on_create(self, client, scoped):
        cid = _seed(scoped)
        assert _criar(client, cid, label="  Escritura  ")["label"] == "Escritura"

    def test_new_lines_land_at_the_bottom(self, client, scoped):
        """`ordem` grows, so a line appears where the operator was looking.

        Defaulting every row to 0 would leave the list ordered by `created_at`
        alone — correct today, and silently wrong the moment drag-to-reorder
        writes a real `ordem` to one row.
        """
        cid = _seed(scoped)
        a = _criar(client, cid, label="A")
        b = _criar(client, cid, label="B")
        c = _criar(client, cid, label="C")
        assert [a["ordem"], b["ordem"], c["ordem"]] == [0, 1, 2]
        assert [i["label"] for i in _listar(client, cid)] == ["A", "B", "C"]

    def test_list_is_ordered_by_ordem_then_created_at(self, client, scoped):
        """Two lines sharing an `ordem` keep the order they were typed rather
        than shuffling between requests."""
        cid = _seed(scoped)
        eid_a, eid_b, eid_c = str(uuid4()), str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "cliente_checklist_extras",
            [
                checklist_extra_row(eid_c, cid, label="C", ordem=5),
                checklist_extra_row(
                    eid_b, cid, label="B", ordem=0, created_at="2026-02-02T00:00:00+00:00"
                ),
                checklist_extra_row(
                    eid_a, cid, label="A", ordem=0, created_at="2026-01-01T00:00:00+00:00"
                ),
            ],
        )
        assert [i["label"] for i in _listar(client, cid)] == ["A", "B", "C"]

    def test_patch_sets_valor_texto_and_label_and_ordem(self, client, scoped):
        cid = _seed(scoped)
        criado = _criar(client, cid)
        resp = client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"label": "Novo rótulo", "valor_texto": "1234-5", "ordem": 7},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["label"] == "Novo rótulo"
        assert body["valor_texto"] == "1234-5"
        assert body["ordem"] == 7

    def test_patch_only_writes_what_it_carried(self, client, scoped):
        """Absence means "leave alone" — a PATCH that only moves a line must
        not blank the text somebody typed into it."""
        cid = _seed(scoped)
        criado = _criar(client, cid)
        client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"valor_texto": "mantém"},
            headers=_auth(),
        )
        body = client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"ordem": 3},
            headers=_auth(),
        ).json()
        assert body["valor_texto"] == "mantém"
        assert body["ordem"] == 3

    def test_explicit_null_valor_texto_clears_it(self, client, scoped):
        """`None` is a real value here, which is why the route reads
        `model_fields_set` and not `exclude_none`."""
        cid = _seed(scoped)
        criado = _criar(client, cid)
        client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"valor_texto": "algo"},
            headers=_auth(),
        )
        body = client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"valor_texto": None},
            headers=_auth(),
        ).json()
        assert body["valor_texto"] is None
        assert body["concluido"] is False

    def test_blank_label_is_refused_not_stored(self, client, scoped):
        """A row nobody can identify is indistinguishable from a rendering bug.
        `NOT NULL` cannot express "not blank"; this does."""
        cid = _seed(scoped)
        criado = _criar(client, cid)
        resp = client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"label": "   "},
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert _listar(client, cid)[0]["label"] == "Convenção"

    def test_delete_is_a_soft_delete(self, client, scoped):
        """The row survives with `deleted_at` — one UPDATE to undo, per the
        card_hub convention."""
        cid = _seed(scoped)
        criado = _criar(client, cid)
        resp = client.delete(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}", headers=_auth()
        )
        assert resp.status_code == 204, resp.text
        assert _listar(client, cid) == []

        stored = scoped.table("cliente_checklist_extras").select("*").execute().data
        assert len(stored) == 1
        assert stored[0]["deleted_at"] is not None

    def test_another_clients_line_is_a_404_not_an_edit(self, client, scoped):
        """The ownership check IS the security boundary — an id alone must
        never be enough to edit a line on someone else's card."""
        cid = _seed(scoped)
        criado = _criar(client, cid)
        outro = str(uuid4())
        scoped.set_table_data(
            "clientes", [cliente_row(cid), cliente_row(outro)]
        )
        resp = client.patch(
            f"/api/clientes/{outro}/checklist-extras/{criado['id']}",
            json={"label": "invadido"},
            headers=_auth(),
        )
        assert resp.status_code == 404, resp.text

    def test_unknown_extra_is_a_404(self, client, scoped):
        cid = _seed(scoped)
        resp = client.delete(
            f"/api/clientes/{cid}/checklist-extras/{uuid4()}", headers=_auth()
        )
        assert resp.status_code == 404, resp.text


# ─── the derivation ──────────────────────────────────────────────────────


class TestConcluidoIsDerived:
    def test_texto_line_ticks_when_it_has_text(self, client, scoped):
        cid = _seed(scoped)
        criado = _criar(client, cid, tipo="texto")
        assert criado["concluido"] is False
        body = client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"valor_texto": "Bloco B, apto 42"},
            headers=_auth(),
        ).json()
        assert body["concluido"] is True

    def test_whitespace_only_text_does_not_tick(self, client, scoped):
        """`"   "` satisfies NOT NULL and satisfies nobody."""
        cid = _seed(scoped)
        criado = _criar(client, cid, tipo="texto")
        body = client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"valor_texto": "   "},
            headers=_auth(),
        ).json()
        assert body["valor_texto"] is None
        assert body["concluido"] is False

    def test_arquivo_line_ticks_only_with_a_live_document(self, client, scoped):
        cid = _seed(scoped)
        criado = _criar(client, cid, tipo="arquivo")
        assert criado["concluido"] is False

    def test_a_soft_deleted_document_unticks_the_line(self, client, scoped):
        """🔴 THE reason completion is derived rather than stored.

        `run_retention_sweep` soft-deletes documents on a schedule and knows
        nothing about this table. A stored tick would outlive the file it
        asserts; a derived one cannot.
        """
        cid = _seed(scoped)
        did, eid = str(uuid4()), str(uuid4())
        scoped.set_table_data(
            "cliente_documentos",
            [documento_row(did, cid, deleted_at="2026-03-01T00:00:00+00:00")],
        )
        scoped.set_table_data(
            "cliente_checklist_extras",
            [checklist_extra_row(eid, cid, tipo="arquivo", documento_id=did)],
        )
        linha = _listar(client, cid)[0]
        assert linha["documento"] is None
        assert linha["concluido"] is False

    def test_nothing_stores_a_concluido_column(self, client, scoped):
        """The pure rule and the persisted row must not both claim to know."""
        cid = _seed(scoped)
        criado = _criar(client, cid)
        client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"valor_texto": "x"},
            headers=_auth(),
        )
        stored = scoped.table("cliente_checklist_extras").select("*").execute().data[0]
        assert "concluido" not in stored

    def test_the_rule_is_a_pure_function(self):
        """Callable without a database, an org, or an HTTP request — the same
        property `documento_checklist_service.derivar` has, for the same
        reason: this decides whether a card claims a request was answered."""
        assert svc.concluido_de({"tipo": "texto", "valor_texto": "ok"}, None) is True
        assert svc.concluido_de({"tipo": "texto", "valor_texto": " "}, None) is False
        assert svc.concluido_de({"tipo": "texto", "valor_texto": None}, None) is False
        assert svc.concluido_de({"tipo": "arquivo"}, None) is False
        assert svc.concluido_de({"tipo": "arquivo"}, {"id": "d"}) is True


# ─── documents on a line ─────────────────────────────────────────────────


class TestDocumento:
    def test_upload_links_the_document_and_ticks(self, client, scoped, fake_storage):
        cid = _seed(scoped)
        _seed_upload_catalogue(scoped)
        criado = _criar(client, cid, tipo="arquivo")

        resp = _upload(client, cid, criado["id"], nome="convencao.pdf")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["concluido"] is True
        assert body["documento"]["nome_original"] == "convencao.pdf"
        assert set(body["documento"]) == {
            "id",
            "nome_original",
            "mime_type",
            "tamanho_bytes",
            "created_at",
        }

    def test_upload_goes_through_documentos_service_not_a_second_path(
        self, client, scoped, fake_storage
    ):
        """One path in, so the file gets the same storage layout, LGPD category
        and retention clock every other document does."""
        cid = _seed(scoped)
        _seed_upload_catalogue(scoped)
        criado = _criar(client, cid, tipo="arquivo")
        _upload(client, cid, criado["id"])

        docs = scoped.table("cliente_documentos").select("*").execute().data
        assert len(docs) == 1
        assert docs[0]["tipo_documento"] == svc.TIPO_DOCUMENTO
        assert docs[0]["categoria_lgpd"] == "nao_classificado"
        assert docs[0]["retencao_ate"] is not None
        assert docs[0]["storage_path"].startswith(f"{ORG_ID}/clientes/{cid}/")

    def test_upload_onto_an_occupied_line_replaces(
        self, client, scoped, fake_storage
    ):
        """The request did not change; its answer did. The displaced document is
        soft-deleted rather than orphaned, so it keeps its access log and stays
        visible in the Documentos tab as history."""
        cid = _seed(scoped)
        _seed_upload_catalogue(scoped)
        criado = _criar(client, cid, tipo="arquivo")

        primeiro = _upload(client, cid, criado["id"], nome="errado.pdf").json()
        segundo = _upload(client, cid, criado["id"], nome="certo.pdf").json()

        assert segundo["documento"]["nome_original"] == "certo.pdf"
        assert segundo["documento"]["id"] != primeiro["documento"]["id"]
        assert segundo["concluido"] is True

        docs = {
            d["id"]: d
            for d in scoped.table("cliente_documentos").select("*").execute().data
        }
        assert docs[primeiro["documento"]["id"]]["deleted_at"] is not None
        assert docs[segundo["documento"]["id"]]["deleted_at"] is None

        # One live line, still — replacing an answer must not add a request.
        assert len(_listar(client, cid)) == 1

    def test_delete_documento_keeps_the_line(self, client, scoped, fake_storage):
        """🔴 THE product rule: the card stays there, the doc is deleted for a
        fresh upload. A cascade that removed the line would delete the REQUEST
        because someone sent the wrong scan."""
        cid = _seed(scoped)
        _seed_upload_catalogue(scoped)
        criado = _criar(client, cid, tipo="arquivo")
        enviado = _upload(client, cid, criado["id"]).json()

        resp = client.delete(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}/documento",
            headers=_auth(),
        )
        assert resp.status_code == 204, resp.text

        items = _listar(client, cid)
        assert len(items) == 1
        assert items[0]["id"] == criado["id"]
        assert items[0]["documento"] is None
        assert items[0]["concluido"] is False

        docs = scoped.table("cliente_documentos").select("*").execute().data
        assert docs[0]["id"] == enviado["documento"]["id"]
        assert docs[0]["deleted_at"] is not None

    def test_the_line_accepts_a_fresh_upload_after_a_delete(
        self, client, scoped, fake_storage
    ):
        """"...for a fresh upload" is the second half of the rule, and it is the
        half a soft-delete could quietly break."""
        cid = _seed(scoped)
        _seed_upload_catalogue(scoped)
        criado = _criar(client, cid, tipo="arquivo")
        _upload(client, cid, criado["id"], nome="errado.pdf")
        client.delete(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}/documento",
            headers=_auth(),
        )
        de_novo = _upload(client, cid, criado["id"], nome="certo.pdf")
        assert de_novo.status_code == 200, de_novo.text
        assert de_novo.json()["documento"]["nome_original"] == "certo.pdf"
        assert de_novo.json()["concluido"] is True

    def test_delete_documento_appends_to_the_lgpd_access_log(
        self, client, scoped, fake_storage
    ):
        """Deleting a file is an LGPD delete wherever it is triggered from —
        going through `documentos_service` is what keeps that true."""
        cid = _seed(scoped)
        _seed_upload_catalogue(scoped)
        scoped.set_table_data("cliente_documento_acessos", [])
        criado = _criar(client, cid, tipo="arquivo")
        _upload(client, cid, criado["id"])
        client.delete(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}/documento",
            headers=_auth(),
        )
        acessos = scoped.table("cliente_documento_acessos").select("*").execute().data
        assert [a["acao"] for a in acessos] == ["delete"]

    def test_delete_documento_on_an_empty_line_is_a_no_op(
        self, client, scoped, fake_storage
    ):
        """Deleting an absent file is not an error — a 404 here would make the
        trash button race its own refetch."""
        cid = _seed(scoped)
        criado = _criar(client, cid, tipo="arquivo")
        resp = client.delete(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}/documento",
            headers=_auth(),
        )
        assert resp.status_code == 204, resp.text
        assert len(_listar(client, cid)) == 1

    def test_removing_the_line_does_not_delete_the_document(
        self, client, scoped, fake_storage
    ):
        """The inverse of the rule above. A document is a real file in this
        client's Documentos tab with its own retention clock; removing a
        checklist line is not a request to erase it."""
        cid = _seed(scoped)
        _seed_upload_catalogue(scoped)
        criado = _criar(client, cid, tipo="arquivo")
        _upload(client, cid, criado["id"])
        client.delete(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}", headers=_auth()
        )
        docs = scoped.table("cliente_documentos").select("*").execute().data
        assert docs[0]["deleted_at"] is None


    def test_replace_survives_a_previous_document_already_swept(
        self, client, scoped, fake_storage
    ):
        """The retention sweep soft-deletes on a schedule and knows nothing
        about this table, so the row a line points at can already be gone. The
        replacement must still land — a 404 here would leave the file the
        operator just uploaded attached to nothing."""
        cid = _seed(scoped)
        _seed_upload_catalogue(scoped)
        criado = _criar(client, cid, tipo="arquivo")
        primeiro = _upload(client, cid, criado["id"], nome="antigo.pdf").json()

        scoped.table("cliente_documentos").update(
            {"deleted_at": "2026-04-01T00:00:00+00:00"}
        ).eq("id", primeiro["documento"]["id"]).execute()

        resp = _upload(client, cid, criado["id"], nome="novo.pdf")
        assert resp.status_code == 200, resp.text
        assert resp.json()["documento"]["nome_original"] == "novo.pdf"
        assert resp.json()["concluido"] is True

    def test_delete_survives_a_document_already_swept(
        self, client, scoped, fake_storage
    ):
        """Same race, other verb. The operator asked for the line to be empty
        and it is; refusing would leave a dangling `documento_id` on a line the
        card already renders as empty."""
        cid = _seed(scoped)
        _seed_upload_catalogue(scoped)
        criado = _criar(client, cid, tipo="arquivo")
        enviado = _upload(client, cid, criado["id"]).json()

        scoped.table("cliente_documentos").update(
            {"deleted_at": "2026-04-01T00:00:00+00:00"}
        ).eq("id", enviado["documento"]["id"]).execute()

        resp = client.delete(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}/documento",
            headers=_auth(),
        )
        assert resp.status_code == 204, resp.text
        stored = scoped.table("cliente_checklist_extras").select("*").execute().data[0]
        assert stored["documento_id"] is None, "the dangling link must be cleared"
        assert stored["deleted_at"] is None, "the LINE survives"


# ─── tipo mismatches ─────────────────────────────────────────────────────


class TestTipoMismatch:
    def test_texto_line_refuses_a_document_upload(self, client, scoped, fake_storage):
        """422, not a silent ignore: `tipo` is chosen at creation and returned
        on every read, so this is a caller bug and must say so."""
        cid = _seed(scoped)
        _seed_upload_catalogue(scoped)
        criado = _criar(client, cid, tipo="texto")

        resp = _upload(client, cid, criado["id"])
        assert resp.status_code == 422, resp.text

        # And nothing landed — a refusal that still stored the file would be
        # worse than accepting it.
        assert scoped.table("cliente_documentos").select("*").execute().data == []
        assert _listar(client, cid)[0]["documento"] is None

    def test_arquivo_line_refuses_valor_texto(self, client, scoped):
        """The operator would otherwise type into a box whose contents vanish
        on every save, with a 200 saying it worked."""
        cid = _seed(scoped)
        criado = _criar(client, cid, tipo="arquivo")

        resp = client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"valor_texto": "não deveria colar"},
            headers=_auth(),
        )
        assert resp.status_code == 422, resp.text
        assert _listar(client, cid)[0]["valor_texto"] is None

    def test_arquivo_line_still_accepts_label_and_ordem(self, client, scoped):
        """The refusal is about the crossed FIELD, not about PATCH."""
        cid = _seed(scoped)
        criado = _criar(client, cid, tipo="arquivo")
        resp = client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"label": "Certidão", "ordem": 2},
            headers=_auth(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["label"] == "Certidão"

    def test_unknown_tipo_is_rejected_at_the_boundary(self, client, scoped):
        """`StrictHttpModel` + `Literal` — the closed set is the schema's job,
        so the service never sees a third kind."""
        cid = _seed(scoped)
        resp = client.post(
            f"/api/clientes/{cid}/checklist-extras",
            json={"label": "x", "tipo": "video"},
            headers=_auth(),
        )
        assert resp.status_code == 422, resp.text

    def test_tipo_cannot_be_changed_by_patch(self, client, scoped):
        """`extra="forbid"` — flipping `tipo` would strand either a
        `valor_texto` nothing reads or a document nothing points at."""
        cid = _seed(scoped)
        criado = _criar(client, cid, tipo="texto")
        resp = client.patch(
            f"/api/clientes/{cid}/checklist-extras/{criado['id']}",
            json={"tipo": "arquivo"},
            headers=_auth(),
        )
        assert resp.status_code == 422, resp.text


# ─── auth ────────────────────────────────────────────────────────────────


class TestAuthBoundary:
    def test_every_checklist_extras_route_requires_auth(self, anon_client):
        """🔴 Strict `== 401`, never `in (401, 404)`. A permissive tuple passes
        when the route does not exist at all and when validation runs before
        auth; only the exact code proves the guard fired.
        → `KB § PATTERNS/compliance/auth-boundary-false-green.md`
        """
        cid, eid = str(uuid4()), str(uuid4())
        base = f"/api/clientes/{cid}/checklist-extras"
        chamadas = [
            ("get", base, {}),
            ("post", base, {"json": {"label": "x", "tipo": "texto"}}),
            ("patch", f"{base}/{eid}", {"json": {"label": "x"}}),
            ("delete", f"{base}/{eid}", {}),
            (
                "post",
                f"{base}/{eid}/documento",
                {"files": {"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}},
            ),
            ("delete", f"{base}/{eid}/documento", {}),
        ]
        for metodo, url, kwargs in chamadas:
            resp = getattr(anon_client, metodo)(url, **kwargs)
            assert resp.status_code == 401, (
                f"{metodo.upper()} {url} -> {resp.status_code} "
                "(every checklist-extras route must require auth)"
            )
