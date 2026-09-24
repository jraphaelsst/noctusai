"""`empresas.dados_service` — the group-level D1 apply (Cartão CNPJ) and the
manual link (P0c contract §C6/§D2).

WHAT THESE PIN
--------------
- `aplicar_cartao`: an empty field fills, a differing field opens ONE
  `empresa_campo_conflitos` row per field (never a group-level conflict),
  and a fill ALSO re-stamps the group provenance (`dados_origem=
  'cartao_cnpj'`, `dados_confirmado_em=None` — machine-pending again);
- a Cartão CNPJ whose own `cnpj` disagrees with the empresa's never applies
  anything (`cnpj_divergente`);
- `criar_ou_vincular_manual`: upserts by `(org_id, cnpj)`, fill-empty
  `razao_social` only, `origem='manual'`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Optional
from uuid import uuid4

import pytest
from noctusai_lib.testing.mocks import MockSupabaseClient

from app.dependencies import coerce_org_uuid
from app.modules.empresas import dados_service
from app.services import campo_conflitos
from tests.support.document_fakes import (
    CNPJ_VALIDO,
    CNPJ_VALIDO_OUTRO,
    CNPJ_VALIDO_TERCEIRO,
)

ORG_ID = coerce_org_uuid("test-org-empresas")


@pytest.fixture
def client():
    mock = MockSupabaseClient()
    scoped = mock.schema("social_wiring")
    for table in (
        "empresas", "empresa_campo_conflitos",
        "cliente_empresa_participacoes", "empresa_documentos",
    ):
        scoped.set_table_data(table, [])
    return scoped


def _empresa(client, **extra) -> dict:
    row = {
        "id": str(uuid4()), "org_id": str(ORG_ID), "cnpj": CNPJ_VALIDO,
        "razao_social": None, "nome_fantasia": None, "natureza_juridica": None,
        "data_abertura": None, "situacao_cadastral": None,
        "data_situacao_cadastral": None, "motivo_situacao": None,
        "dados_origem": None, "dados_documento_id": None, "dados_em": None,
        "dados_confirmado_por": None, "dados_confirmado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    row.update(extra)
    client.table("empresas").insert(row).execute()
    return row


@dataclass(frozen=True)
class _CartaoLeitura:
    cnpj: Optional[str] = CNPJ_VALIDO
    cnpj_valido: bool = True
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    natureza_juridica: Optional[str] = None
    data_abertura: Optional[date] = None
    situacao_cadastral: Optional[str] = None
    data_situacao_cadastral: Optional[date] = None
    motivo_situacao: Optional[str] = None
    confiancas: Mapping[str, str] = field(default_factory=dict)


class TestAplicarCartao:
    def test_empty_fields_fill_and_stamp_group_provenance(self, client):
        empresa = _empresa(client)
        doc_id = str(uuid4())

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(razao_social="EMPRESA TESTE LTDA", situacao_cadastral="ativa"),
            documento_id=doc_id,
        )

        assert resultado["status"] == dados_service.APLICADO
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["razao_social"] == "EMPRESA TESTE LTDA"
        assert row["situacao_cadastral"] == "ativa"
        assert row["dados_origem"] == "cartao_cnpj"
        assert row["dados_documento_id"] == doc_id
        assert row["dados_confirmado_em"] is None  # machine-pending

    def test_a_differing_field_opens_a_conflict_never_overwrites(self, client):
        empresa = _empresa(client, razao_social="NOME ANTIGO LTDA", dados_origem="manual")
        doc_id = str(uuid4())

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(razao_social="NOME NOVO LTDA"),
            documento_id=doc_id,
        )

        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["razao_social"] == "NOME ANTIGO LTDA"  # untouched
        assert len(resultado["conflitos"]) == 1
        assert resultado["conflitos"][0]["campo"] == "razao_social"
        conflitos = client.table("empresa_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        assert conflitos[0]["valor_anterior"] == "NOME ANTIGO LTDA"
        assert conflitos[0]["valor_proposto"] == "NOME NOVO LTDA"

    def test_same_value_is_a_noop(self, client):
        empresa = _empresa(client, razao_social="EMPRESA TESTE LTDA")

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(razao_social="empresa teste ltda"),  # case-only
            documento_id=str(uuid4()),
        )

        assert resultado["status"] == dados_service.SEM_MUDANCA
        assert client.table("empresa_campo_conflitos").select("*").execute().data == []

    def test_cnpj_divergente_applies_nothing(self, client):
        empresa = _empresa(client)

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(cnpj=CNPJ_VALIDO_OUTRO, razao_social="OUTRA LTDA"),
            documento_id=str(uuid4()),
        )

        assert resultado["status"] == dados_service.CNPJ_DIVERGENTE
        assert resultado["aviso"] == "cnpj_divergente"
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["razao_social"] is None  # nothing applied
        assert client.table("empresa_campo_conflitos").select("*").execute().data == []

    def test_empresa_missing_is_a_404(self, client):
        from noctusai_lib.primitives.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            dados_service.aplicar_cartao(
                client, ORG_ID, str(uuid4()), _CartaoLeitura(), documento_id=str(uuid4())
            )


class TestManualLink:
    def test_creates_a_new_empresa_with_manual_origem(self, client):
        empresa = dados_service.criar_ou_vincular_manual(
            client, ORG_ID, str(uuid4()),
            cnpj=CNPJ_VALIDO, razao_social="EMPRESA MANUAL LTDA",
        )
        assert empresa["cnpj"] == CNPJ_VALIDO
        assert empresa["dados_origem"] == "manual"
        participacoes = (
            client.table("cliente_empresa_participacoes").select("*").execute().data
        )
        assert len(participacoes) == 1
        assert participacoes[0]["origem"] == "manual"

    def test_reuses_an_existing_empresa_fill_empty_razao_social_only(self, client):
        existing = _empresa(client, razao_social=None, dados_origem="serasa_crednet")

        empresa = dados_service.criar_ou_vincular_manual(
            client, ORG_ID, str(uuid4()),
            cnpj=existing["cnpj"], razao_social="NOME PREENCHIDO LTDA",
        )
        assert empresa["id"] == existing["id"]
        row = client.table("empresas").select("*").eq("id", existing["id"]).execute().data[0]
        assert row["razao_social"] == "NOME PREENCHIDO LTDA"
        assert row["dados_origem"] == "serasa_crednet"  # never restamped


class TestAtualizarManual:
    """`PATCH /api/empresas/{id}` (slice D) — group-level gate over the
    cadastral fields, `cnpj` never gated."""

    def test_field_edit_applies_immediately_when_ungated(self, client):
        empresa = _empresa(client, dados_origem="manual")

        resultado = dados_service.atualizar_manual(
            client, ORG_ID, empresa["id"], razao_social="NOVO NOME LTDA",
        )

        assert resultado["razao_social"] == "NOVO NOME LTDA"
        assert resultado["pendente_confirmacao"] == []
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["razao_social"] == "NOVO NOME LTDA"
        assert row["dados_origem"] == "manual"

    def test_non_admin_edit_of_document_sourced_group_defers_to_conflict(self, client):
        empresa = _empresa(
            client, razao_social="NOME ANTIGO LTDA", dados_origem="cartao_cnpj",
        )

        resultado = dados_service.atualizar_manual(
            client, ORG_ID, empresa["id"],
            razao_social="NOME PROPOSTO LTDA", is_admin=False,
        )

        assert resultado["pendente_confirmacao"] == ["razao_social"]
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["razao_social"] == "NOME ANTIGO LTDA"  # untouched

        conflitos = client.table("empresa_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        assert conflitos[0]["campo"] == "razao_social"
        assert conflitos[0]["status"] == "pendente"
        assert conflitos[0]["valor_proposto"] == "NOME PROPOSTO LTDA"
        assert conflitos[0]["origem_proposto"] == "manual"

    def test_admin_edit_of_document_sourced_group_applies_and_logs_audit_trail(self, client):
        empresa = _empresa(
            client, razao_social="NOME ANTIGO LTDA", dados_origem="cartao_cnpj",
        )
        admin_id = str(uuid4())

        resultado = dados_service.atualizar_manual(
            client, ORG_ID, empresa["id"],
            razao_social="NOME NOVO LTDA", is_admin=True, acting_user_id=admin_id,
        )

        assert resultado["razao_social"] == "NOME NOVO LTDA"
        assert resultado["pendente_confirmacao"] == []
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["razao_social"] == "NOME NOVO LTDA"
        assert row["dados_origem"] == "manual"  # a human just typed it

        conflitos = client.table("empresa_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        assert conflitos[0]["status"] == "aceito"
        assert conflitos[0]["valor_anterior"] == "NOME ANTIGO LTDA"
        assert conflitos[0]["valor_proposto"] == "NOME NOVO LTDA"
        assert conflitos[0]["decidido_por"] == admin_id

    def test_cnpj_edit_never_gated_even_when_group_is_document_sourced(self, client):
        empresa = _empresa(client, dados_origem="cartao_cnpj")

        resultado = dados_service.atualizar_manual(
            client, ORG_ID, empresa["id"], cnpj=CNPJ_VALIDO_OUTRO, is_admin=False,
        )

        assert resultado["cnpj"] == CNPJ_VALIDO_OUTRO
        assert resultado["pendente_confirmacao"] == []

    def test_cnpj_invalid_raises_validation_error(self, client):
        from noctusai_lib.primitives.exceptions import ValidationError_

        empresa = _empresa(client)
        with pytest.raises(ValidationError_):
            dados_service.atualizar_manual(
                client, ORG_ID, empresa["id"], cnpj="00000000000000",
            )

    def test_cnpj_duplicate_in_org_raises_validation_error(self, client):
        from noctusai_lib.primitives.exceptions import ValidationError_

        _empresa(client, cnpj=CNPJ_VALIDO_OUTRO)
        empresa = _empresa(client, cnpj=CNPJ_VALIDO)

        with pytest.raises(ValidationError_):
            dados_service.atualizar_manual(
                client, ORG_ID, empresa["id"], cnpj=CNPJ_VALIDO_OUTRO,
            )

    def test_no_recognized_field_is_a_noop(self, client):
        empresa = _empresa(client)
        resultado = dados_service.atualizar_manual(client, ORG_ID, empresa["id"])
        assert resultado["pendente_confirmacao"] == []
        assert resultado["cnpj"] == empresa["cnpj"]

    def test_empresa_missing_is_a_404(self, client):
        from noctusai_lib.primitives.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            dados_service.atualizar_manual(
                client, ORG_ID, str(uuid4()), razao_social="X",
            )


class TestRemoverParticipacao:
    """DELETE surface (slice D) — unlink always; empresa+documents deleted
    only when this was the last participação."""

    def _participacao(self, client, *, cliente_id, empresa_id, **extra) -> dict:
        row = {
            "id": str(uuid4()), "org_id": str(ORG_ID),
            "cliente_id": cliente_id, "empresa_id": empresa_id,
            "participacao_pct": None, "desde": None,
            "fonte_documento_id": None, "origem": "manual",
            "confirmado_por": None, "confirmado_em": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        row.update(extra)
        client.table("cliente_empresa_participacoes").insert(row).execute()
        return row

    def test_removes_link_keeps_empresa_when_other_participacoes_remain(self, client):
        empresa = _empresa(client)
        cliente_a, cliente_b = str(uuid4()), str(uuid4())
        self._participacao(client, cliente_id=cliente_a, empresa_id=empresa["id"])
        self._participacao(client, cliente_id=cliente_b, empresa_id=empresa["id"])

        resultado = dados_service.remover_participacao(
            client, ORG_ID, cliente_a, empresa["id"],
        )

        assert resultado["participacao_removida"] is True
        assert resultado["empresa_removida"] is False
        assert resultado["documentos"] == []
        restantes = (
            client.table("cliente_empresa_participacoes")
            .select("*").eq("empresa_id", empresa["id"]).execute().data
        )
        assert [r["cliente_id"] for r in restantes] == [cliente_b]
        assert client.table("empresas").select("*").eq(
            "id", empresa["id"]
        ).execute().data

    def test_removes_link_and_empresa_when_last_participacao_collects_documentos(
        self, client
    ):
        empresa = _empresa(client)
        cliente_id = str(uuid4())
        self._participacao(client, cliente_id=cliente_id, empresa_id=empresa["id"])
        doc = {
            "id": str(uuid4()), "org_id": str(ORG_ID), "empresa_id": empresa["id"],
            "storage_path": f"{ORG_ID}/empresas/{empresa['id']}/cartao.pdf",
        }
        client.table("empresa_documentos").insert(doc).execute()

        resultado = dados_service.remover_participacao(
            client, ORG_ID, cliente_id, empresa["id"],
        )

        assert resultado["participacao_removida"] is True
        assert resultado["empresa_removida"] is True
        assert [d["id"] for d in resultado["documentos"]] == [doc["id"]]
        assert client.table("empresas").select("*").eq(
            "id", empresa["id"]
        ).execute().data == []

    def test_missing_participacao_is_a_404(self, client):
        from noctusai_lib.primitives.exceptions import NotFoundError

        empresa = _empresa(client)
        with pytest.raises(NotFoundError):
            dados_service.remover_participacao(
                client, ORG_ID, str(uuid4()), empresa["id"],
            )
