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
        "certidao_consultas", "certidao_resultados",
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


class TestCrednetPrefixUpgrade:
    """🔴 The Serasa Crednet prints `razão social` truncated to 40 columns
    (live case, 2026-09-25): the empresa row Crednet CREATES carries that
    truncated string, `dados_origem='serasa_crednet'`. A later Cartão CNPJ
    read of the FULL name is not a disagreement — it is the SAME name,
    completed by the authoritative Receita document."""

    NOME_TRUNCADO_40 = "COMERCIO E SERVICOS DE ALIMENTOS EXEMPLO"[:40]

    def test_a_strict_prefix_upgrades_not_conflicts(self, client):
        empresa = _empresa(
            client, razao_social=self.NOME_TRUNCADO_40, dados_origem="serasa_crednet",
        )
        nome_completo = self.NOME_TRUNCADO_40 + " LTDA"
        doc_id = str(uuid4())

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(razao_social=nome_completo),
            documento_id=doc_id,
        )

        assert resultado["status"] == dados_service.APLICADO
        assert resultado["conflitos"] == []
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["razao_social"] == nome_completo
        assert row["dados_origem"] == "cartao_cnpj"  # provenance upgraded too
        assert row["dados_documento_id"] == doc_id
        assert client.table("empresa_campo_conflitos").select("*").execute().data == []

    def test_whitespace_and_case_normalised_prefix_still_upgrades(self, client):
        empresa = _empresa(
            client, razao_social=f"  {self.NOME_TRUNCADO_40.lower()}  ",
            dados_origem="serasa_crednet",
        )
        nome_completo = self.NOME_TRUNCADO_40 + " LTDA"

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(razao_social=nome_completo),
            documento_id=str(uuid4()),
        )

        assert resultado["status"] == dados_service.APLICADO
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["razao_social"] == nome_completo

    def test_a_non_prefix_disagreement_still_conflicts(self, client):
        """`dados_origem='serasa_crednet'`, but the incoming name is NOT a
        completion of the stored one — a genuinely different name, and
        must open a conflict exactly like the non-Crednet case."""
        empresa = _empresa(
            client, razao_social=self.NOME_TRUNCADO_40, dados_origem="serasa_crednet",
        )

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(razao_social="RAZAO SOCIAL COMPLETAMENTE DIFERENTE LTDA"),
            documento_id=str(uuid4()),
        )

        assert resultado["status"] == dados_service.SEM_MUDANCA
        assert len(resultado["conflitos"]) == 1
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["razao_social"] == self.NOME_TRUNCADO_40  # untouched

    def test_a_shorter_incoming_value_is_not_treated_as_an_upgrade(self):
        assert (
            dados_service._e_upgrade_de_crednet_truncado(
                "NOME COMPLETO JA CADASTRADO LTDA", "NOME COMPLETO"
            )
            is False
        )

    def test_upgrade_still_fires_when_group_origem_already_flipped_to_cartao_cnpj(
        self, client
    ):
        """🔴 Regression (live deal, 2026-09-25): the group shares ONE
        `dados_*` quintet, so an EARLIER Cartão CNPJ read that filled some
        OTHER field already re-stamped `dados_origem='cartao_cnpj'` — the
        stored `razao_social` is still Crednet's own 40-column truncation,
        never actually replaced. Gating the upgrade on
        `dados_origem == 'serasa_crednet'` then silently stopped firing
        forever; the prefix match alone must be enough."""
        empresa = _empresa(
            client, razao_social=self.NOME_TRUNCADO_40, dados_origem="cartao_cnpj",
            situacao_cadastral="ativa",
        )
        nome_completo = self.NOME_TRUNCADO_40 + " LTDA"

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(razao_social=nome_completo, situacao_cadastral="ativa"),
            documento_id=str(uuid4()),
        )

        assert resultado["status"] == dados_service.APLICADO
        assert resultado["conflitos"] == []
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["razao_social"] == nome_completo
        assert client.table("empresa_campo_conflitos").select("*").execute().data == []

    def test_an_already_open_pendente_conflict_is_closed_by_the_upgrade(self, client):
        """A PRIOR extraction attempt already opened a `pendente`
        `razao_social` conflict (e.g. before this upgrade rule existed, or
        from an unrelated earlier disagreement). A re-extraction that now
        qualifies as an upgrade must close it out — `rejeitado`, never
        silently deleted — rather than leaving a stale row an admin would
        otherwise have to adjudicate for no reason."""
        empresa = _empresa(
            client, razao_social=self.NOME_TRUNCADO_40, dados_origem="serasa_crednet",
        )
        pendente_id = str(uuid4())
        client.table("empresa_campo_conflitos").insert(
            {
                "id": pendente_id,
                "org_id": str(ORG_ID),
                "empresa_id": empresa["id"],
                "campo": "razao_social",
                "valor_anterior": self.NOME_TRUNCADO_40,
                "origem_anterior": "serasa_crednet",
                "valor_proposto": "ALGUMA LEITURA ANTERIOR LTDA",
                "origem_proposto": "cartao_cnpj",
                "confianca_proposta": None,
                "fonte_tabela": "empresa_documentos",
                "fonte_id": str(uuid4()),
                "status": "pendente",
                "notificado_em": None,
                "decidido_por": None,
                "decidido_em": None,
                "created_at": "2026-09-20T00:00:00+00:00",
            }
        ).execute()
        nome_completo = self.NOME_TRUNCADO_40 + " LTDA"

        dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(razao_social=nome_completo),
            documento_id=str(uuid4()),
        )

        conflitos = client.table("empresa_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        assert conflitos[0]["id"] == pendente_id
        assert conflitos[0]["status"] == "rejeitado"
        assert conflitos[0]["decidido_por"] is None
        assert conflitos[0]["decidido_em"] is not None


class TestSameDocumentReReadReplaces:
    """🔴 Regression (live deal, 2026-09-25): re-extracting a document
    whose earlier reading is STILL machine-pending must REFRESH the
    group instead of opening a conflict with itself — see
    `campo_conflitos.mesmo_documento_pendente`'s own docstring."""

    def test_same_document_still_pending_replaces_not_conflicts(self, client):
        doc_id = str(uuid4())
        empresa = _empresa(
            client,
            motivo_situacao="EXTINCAO POR ENCERRAMENTO | | |",  # garbled first read
            dados_origem="cartao_cnpj",
            dados_documento_id=doc_id,
            dados_confirmado_em=None,
        )

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(motivo_situacao="EXTINCAO POR ENCERRAMENTO LIQUIDACAO VOLUNTARIA"),
            documento_id=doc_id,
        )

        assert resultado["status"] == dados_service.APLICADO
        assert resultado["conflitos"] == []
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["motivo_situacao"] == "EXTINCAO POR ENCERRAMENTO LIQUIDACAO VOLUNTARIA"
        assert client.table("empresa_campo_conflitos").select("*").execute().data == []

    def test_a_confirmed_value_still_conflicts_even_off_the_same_document(self, client):
        doc_id = str(uuid4())
        empresa = _empresa(
            client,
            motivo_situacao="MOTIVO ANTIGO",
            dados_origem="cartao_cnpj",
            dados_documento_id=doc_id,
            dados_confirmado_em="2026-09-20T00:00:00+00:00",
        )

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(motivo_situacao="MOTIVO NOVO"),
            documento_id=doc_id,
        )

        assert len(resultado["conflitos"]) == 1
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["motivo_situacao"] == "MOTIVO ANTIGO"  # untouched

    def test_a_manual_value_still_conflicts_even_off_the_same_document(self, client):
        doc_id = str(uuid4())
        empresa = _empresa(
            client,
            motivo_situacao="MOTIVO DIGITADO",
            dados_origem="manual",
            dados_documento_id=doc_id,
            dados_confirmado_em=None,
        )

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(motivo_situacao="MOTIVO NOVO"),
            documento_id=doc_id,
        )

        assert len(resultado["conflitos"]) == 1
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["motivo_situacao"] == "MOTIVO DIGITADO"  # untouched

    def test_a_different_document_still_conflicts(self, client):
        empresa = _empresa(
            client,
            motivo_situacao="MOTIVO ANTIGO",
            dados_origem="cartao_cnpj",
            dados_documento_id=str(uuid4()),
            dados_confirmado_em=None,
        )

        resultado = dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(motivo_situacao="MOTIVO NOVO"),
            documento_id=str(uuid4()),  # a DIFFERENT document
        )

        assert len(resultado["conflitos"]) == 1
        row = client.table("empresas").select("*").eq("id", empresa["id"]).execute().data[0]
        assert row["motivo_situacao"] == "MOTIVO ANTIGO"  # untouched

    def test_a_stale_pending_conflict_on_the_same_field_is_closed(self, client):
        doc_id = str(uuid4())
        empresa = _empresa(
            client,
            natureza_juridica="206-2 - SOCIEDADE | | |",
            dados_origem="cartao_cnpj",
            dados_documento_id=doc_id,
            dados_confirmado_em=None,
        )
        pendente_id = str(uuid4())
        client.table("empresa_campo_conflitos").insert(
            {
                "id": pendente_id,
                "org_id": str(ORG_ID),
                "empresa_id": empresa["id"],
                "campo": "natureza_juridica",
                "valor_anterior": "206-2 - SOCIEDADE | | |",
                "origem_anterior": "cartao_cnpj",
                "valor_proposto": "ALGUMA LEITURA ANTERIOR",
                "origem_proposto": "cartao_cnpj",
                "confianca_proposta": None,
                "fonte_tabela": "empresa_documentos",
                "fonte_id": str(uuid4()),
                "status": "pendente",
                "notificado_em": None,
                "decidido_por": None,
                "decidido_em": None,
                "created_at": "2026-09-20T00:00:00+00:00",
            }
        ).execute()

        dados_service.aplicar_cartao(
            client, ORG_ID, empresa["id"],
            _CartaoLeitura(natureza_juridica="206-2 - SOCIEDADE EMPRESARIA LIMITADA"),
            documento_id=doc_id,
        )

        conflitos = client.table("empresa_campo_conflitos").select("*").execute().data
        assert len(conflitos) == 1
        assert conflitos[0]["id"] == pendente_id
        assert conflitos[0]["status"] == "rejeitado"
        assert conflitos[0]["decidido_por"] is None
        assert conflitos[0]["decidido_em"] is not None


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

    # ─── Owner decision (this dispatch): a full empresa delete ALSO soft-
    # deletes its certidões through the audited certidões mechanism ───────

    @staticmethod
    def _consulta(*, empresa_id=None, cliente_id=None, **extra) -> dict:
        row = {
            "id": str(uuid4()), "org_id": str(ORG_ID),
            "tipo_documento": "cnpj" if empresa_id else "cpf",
            "documento": "11222333000181" if empresa_id else "41295423898",
            "nome": "Empresa Teste" if empresa_id else "Fulana de Teste",
            "cliente_id": cliente_id, "atendimento_parte_id": None,
            "empresa_id": empresa_id,
            "created_by": "user-1", "status": "pendente", "origem": "manual",
            "total_certidoes": 13, "concluidas": 0,
            "situacao_cadastral": None, "data_situacao": None,
            "situacao_origem": None,
            "excluida_em": None, "excluida_por": None,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        row.update(extra)
        return row

    @staticmethod
    def _resultado(*, consulta_id, **extra) -> dict:
        row = {
            "id": str(uuid4()), "consulta_id": consulta_id, "org_id": str(ORG_ID),
            "tipo": "serasa", "nome_display": "Serasa", "ordem": 11,
            "status": "pendente", "excluida_em": None, "excluida_por": None,
        }
        row.update(extra)
        return row

    def test_full_delete_soft_deletes_the_empresa_scoped_certidoes(self, client):
        empresa = _empresa(client)
        cliente_id = str(uuid4())
        admin_id = str(uuid4())
        self._participacao(client, cliente_id=cliente_id, empresa_id=empresa["id"])
        consulta = self._consulta(empresa_id=empresa["id"])
        client.table("certidao_consultas").insert(consulta).execute()
        resultado_row = self._resultado(consulta_id=consulta["id"])
        client.table("certidao_resultados").insert(resultado_row).execute()

        resultado = dados_service.remover_participacao(
            client, ORG_ID, cliente_id, empresa["id"], acting_user_id=admin_id,
        )

        assert resultado["empresa_removida"] is True
        assert resultado["certidoes_removidas"] == 1

        consulta_row = (
            client.table("certidao_consultas").select("*")
            .eq("id", consulta["id"]).execute().data[0]
        )
        assert consulta_row["excluida_em"] is not None
        assert consulta_row["excluida_por"] == admin_id
        # Soft-delete NEVER touches storage/blobs — see soft_delete_consulta's
        # own docstring; nothing here asserts a file was removed, on purpose.

        resultado_row_after = (
            client.table("certidao_resultados").select("*")
            .eq("id", resultado_row["id"]).execute().data[0]
        )
        assert resultado_row_after["excluida_em"] is not None
        assert resultado_row_after["excluida_por"] == admin_id

    def test_shared_empresa_delete_removes_no_certidoes(self, client):
        """The empresa stays linked to another cliente -> the empresa row
        (and, per this same rule, its certidões) must NOT be touched."""
        empresa = _empresa(client)
        cliente_a, cliente_b = str(uuid4()), str(uuid4())
        self._participacao(client, cliente_id=cliente_a, empresa_id=empresa["id"])
        self._participacao(client, cliente_id=cliente_b, empresa_id=empresa["id"])
        consulta = self._consulta(empresa_id=empresa["id"])
        client.table("certidao_consultas").insert(consulta).execute()

        resultado = dados_service.remover_participacao(
            client, ORG_ID, cliente_a, empresa["id"],
        )

        assert resultado["empresa_removida"] is False
        assert resultado["certidoes_removidas"] == 0
        consulta_row = (
            client.table("certidao_consultas").select("*")
            .eq("id", consulta["id"]).execute().data[0]
        )
        assert consulta_row["excluida_em"] is None

    def test_full_delete_never_touches_a_person_linked_consulta(self, client):
        empresa = _empresa(client)
        cliente_id = str(uuid4())
        self._participacao(client, cliente_id=cliente_id, empresa_id=empresa["id"])
        # A CPF consulta for the SAME cliente — no `empresa_id` at all.
        pessoa_consulta = self._consulta(cliente_id=cliente_id)
        client.table("certidao_consultas").insert(pessoa_consulta).execute()

        resultado = dados_service.remover_participacao(
            client, ORG_ID, cliente_id, empresa["id"],
        )

        assert resultado["empresa_removida"] is True
        assert resultado["certidoes_removidas"] == 0
        consulta_row = (
            client.table("certidao_consultas").select("*")
            .eq("id", pessoa_consulta["id"]).execute().data[0]
        )
        assert consulta_row["excluida_em"] is None

    def test_full_delete_never_touches_another_empresas_consulta(self, client):
        empresa = _empresa(client)
        outra_empresa = _empresa(client, cnpj=CNPJ_VALIDO_OUTRO)
        cliente_id = str(uuid4())
        self._participacao(client, cliente_id=cliente_id, empresa_id=empresa["id"])
        outra_consulta = self._consulta(empresa_id=outra_empresa["id"])
        client.table("certidao_consultas").insert(outra_consulta).execute()

        resultado = dados_service.remover_participacao(
            client, ORG_ID, cliente_id, empresa["id"],
        )

        assert resultado["empresa_removida"] is True
        assert resultado["certidoes_removidas"] == 0
        consulta_row = (
            client.table("certidao_consultas").select("*")
            .eq("id", outra_consulta["id"]).execute().data[0]
        )
        assert consulta_row["excluida_em"] is None

    def test_full_delete_skips_an_already_excluded_consulta(self, client):
        empresa = _empresa(client)
        cliente_id = str(uuid4())
        self._participacao(client, cliente_id=cliente_id, empresa_id=empresa["id"])
        ja_excluida = self._consulta(
            empresa_id=empresa["id"],
            excluida_em="2026-01-01T00:00:00+00:00", excluida_por="someone-else",
        )
        client.table("certidao_consultas").insert(ja_excluida).execute()

        resultado = dados_service.remover_participacao(
            client, ORG_ID, cliente_id, empresa["id"],
        )

        assert resultado["certidoes_removidas"] == 0
        consulta_row = (
            client.table("certidao_consultas").select("*")
            .eq("id", ja_excluida["id"]).execute().data[0]
        )
        # untouched — the earlier exclusion's attribution survives.
        assert consulta_row["excluida_por"] == "someone-else"
