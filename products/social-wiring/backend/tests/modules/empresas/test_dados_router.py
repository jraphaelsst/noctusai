"""`PATCH /api/empresas/{empresa_id}` and `GET /api/empresas/{empresa_id}
/checklist` (slice D) — through HTTP.

WHAT THESE PIN
--------------
- PATCH: a plain field applies (200); a document-sourced cadastral field
  from a NON-admin defers (`pendente_confirmacao` non-empty, row
  untouched); the SAME field from an admin (trusted `noctus_users.org_role`
  row) applies immediately; an invalid CNPJ is 400.
- checklist: `cartao_cnpj` starts unsatisfied, flips once a non-deleted
  document of that type exists.

Auth is NOT re-tested here — `test_empresas_auth_boundary.py` enumerates
every mounted `/api/empresas/*` route.
"""
from __future__ import annotations

from uuid import uuid4

from noctusai_lib.testing import TEST_USER_ID

from tests.modules.empresas.conftest import ORG_ID, auth, documento_row, empresa_row


def _make_admin(client) -> None:
    client.mock_supabase.set_table_data(
        "noctus_users",
        [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "owner"}],
    )


class TestPatchEmpresa:
    def test_plain_field_applies(self, client, scoped):
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [empresa_row(empresa_id, dados_origem="manual")])

        r = client.patch(
            f"/api/empresas/{empresa_id}",
            json={"nome_fantasia": "Fantasia Nova"},
            headers=auth(),
        )

        assert r.status_code == 200, r.text
        assert r.json()["nome_fantasia"] == "Fantasia Nova"
        assert r.json()["pendente_confirmacao"] == []

    def test_non_admin_editing_a_document_sourced_field_defers(self, client, scoped):
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [
            empresa_row(
                empresa_id, razao_social="NOME ANTIGO LTDA", dados_origem="cartao_cnpj",
            )
        ])
        scoped.set_table_data("empresa_campo_conflitos", [])

        r = client.patch(
            f"/api/empresas/{empresa_id}",
            json={"razao_social": "NOME PROPOSTO LTDA"},
            headers=auth(),
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pendente_confirmacao"] == ["razao_social"]
        assert body["razao_social"] == "NOME ANTIGO LTDA"  # untouched
        conflitos = scoped.table("empresa_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        assert conflitos[0]["status"] == "pendente"

    def test_admin_editing_a_document_sourced_field_applies_immediately(
        self, client, scoped
    ):
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [
            empresa_row(
                empresa_id, razao_social="NOME ANTIGO LTDA", dados_origem="cartao_cnpj",
            )
        ])
        scoped.set_table_data("empresa_campo_conflitos", [])
        _make_admin(client)

        r = client.patch(
            f"/api/empresas/{empresa_id}",
            json={"razao_social": "NOME NOVO LTDA"},
            headers=auth(),
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pendente_confirmacao"] == []
        assert body["razao_social"] == "NOME NOVO LTDA"
        conflitos = scoped.table("empresa_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        assert conflitos[0]["status"] == "aceito"

    def test_invalid_cnpj_is_400(self, client, scoped):
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [empresa_row(empresa_id)])

        r = client.patch(
            f"/api/empresas/{empresa_id}",
            json={"cnpj": "00000000000000"},
            headers=auth(),
        )

        assert r.status_code == 400, r.text

    def test_unknown_empresa_is_404(self, client, scoped):
        scoped.set_table_data("empresas", [])

        r = client.patch(
            f"/api/empresas/{uuid4()}",
            json={"nome_fantasia": "X"},
            headers=auth(),
        )

        assert r.status_code == 404


class TestChecklist:
    def test_cartao_cnpj_starts_unsatisfied(self, client, scoped):
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [empresa_row(empresa_id)])
        scoped.set_table_data("empresa_documentos", [])

        r = client.get(f"/api/empresas/{empresa_id}/checklist", headers=auth())

        assert r.status_code == 200, r.text
        [item] = r.json()["items"]
        assert item["item_key"] == "cartao_cnpj"
        assert item["satisfeito"] is False

    def test_cartao_cnpj_satisfied_once_a_document_exists(self, client, scoped):
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [empresa_row(empresa_id)])
        doc = documento_row(empresa_id=empresa_id)
        scoped.set_table_data("empresa_documentos", [doc])

        r = client.get(f"/api/empresas/{empresa_id}/checklist", headers=auth())

        assert r.status_code == 200, r.text
        [item] = r.json()["items"]
        assert item["satisfeito"] is True
        assert item["documento_id"] == doc["id"]

    def test_a_soft_deleted_document_does_not_satisfy_it(self, client, scoped):
        empresa_id = str(uuid4())
        scoped.set_table_data("empresas", [empresa_row(empresa_id)])
        doc = documento_row(
            empresa_id=empresa_id, deleted_at="2026-01-02T00:00:00+00:00",
        )
        scoped.set_table_data("empresa_documentos", [doc])

        r = client.get(f"/api/empresas/{empresa_id}/checklist", headers=auth())

        assert r.status_code == 200, r.text
        [item] = r.json()["items"]
        assert item["satisfeito"] is False

    def test_unknown_empresa_is_404(self, client, scoped):
        scoped.set_table_data("empresas", [])

        r = client.get(f"/api/empresas/{uuid4()}/checklist", headers=auth())

        assert r.status_code == 404
