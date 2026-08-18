"""Documents, LGPD-complete (contract §2 `057`, ruling S2 / D5).

Storage is ALWAYS the `fake_storage` fixture — never
`MockSupabaseClient.storage` (a bare `MagicMock()` that would silently
"succeed" instead of failing loudly). Per
`KB § PATTERNS/backend/di-test-seam.md` Class-B."""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from tests.modules.card_hub.conftest import (
    ORG_ID,
    cliente_row,
    documento_row,
    documento_tipo_row,
)


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


class TestUpload:
    def test_upload_roundtrip(self, client, scoped, fake_storage):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("cliente_documento_tipos", [documento_tipo_row("contrato")])

        resp = client.post(
            f"/api/clientes/{cid}/documentos",
            files={"file": ("contrato.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
            data={"tipo_documento": "contrato"},
            headers=_auth(),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["nome_original"] == "contrato.pdf"
        assert body["tipo_documento"] == "contrato"
        assert body["categoria_lgpd"] == "contratual"
        assert body["retencao_ate"] is not None
        assert body["thumbnail_url"] is None

        stored = scoped.table("cliente_documentos").select("*").execute().data
        assert len(stored) == 1
        # Object path is org_id-first (contract §2, migration 057's
        # object-RLS policies key on the first path segment).
        assert stored[0]["storage_path"].startswith(f"{ORG_ID}/clientes/{cid}/")

    def test_upload_rejects_disallowed_mime_type(self, client, scoped, fake_storage):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("cliente_documento_tipos", [documento_tipo_row("contrato")])

        resp = client.post(
            f"/api/clientes/{cid}/documentos",
            files={"file": ("script.exe", b"MZ", "application/x-msdownload")},
            data={"tipo_documento": "contrato"},
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert "Tipo de arquivo não permitido" in resp.json()["error"]["message"]

    def test_upload_rejects_oversized_file_naming_the_limit(self, client, scoped, fake_storage):
        """`oversized` sits ABOVE `MAX_UPLOAD_BYTES` but BELOW the
        platform's `MaxBodySizeMiddleware` cap (1 MB default) — so this
        endpoint's own typed-error check is what fires, not the
        app-wide 413 (see `MAX_UPLOAD_BYTES`'s docstring for why the two
        limits are close enough together in this product for this to
        matter for test design)."""
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("cliente_documento_tipos", [documento_tipo_row("contrato")])

        from app.modules.card_hub.documentos_service import MAX_UPLOAD_BYTES

        oversized = b"0" * (MAX_UPLOAD_BYTES + 1)
        resp = client.post(
            f"/api/clientes/{cid}/documentos",
            files={"file": ("grande.pdf", oversized, "application/pdf")},
            data={"tipo_documento": "contrato"},
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert "limite" in resp.json()["error"]["message"].lower()

    def test_upload_rejects_withheld_identity_document_type(self, client, scoped, fake_storage):
        """The conservative default allow-list (contract §2) excludes
        RG/CPF-class types until the LGPD intake is filed."""
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "cliente_documento_tipos", [documento_tipo_row("rg", categoria="identidade", ativo=False, identidade=True)]
        )
        resp = client.post(
            f"/api/clientes/{cid}/documentos",
            files={"file": ("rg.pdf", b"%PDF-1.4", "application/pdf")},
            data={"tipo_documento": "rg"},
            headers=_auth(),
        )
        assert resp.status_code == 400, resp.text
        assert "não está habilitado" in resp.json()["error"]["message"]

    def test_upload_rejects_unknown_tipo_documento(self, client, scoped, fake_storage):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.post(
            f"/api/clientes/{cid}/documentos",
            files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
            data={"tipo_documento": "nao_existe"},
            headers=_auth(),
        )
        assert resp.status_code == 400


class TestListAndUrlAndDelete:
    def test_list_excludes_deleted(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        active = documento_row(str(uuid4()), cid)
        deleted = documento_row(str(uuid4()), cid, deleted_at="2026-01-01T00:00:00+00:00")
        scoped.set_table_data("cliente_documentos", [active, deleted])

        resp = client.get(f"/api/clientes/{cid}/documentos", headers=_auth())
        assert resp.status_code == 200, resp.text
        assert {d["id"] for d in resp.json()["items"]} == {active["id"]}

    def test_get_url_mints_and_logs_view(self, client, scoped, fake_storage):
        cid = str(uuid4())
        doc = documento_row(str(uuid4()), cid)
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("cliente_documentos", [doc])

        resp = client.get(f"/api/clientes/{cid}/documentos/{doc['id']}/url", headers=_auth())
        assert resp.status_code == 200, resp.text
        assert resp.json()["url"]
        assert resp.json()["expires_at"]

        acessos = scoped.table("cliente_documento_acessos").select("*").execute().data
        assert len(acessos) == 1
        assert acessos[0]["acao"] == "view"
        assert acessos[0]["documento_id"] == doc["id"]

    def test_get_url_download_intent_logs_download(self, client, scoped, fake_storage):
        cid = str(uuid4())
        doc = documento_row(str(uuid4()), cid)
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("cliente_documentos", [doc])

        resp = client.get(
            f"/api/clientes/{cid}/documentos/{doc['id']}/url?intent=download", headers=_auth()
        )
        assert resp.status_code == 200, resp.text
        acessos = scoped.table("cliente_documento_acessos").select("*").execute().data
        assert acessos[0]["acao"] == "download"

    def test_delete_requires_motivo_as_query_param(self, client, scoped, fake_storage):
        """Contract correction: DELETE takes NO JSON body — the seed
        ApiClient.delete() has no body parameter. `motivo` is a required
        query param."""
        cid = str(uuid4())
        doc = documento_row(str(uuid4()), cid)
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("cliente_documentos", [doc])

        # No motivo at all -> 422 (missing required query param).
        resp = client.delete(f"/api/clientes/{cid}/documentos/{doc['id']}", headers=_auth())
        assert resp.status_code == 422

        resp = client.delete(
            f"/api/clientes/{cid}/documentos/{doc['id']}?motivo=solicitação%20do%20cliente",
            headers=_auth(),
        )
        assert resp.status_code == 204, resp.text

        stored = scoped.table("cliente_documentos").select("*").eq("id", doc["id"]).execute().data[0]
        assert stored["deleted_at"] is not None
        assert stored["delete_motivo"] == "solicitação do cliente"

        acessos = scoped.table("cliente_documento_acessos").select("*").execute().data
        assert any(a["acao"] == "delete" for a in acessos)

        # Soft-deleted -> no longer listed, no longer accessible via url.
        resp = client.get(f"/api/clientes/{cid}/documentos", headers=_auth())
        assert resp.json()["items"] == []
        resp = client.get(f"/api/clientes/{cid}/documentos/{doc['id']}/url", headers=_auth())
        assert resp.status_code == 404

    def test_acessos_log_survives_the_documents_own_delete(self, client, scoped, fake_storage):
        """Soft-delete is not erasure — the access log (including the
        delete entry itself) must remain readable."""
        cid = str(uuid4())
        doc = documento_row(str(uuid4()), cid)
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data("cliente_documentos", [doc])

        client.delete(f"/api/clientes/{cid}/documentos/{doc['id']}?motivo=x", headers=_auth())

        resp = client.get(f"/api/clientes/{cid}/documentos/{doc['id']}/acessos", headers=_auth())
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] >= 1

    def test_unknown_documento_404s(self, client, scoped, fake_storage):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.get(f"/api/clientes/{cid}/documentos/{uuid4()}/url", headers=_auth())
        assert resp.status_code == 404


class TestAccessLogIsAppendOnly:
    def test_no_mutation_route_exists_for_acessos(self):
        """The API surface itself never offers a PATCH/PUT/DELETE on the
        access log — mutability is refused by construction (no route),
        not merely by an RLS policy this mock cannot exercise."""
        from app.modules.card_hub import register

        paths_methods = {
            route.path: {m.lower() for m in getattr(route, "methods", set())}
            for router in register().routers
            for route in router.routes
            if hasattr(route, "path")
        }
        acesso_path = "/api/clientes/{cliente_id}/documentos/{documento_id}/acessos"
        assert acesso_path in paths_methods
        assert paths_methods[acesso_path] == {"get"}


class TestTiposCatalogue:
    def test_lists_only_active_types(self, client, scoped):
        scoped.set_table_data(
            "cliente_documento_tipos",
            [
                documento_tipo_row("contrato", ativo=True),
                documento_tipo_row("rg", categoria="identidade", ativo=False, identidade=True),
            ],
        )
        resp = client.get("/api/clientes/documentos/tipos", headers=_auth())
        assert resp.status_code == 200, resp.text
        tipos = {t["tipo_documento"] for t in resp.json()["items"]}
        assert tipos == {"contrato"}


class TestRetentionSweep:
    def test_sweep_soft_deletes_past_retention_and_logs(self, scoped):
        from app.modules.card_hub.documentos_service import run_retention_sweep
        from tests.modules.card_hub.conftest import ORG_ID

        cid = str(uuid4())
        past_date = (date.today() - timedelta(days=1)).isoformat()
        expired = documento_row(str(uuid4()), cid, retencao_ate=past_date)
        fresh = documento_row(
            str(uuid4()), cid, retencao_ate=(date.today() + timedelta(days=30)).isoformat()
        )
        scoped.set_table_data("cliente_documentos", [expired, fresh])

        swept = run_retention_sweep(scoped, ORG_ID)
        assert swept == 1

        rows = {r["id"]: r for r in scoped.table("cliente_documentos").select("*").execute().data}
        assert rows[expired["id"]]["deleted_at"] is not None
        assert rows[fresh["id"]]["deleted_at"] is None

        acessos = scoped.table("cliente_documento_acessos").select("*").eq("documento_id", expired["id"]).execute().data
        assert any(a["acao"] == "delete" for a in acessos)
