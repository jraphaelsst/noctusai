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
from tests.support.fake_documents_p0c import CNPJ_VALIDO, CNPJ_VALIDO_OUTRO

ORG_ID = coerce_org_uuid("test-org-empresas")


@pytest.fixture
def client():
    mock = MockSupabaseClient()
    scoped = mock.schema("social_wiring")
    for table in ("empresas", "empresa_campo_conflitos"):
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
