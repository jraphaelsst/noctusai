"""The shared `<entidade>_campo_conflitos` writer (P0c contract §H6).

WHAT THESE PIN
--------------
- open + dedupe-pending: a second `registrar_conflito` for the same (owner,
  campo) while one is still `pendente` returns `None` and inserts nothing;
- the row shape is identical across the three registered surfaces, except
  `documento_id_proposto`, which ONLY `IMOVEL` carries (contract §A.4's
  polymorphic pointer, mirroring migration 154's own extra column);
- notify is best-effort per conflict (one failure does not stop the next),
  stamps `notificado_em` only on success, and a missing notifier is logged,
  never silently dropped.

The two EXISTING consumers (`identidade_extracao_service`,
`imovel_hub.campos_extraidos_service`) keep their own colocated tests
unchanged — this file is this module's OWN unit coverage, plus the one new
consumer (`app.modules.empresas`, tested in its own suite).
"""
from __future__ import annotations

import logging

import pytest
from noctusai_lib.testing.mocks import MockSupabaseClient

from app.dependencies import coerce_org_uuid
from app.services import campo_conflitos

ORG = coerce_org_uuid("test-org-conflitos")


@pytest.fixture
def client():
    mock = MockSupabaseClient()
    scoped = mock.schema("social_wiring")
    for table in (
        campo_conflitos.CLIENTE.table,
        campo_conflitos.IMOVEL.table,
        campo_conflitos.EMPRESA.table,
    ):
        scoped.set_table_data(table, [])
    return scoped


class TestOpenAndDedupe:
    def test_opens_a_row_with_the_full_shape(self, client):
        row = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="11.111.111-1",
            origem_anterior="manual",
            valor_proposto="22.222.222-2",
            origem_proposto="rg",
            confianca_proposta="alta",
            fonte_tabela="cliente_documentos",
            fonte_id="doc-1",
        )
        assert row is not None
        assert row["status"] == "pendente"
        assert row["cliente_id"] == "cliente-1"
        assert row["notificado_em"] is None
        assert row["decidido_por"] is None
        assert row["fonte_id"] == "doc-1"
        stored = (
            client.table(campo_conflitos.CLIENTE.table).select("*").execute()
        ).data
        assert len(stored) == 1
        assert stored[0]["id"] == row["id"]

    def test_a_second_call_on_the_same_owner_and_campo_is_a_noop(self, client):
        first = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="b", origem_proposto="rg",
        )
        second = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="c", origem_proposto="rg",
        )
        assert first is not None
        assert second is None
        stored = (
            client.table(campo_conflitos.CLIENTE.table).select("*").execute()
        ).data
        assert len(stored) == 1

    def test_a_different_campo_on_the_same_owner_opens_its_own_row(self, client):
        campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="b", origem_proposto="rg",
        )
        second = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "cpf",
            valor_anterior="x", origem_anterior="manual",
            valor_proposto="y", origem_proposto="cpf",
        )
        assert second is not None
        stored = (
            client.table(campo_conflitos.CLIENTE.table).select("*").execute()
        ).data
        assert len(stored) == 2

    def test_conflito_pendente_existente_reads_the_open_row(self, client):
        assert campo_conflitos.conflito_pendente_existente(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "razao_social"
        ) is None
        campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "razao_social",
            valor_anterior="Acme", origem_anterior="cartao_cnpj",
            valor_proposto="Acme Ltda", origem_proposto="cartao_cnpj",
        )
        found = campo_conflitos.conflito_pendente_existente(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "razao_social"
        )
        assert found is not None
        assert found["empresa_id"] == "empresa-1"


class TestDocumentoIdProposto:
    def test_imovel_carries_documento_id_proposto(self, client):
        row = campo_conflitos.registrar_conflito(
            client, campo_conflitos.IMOVEL, ORG, "SP-001", "numero_matricula",
            valor_anterior="12345", origem_anterior="matricula",
            valor_proposto="12846", origem_proposto="matricula",
            documento_id_proposto="doc-99",
        )
        assert row["documento_id_proposto"] == "doc-99"

    def test_cliente_and_empresa_never_carry_the_column(self, client):
        cliente_row = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-9", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="b", origem_proposto="rg",
            documento_id_proposto="ignored",
        )
        empresa_row = campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, ORG, "empresa-9", "uf",
            valor_anterior="SP", origem_anterior="cartao_cnpj",
            valor_proposto="RJ", origem_proposto="cartao_cnpj",
            documento_id_proposto="ignored",
        )
        assert "documento_id_proposto" not in cliente_row
        assert "documento_id_proposto" not in empresa_row


class TestMesmoDocumentoPendente:
    """The D1 same-document-re-read refinement's shared predicate (see the
    module docstring)."""

    def test_same_document_still_pending_is_a_replace(self):
        assert campo_conflitos.mesmo_documento_pendente(
            origem_atual="cartao_cnpj",
            confirmado_em_atual=None,
            documento_id_atual="doc-1",
            documento_id_proposto="doc-1",
        ) is True

    def test_a_different_document_still_conflicts(self):
        assert campo_conflitos.mesmo_documento_pendente(
            origem_atual="cartao_cnpj",
            confirmado_em_atual=None,
            documento_id_atual="doc-1",
            documento_id_proposto="doc-2",
        ) is False

    def test_a_confirmed_value_is_never_replaced(self):
        assert campo_conflitos.mesmo_documento_pendente(
            origem_atual="cartao_cnpj",
            confirmado_em_atual="2026-09-20T00:00:00+00:00",
            documento_id_atual="doc-1",
            documento_id_proposto="doc-1",
        ) is False

    def test_a_manual_value_is_never_replaced(self):
        assert campo_conflitos.mesmo_documento_pendente(
            origem_atual="manual",
            confirmado_em_atual=None,
            documento_id_atual="doc-1",
            documento_id_proposto="doc-1",
        ) is False

    def test_nothing_stored_is_never_a_replace(self):
        assert campo_conflitos.mesmo_documento_pendente(
            origem_atual=None,
            confirmado_em_atual=None,
            documento_id_atual=None,
            documento_id_proposto="doc-1",
        ) is False

    def test_a_missing_proposed_document_id_is_never_a_replace(self):
        assert campo_conflitos.mesmo_documento_pendente(
            origem_atual="cartao_cnpj",
            confirmado_em_atual=None,
            documento_id_atual="doc-1",
            documento_id_proposto=None,
        ) is False

    def test_ids_are_compared_as_strings(self):
        """Callers pass a mix of `UUID`/`str` across the three apply
        paths — the SAME id in different types must still match."""
        from uuid import UUID

        doc = UUID("11111111-1111-1111-1111-111111111111")
        assert campo_conflitos.mesmo_documento_pendente(
            origem_atual="cartao_cnpj",
            confirmado_em_atual=None,
            documento_id_atual=str(doc),
            documento_id_proposto=doc,
        ) is True


class TestFecharConflitosPendentes:
    def test_closes_every_pending_row_on_the_owner_and_campo(self, client):
        campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "razao_social",
            valor_anterior="A", origem_anterior="cartao_cnpj",
            valor_proposto="B", origem_proposto="cartao_cnpj",
        )
        fechados = campo_conflitos.fechar_conflitos_pendentes(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "razao_social",
        )
        assert fechados == 1
        row = client.table(campo_conflitos.EMPRESA.table).select("*").execute().data[0]
        assert row["status"] == "rejeitado"
        assert row["decidido_por"] is None
        assert row["decidido_em"] is not None

    def test_a_different_campo_is_left_alone(self, client):
        campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "razao_social",
            valor_anterior="A", origem_anterior="cartao_cnpj",
            valor_proposto="B", origem_proposto="cartao_cnpj",
        )
        campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "uf",
            valor_anterior="SP", origem_anterior="cartao_cnpj",
            valor_proposto="RJ", origem_proposto="cartao_cnpj",
        )
        campo_conflitos.fechar_conflitos_pendentes(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "razao_social",
        )
        rows = client.table(campo_conflitos.EMPRESA.table).select("*").execute().data
        by_campo = {r["campo"]: r["status"] for r in rows}
        assert by_campo["razao_social"] == "rejeitado"
        assert by_campo["uf"] == "pendente"

    def test_nothing_pending_is_a_noop(self, client):
        assert campo_conflitos.fechar_conflitos_pendentes(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "razao_social",
        ) == 0


class TestNotify:
    @pytest.mark.asyncio
    async def test_no_conflicts_is_a_noop(self, client):
        assert await campo_conflitos.notificar_conflitos(
            client, campo_conflitos.EMPRESA, [], None
        ) == 0

    @pytest.mark.asyncio
    async def test_missing_notifier_is_logged_not_dropped(self, client, caplog):
        conflito = campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "uf",
            valor_anterior="SP", origem_anterior="cartao_cnpj",
            valor_proposto="RJ", origem_proposto="cartao_cnpj",
        )
        with caplog.at_level(logging.WARNING):
            sent = await campo_conflitos.notificar_conflitos(
                client, campo_conflitos.EMPRESA, [conflito], None
            )
        assert sent == 0
        assert "sem notificador" in caplog.text

    @pytest.mark.asyncio
    async def test_success_stamps_notificado_em(self, client):
        conflito = campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "uf",
            valor_anterior="SP", origem_anterior="cartao_cnpj",
            valor_proposto="RJ", origem_proposto="cartao_cnpj",
        )
        sent_to = []

        async def _notify_one(c):
            sent_to.append(c["id"])

        sent = await campo_conflitos.notificar_conflitos(
            client, campo_conflitos.EMPRESA, [conflito], _notify_one
        )
        assert sent == 1
        assert sent_to == [conflito["id"]]
        stored = (
            client.table(campo_conflitos.EMPRESA.table)
            .select("*")
            .eq("id", conflito["id"])
            .execute()
        ).data[0]
        assert stored["notificado_em"] is not None

    @pytest.mark.asyncio
    async def test_one_failure_does_not_stop_the_next(self, client, caplog):
        ok = campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, ORG, "empresa-1", "uf",
            valor_anterior="SP", origem_anterior="cartao_cnpj",
            valor_proposto="RJ", origem_proposto="cartao_cnpj",
        )
        boom = campo_conflitos.registrar_conflito(
            client, campo_conflitos.EMPRESA, ORG, "empresa-2", "razao_social",
            valor_anterior="A", origem_anterior="cartao_cnpj",
            valor_proposto="B", origem_proposto="cartao_cnpj",
        )

        async def _notify_one(c):
            if c["id"] == boom["id"]:
                raise RuntimeError("down")

        with caplog.at_level(logging.ERROR):
            sent = await campo_conflitos.notificar_conflitos(
                client, campo_conflitos.EMPRESA, [boom, ok], _notify_one
            )
        assert sent == 1
        boom_row = (
            client.table(campo_conflitos.EMPRESA.table)
            .select("*")
            .eq("id", boom["id"])
            .execute()
        ).data[0]
        ok_row = (
            client.table(campo_conflitos.EMPRESA.table)
            .select("*")
            .eq("id", ok["id"])
            .execute()
        ).data[0]
        assert boom_row["notificado_em"] is None
        assert ok_row["notificado_em"] is not None
