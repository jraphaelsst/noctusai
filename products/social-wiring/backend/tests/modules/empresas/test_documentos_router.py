"""`/api/empresas/{empresa_id}/documentos/*` — the Cartão CNPJ upload/
extraction/document lifecycle (P0c contract §D3/§D4, item 5 of the P0c
integration dispatch).

WHAT THESE PIN
--------------
- upload: 201, `extracao_status` stamped `pendente` at upload time (not by
  the job); an unknown `tipo_documento`/disallowed mime is 400
  (`ValidationError_` — never 422, which FastAPI reserves for a malformed
  request BODY); an unknown empresa is 404;
- `.../extrair`: refused (400) while `pendente`/`processando`, refused once
  `extracao_tentativas >= MAX_TENTATIVAS`, else re-queues;
- `.../extracao/confirmar`: stamps `empresas.dados_confirmado_por/_em`
  (D2); a foreign/unknown documento is 404;
- `.../extracao/descartar`: stamps `extracao_descartada_*`, the reading
  itself (`extracao_dados`) survives;
- `.../url`: a short-TTL signed URL, no `intent` query param;
- `DELETE ...?motivo=`: 204, soft-deletes with the reason; a missing
  `motivo` is 422 (`Query(..., min_length=1)`).

Auth is NOT re-tested here — `test_empresas_auth_boundary.py` enumerates
every mounted `/api/empresas/*` route and asserts a strict `== 401`.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.empresas import documentos_service, extracao_service
from noctusai_lib.primitives.exceptions import ValidationError_
from tests.modules.empresas.conftest import auth, documento_row, empresa_row

PDF = ("cartao.pdf", b"%PDF-1.7 fake", "application/pdf")


def _upload(client, empresa_id, *, arquivo=PDF, tipo="cartao_cnpj"):
    return client.post(
        f"/api/empresas/{empresa_id}/documentos",
        files={"file": arquivo},
        data={"tipo_documento": tipo},
        headers=auth(),
    )


def _seed_empresa(scoped, empresa_id=None, **over) -> str:
    empresa_id = empresa_id or str(uuid4())
    scoped.set_table_data("empresas", [empresa_row(empresa_id, **over)])
    return empresa_id


class TestUpload:
    def test_uploads_and_is_queued_for_reading(
        self, client, scoped, fake_storage, fake_cartao_extractor
    ):
        empresa_id = _seed_empresa(scoped)
        r = _upload(client, empresa_id)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["tipo_documento"] == "cartao_cnpj"
        # 🔴 Stamped at UPLOAD time, not by the job — same reasoning every
        # sibling extraction lifecycle in this product gives.
        assert body["extracao_status"] == "pendente"
        assert body["empresa_id"] == empresa_id

    def test_an_unknown_type_is_400(self, client, scoped, fake_storage, fake_cartao_extractor):
        empresa_id = _seed_empresa(scoped)
        r = _upload(client, empresa_id, tipo="rg")
        assert r.status_code == 400, r.text

    def test_a_disallowed_mime_type_is_400(
        self, client, scoped, fake_storage, fake_cartao_extractor
    ):
        empresa_id = _seed_empresa(scoped)
        r = _upload(client, empresa_id, arquivo=("m.exe", b"MZ", "application/x-msdownload"))
        assert r.status_code == 400, r.text

    def test_an_unknown_empresa_is_404(self, client, scoped, fake_storage, fake_cartao_extractor):
        r = _upload(client, str(uuid4()))
        assert r.status_code == 404

    def test_an_oversized_file_names_the_limit_in_megabytes(self):
        """Driven through `validar_upload`'s `max_bytes` seam, NOT by
        monkeypatching `MAX_UPLOAD_BYTES` — same posture `imovel_hub`'s
        identical test takes (`KB § PATTERNS/backend/di-test-seam.md`)."""
        with pytest.raises(ValidationError_) as exc:
            documentos_service.validar_upload(
                tipo_documento="cartao_cnpj",
                content_type="application/pdf",
                tamanho_bytes=50,
                max_bytes=10,
            )
        msg = str(exc.value)
        assert "0MB" not in msg
        assert "KB" in msg or "MB" in msg


class TestGetEmpresaEDocumentos:
    def test_get_empresa_returns_the_row(self, client, scoped):
        empresa_id = _seed_empresa(scoped, razao_social="Fulana Empreendimentos")
        r = client.get(f"/api/empresas/{empresa_id}", headers=auth())
        assert r.status_code == 200
        assert r.json()["razao_social"] == "Fulana Empreendimentos"

    def test_get_unknown_empresa_is_404(self, client, scoped):
        r = client.get(f"/api/empresas/{uuid4()}", headers=auth())
        assert r.status_code == 404

    def test_list_documentos_excludes_soft_deleted(self, client, scoped):
        empresa_id = _seed_empresa(scoped)
        vivo = documento_row(str(uuid4()), empresa_id)
        excluido = documento_row(str(uuid4()), empresa_id, deleted_at="2026-01-02T00:00:00+00:00")
        scoped.set_table_data("empresa_documentos", [vivo, excluido])
        r = client.get(f"/api/empresas/{empresa_id}/documentos", headers=auth())
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == vivo["id"]


class TestReextrair:
    def test_refused_while_pendente(self, client, scoped, fake_storage, fake_cartao_extractor):
        empresa_id = _seed_empresa(scoped)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "empresa_documentos", [documento_row(doc_id, empresa_id, extracao_status="pendente")]
        )
        r = client.post(
            f"/api/empresas/{empresa_id}/documentos/{doc_id}/extrair", headers=auth()
        )
        assert r.status_code == 400

    def test_refused_while_processando(self, client, scoped, fake_storage, fake_cartao_extractor):
        empresa_id = _seed_empresa(scoped)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "empresa_documentos", [documento_row(doc_id, empresa_id, extracao_status="processando")]
        )
        r = client.post(
            f"/api/empresas/{empresa_id}/documentos/{doc_id}/extrair", headers=auth()
        )
        assert r.status_code == 400

    def test_refused_after_max_tentativas(
        self, client, scoped, fake_storage, fake_cartao_extractor
    ):
        empresa_id = _seed_empresa(scoped)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "empresa_documentos",
            [documento_row(
                doc_id, empresa_id, extracao_status="erro",
                extracao_tentativas=extracao_service.MAX_TENTATIVAS,
            )],
        )
        r = client.post(
            f"/api/empresas/{empresa_id}/documentos/{doc_id}/extrair", headers=auth()
        )
        assert r.status_code == 400

    def test_reruns_and_returns_pending(self, client, scoped, fake_storage, fake_cartao_extractor):
        empresa_id = _seed_empresa(scoped)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "empresa_documentos",
            [documento_row(doc_id, empresa_id, extracao_status="erro", extracao_tentativas=1)],
        )
        r = client.post(
            f"/api/empresas/{empresa_id}/documentos/{doc_id}/extrair", headers=auth()
        )
        assert r.status_code == 200, r.text
        assert r.json()["extracao_status"] == "pendente"


class TestConfirmarDescartar:
    def test_confirmar_stamps_provenance(self, client, scoped, fake_storage):
        doc_id = str(uuid4())
        empresa_id = _seed_empresa(
            scoped,
            situacao_cadastral="ativa", dados_origem="cartao_cnpj",
            dados_documento_id=doc_id, dados_em="2026-01-01T00:00:00+00:00",
            dados_confirmado_por=None, dados_confirmado_em=None,
        )
        scoped.set_table_data("empresa_documentos", [documento_row(doc_id, empresa_id, extracao_status="ok")])
        r = client.post(
            f"/api/empresas/{empresa_id}/documentos/{doc_id}/extracao/confirmar", headers=auth()
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dados_confirmado_em"] is not None
        assert body["dados_confirmado_por"] is not None

    def test_confirmar_unknown_documento_is_404(self, client, scoped, fake_storage):
        empresa_id = _seed_empresa(scoped)
        scoped.set_table_data("empresa_documentos", [])
        r = client.post(
            f"/api/empresas/{empresa_id}/documentos/{uuid4()}/extracao/confirmar", headers=auth()
        )
        assert r.status_code == 404

    def test_descartar_marks_discarded_but_keeps_the_reading(self, client, scoped, fake_storage):
        empresa_id = _seed_empresa(scoped)
        doc_id = str(uuid4())
        scoped.set_table_data(
            "empresa_documentos",
            [documento_row(
                doc_id, empresa_id, extracao_status="ok",
                extracao_dados={"cnpj": "11222333000181"},
            )],
        )
        r = client.post(
            f"/api/empresas/{empresa_id}/documentos/{doc_id}/extracao/descartar", headers=auth()
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["extracao_descartada_em"] is not None
        assert body["extracao_dados"] == {"cnpj": "11222333000181"}


class TestUrl:
    def test_returns_a_signed_url(self, client, scoped, fake_storage):
        empresa_id = _seed_empresa(scoped)
        doc_id = str(uuid4())
        scoped.set_table_data("empresa_documentos", [documento_row(doc_id, empresa_id)])
        scoped.set_table_data("empresa_documento_acessos", [])
        r = client.get(
            f"/api/empresas/{empresa_id}/documentos/{doc_id}/url", headers=auth()
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["url"].startswith("fake://storage/")
        assert "expires_at" in body

    def test_unknown_documento_is_404(self, client, scoped, fake_storage):
        empresa_id = _seed_empresa(scoped)
        scoped.set_table_data("empresa_documentos", [])
        r = client.get(
            f"/api/empresas/{empresa_id}/documentos/{uuid4()}/url", headers=auth()
        )
        assert r.status_code == 404


class TestDelete:
    def test_deletes_with_a_motivo(self, client, scoped, fake_storage):
        empresa_id = _seed_empresa(scoped)
        doc_id = str(uuid4())
        scoped.set_table_data("empresa_documentos", [documento_row(doc_id, empresa_id)])
        scoped.set_table_data("empresa_documento_acessos", [])
        r = client.delete(
            f"/api/empresas/{empresa_id}/documentos/{doc_id}?motivo=duplicado", headers=auth()
        )
        assert r.status_code == 204, r.text
        row = [
            row for row in scoped.table("empresa_documentos").select("*").execute().data
            if row["id"] == doc_id
        ][0]
        assert row["deleted_at"] is not None
        assert row["delete_motivo"] == "duplicado"

    def test_missing_motivo_is_422(self, client, scoped, fake_storage):
        empresa_id = _seed_empresa(scoped)
        doc_id = str(uuid4())
        scoped.set_table_data("empresa_documentos", [documento_row(doc_id, empresa_id)])
        r = client.delete(f"/api/empresas/{empresa_id}/documentos/{doc_id}", headers=auth())
        assert r.status_code == 422
