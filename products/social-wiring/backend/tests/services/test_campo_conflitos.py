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

    def test_a_second_call_with_the_same_proposed_value_is_a_noop(self, client):
        first = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="b", origem_proposto="rg",
        )
        second = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="b", origem_proposto="rg",
        )
        assert first is not None
        assert second is None
        stored = (
            client.table(campo_conflitos.CLIENTE.table).select("*").execute()
        ).data
        assert len(stored) == 1
        assert stored[0]["status"] == "pendente"

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

    def test_a_second_call_with_a_different_value_supersedes_the_stale_row(
        self, client
    ):
        """The fix (audit finding, 2026-09-28): a CORRECTED proposal must
        not be silently dropped just because a stale one is still
        pending."""
        primeiro = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="b", origem_proposto="rg",
        )
        segundo = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="c", origem_proposto="rg",
        )
        assert segundo is not None
        assert segundo["valor_proposto"] == "c"
        stored = (
            client.table(campo_conflitos.CLIENTE.table).select("*").execute()
        ).data
        assert len(stored) == 2
        by_id = {r["id"]: r for r in stored}
        assert by_id[primeiro["id"]]["status"] == "rejeitado"
        assert by_id[primeiro["id"]]["decidido_por"] is None
        assert by_id[primeiro["id"]]["decidido_em"] is not None
        assert by_id[segundo["id"]]["status"] == "pendente"

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


class TestJaRejeitadoPeloUsuario:
    """N=3 formalization (`NOC-REMEDIATE[imovel-rejeitado-antes-decidido-
    por]`, 2026-09-28) — the ONE shared REJEITADO_ANTES check `imovel_hub.
    campos_extraidos_service.aplicar` and `card_hub.negociacao_extracao_
    service._ja_rejeitado_pelo_usuario` both now call."""

    def _rejeitar(self, client, table, row_id, *, decidido_por):
        client.table(table.table).update(
            {"status": "rejeitado", "decidido_por": decidido_por}
        ).eq("id", row_id).execute()

    def test_a_human_rejected_value_blocks_reproposal(self, client):
        row = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="b", origem_proposto="rg",
        )
        self._rejeitar(client, campo_conflitos.CLIENTE, row["id"], decidido_por="admin-1")
        assert campo_conflitos.ja_rejeitado_pelo_usuario(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg", "b",
        ) is True

    def test_a_machine_superseded_value_does_not_block_reproposal(self, client):
        """`registrar_conflito`'s own supersede-on-disagreeing-dedupe also
        lands a row in `status='rejeitado'`, with `decidido_por=None` (a
        SYSTEM resolution, never shown to a human) — that must never block
        the SAME value being proposed again later (the imóvel-side bug this
        formalization fixes)."""
        primeiro = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="b", origem_proposto="rg",
        )
        campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="c", origem_proposto="rg",
        )
        stored = (
            client.table(campo_conflitos.CLIENTE.table).select("*")
            .eq("id", primeiro["id"]).execute()
        ).data[0]
        assert stored["status"] == "rejeitado"
        assert stored["decidido_por"] is None
        assert campo_conflitos.ja_rejeitado_pelo_usuario(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg", "b",
        ) is False

    def test_a_different_proposed_value_never_blocks(self, client):
        row = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg",
            valor_anterior="a", origem_anterior="manual",
            valor_proposto="b", origem_proposto="rg",
        )
        self._rejeitar(client, campo_conflitos.CLIENTE, row["id"], decidido_por="admin-1")
        assert campo_conflitos.ja_rejeitado_pelo_usuario(
            client, campo_conflitos.CLIENTE, ORG, "cliente-1", "rg", "z",
        ) is False

    def test_a_custom_igual_comparator_is_used_when_given(self, client):
        """Imóvel passes its own field-aware `iguais` — a comparator that
        treats `12.846` and `12846` as the same `numero_matricula`."""
        row = campo_conflitos.registrar_conflito(
            client, campo_conflitos.IMOVEL, ORG, "SP-001", "numero_matricula",
            valor_anterior="12345", origem_anterior="matricula",
            valor_proposto="12.846", origem_proposto="matricula",
        )
        self._rejeitar(client, campo_conflitos.IMOVEL, row["id"], decidido_por="admin-1")
        assert campo_conflitos.ja_rejeitado_pelo_usuario(
            client, campo_conflitos.IMOVEL, ORG, "SP-001", "numero_matricula", "12846",
            igual=lambda proposto: proposto.replace(".", "") == "12846",
        ) is True


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


def _mesmo_valor(campo: str, a, b) -> bool:
    if a is None or b is None:
        return False
    return str(a).strip().upper() == str(b).strip().upper()


class TestHistoricoValores:
    def test_every_proposal_ever_made_on_owner_campo_is_returned(self, client):
        campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-h1", "cpf",
            valor_anterior=None, origem_anterior=None,
            valor_proposto="A", origem_proposto="cnh",
        )
        campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-h1", "cpf",
            valor_anterior="A", origem_anterior="cnh",
            valor_proposto="B", origem_proposto="rg",
        )
        historico = campo_conflitos.historico_valores(
            client, campo_conflitos.CLIENTE, ORG, "cliente-h1", "cpf"
        )
        assert set(historico) == {("A", "cnh"), ("B", "rg")}

    def test_a_different_owner_or_campo_is_not_mixed_in(self, client):
        campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-h2", "cpf",
            valor_anterior=None, origem_anterior=None,
            valor_proposto="A", origem_proposto="cnh",
        )
        assert campo_conflitos.historico_valores(
            client, campo_conflitos.CLIENTE, ORG, "cliente-other", "cpf"
        ) == []
        assert campo_conflitos.historico_valores(
            client, campo_conflitos.CLIENTE, ORG, "cliente-h2", "rg"
        ) == []


class TestResolverERegistrar:
    def test_a_tier_win_inserts_a_resolved_row_directly_never_pendente(self, client):
        decisao = campo_conflitos.resolver_e_registrar(
            client, campo_conflitos.CLIENTE, ORG, "cliente-r1", "cpf",
            valor_anterior="412.954.238-98", origem_anterior="cnh",
            valor_proposto="303.102.653-55", origem_proposto="certidao_casamento",
            confianca_proposta="alta", fonte_tabela="cliente_documentos", fonte_id="doc-r1",
            mesmo_valor=_mesmo_valor,
        )
        assert decisao.vencedor == "atual"
        assert not decisao.requer_humano
        rows = (
            client.table(campo_conflitos.CLIENTE.table).select("*")
            .eq("cliente_id", "cliente-r1").execute()
        ).data
        assert len(rows) == 1
        assert rows[0]["status"] == "resolvido_automatico"
        assert rows[0]["decidido_por"] is None
        assert rows[0]["decidido_em"] is not None
        assert "[tier]" in rows[0]["motivo_resolucao"]

    def test_a_human_required_verdict_writes_nothing(self, client):
        decisao = campo_conflitos.resolver_e_registrar(
            client, campo_conflitos.CLIENTE, ORG, "cliente-r2", "nacionalidade",
            valor_anterior="brasileiro", origem_anterior="cnh",
            valor_proposto="brasileira", origem_proposto="matricula",
            mesmo_valor=_mesmo_valor,
        )
        assert decisao.requer_humano
        rows = (
            client.table(campo_conflitos.CLIENTE.table).select("*")
            .eq("cliente_id", "cliente-r2").execute()
        ).data
        assert rows == []

    def test_an_existing_pendente_row_is_updated_in_place_not_duplicated(self, client):
        pendente = campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-r3", "cpf",
            valor_anterior="412.954.238-98", origem_anterior="cnh",
            valor_proposto="303.102.653-55", origem_proposto="certidao_casamento",
        )
        decisao = campo_conflitos.resolver_e_registrar(
            client, campo_conflitos.CLIENTE, ORG, "cliente-r3", "cpf",
            valor_anterior=pendente["valor_anterior"],
            origem_anterior=pendente["origem_anterior"],
            valor_proposto=pendente["valor_proposto"],
            origem_proposto=pendente["origem_proposto"],
            mesmo_valor=_mesmo_valor,
            conflito_existente_id=pendente["id"],
        )
        assert decisao.vencedor == "atual"
        rows = (
            client.table(campo_conflitos.CLIENTE.table).select("*")
            .eq("cliente_id", "cliente-r3").execute()
        ).data
        assert len(rows) == 1  # updated, not a second row
        assert rows[0]["id"] == pendente["id"]
        assert rows[0]["status"] == "resolvido_automatico"

    def test_the_generic_resolver_composes_with_historico_for_corroboration(self, client):
        # A THIRD document already proposed the on-file value — corroboration
        # should win even though the two candidates' OWN tiers alone would
        # tie (rg vs serasa_crednet are both 100% for nome_oficial).
        campo_conflitos.registrar_conflito(
            client, campo_conflitos.CLIENTE, ORG, "cliente-r4", "nome_oficial",
            valor_anterior=None, origem_anterior=None,
            valor_proposto="ANA PAULA SOUZA", origem_proposto="matricula",
        )
        decisao = campo_conflitos.resolver_e_registrar(
            client, campo_conflitos.CLIENTE, ORG, "cliente-r4", "nome_oficial",
            valor_anterior="ANA PAULA SOUZA", origem_anterior="rg",
            valor_proposto="ANA PAULA SOUZA COSTA", origem_proposto="serasa_crednet",
            mesmo_valor=_mesmo_valor,
        )
        assert decisao.vencedor == "atual"
        assert decisao.regra == "corroboracao"
