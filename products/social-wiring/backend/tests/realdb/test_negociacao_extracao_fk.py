"""Real-DB FK integrity for the migration 171 `*_documento_id` columns —
S2 contract §G, lesson G5: "a mock hid an FK bug once".

`MockSupabaseClient` never enforces a foreign key: a `valor_negociado_
documento_id` (or `parcela.documento_id`, or `financiamento.<campo>_
documento_id`) pointing at a non-existent `atendimento_documentos.id`
inserts happily under every mock-backed test in `test_negociacao_
extracao.py`. Only a REAL Postgres constraint catches that.

🔴 THIS SUITE CANNOT RUN until migration 171 is applied to whatever
project `SUPABASE_URL` resolves to (`noctus.dev.migrate_product`, the
tech-lead's call — see the migration file's own header) AND that project
is a disposable branch, never prod (`get_realdb_credentials`' own gate —
social-wiring shares the SAME prod project dev does, so this suite is a
loud skip in every environment that has not pointed at a branch).
"""
from __future__ import annotations

import uuid

import pytest
from postgrest.exceptions import APIError


@pytest.fixture
def cleanup(sw_db):
    """`[(table, id), ...]` deleted in REVERSE order on teardown — children
    before parents, so a still-live FK never blocks the cleanup itself."""
    registrados: list[tuple[str, str]] = []
    yield registrados
    for table, row_id in reversed(registrados):
        try:
            sw_db.table(table).delete().eq("id", row_id).execute()
        except APIError:
            pass


@pytest.fixture
def atendimento(sw_db, test_org, cleanup):
    cliente_id = str(uuid.uuid4())
    cleanup.append(("clientes", cliente_id))
    sw_db.table("clientes").insert(
        {"id": cliente_id, "org_id": test_org["id"], "nome": "RealDB FK Test"}
    ).execute()

    atendimento_id = str(uuid.uuid4())
    cleanup.append(("atendimentos", atendimento_id))
    sw_db.table("atendimentos").insert(
        {
            "id": atendimento_id, "org_id": test_org["id"], "cliente_id": cliente_id,
            "titulo": "RealDB FK Test",
        }
    ).execute()
    return atendimento_id


class TestAtendimentoNegociacaoDocumentoFk:
    def test_valor_negociado_documento_id_rejects_an_unknown_document(
        self, sw_db, test_org, atendimento, cleanup,
    ):
        fake_documento_id = str(uuid.uuid4())
        with pytest.raises(APIError):
            sw_db.table("atendimento_negociacao").insert(
                {
                    "atendimento_id": atendimento, "org_id": test_org["id"],
                    "valor_negociado": "500000.00",
                    "valor_negociado_origem": "guia_itbi",
                    "valor_negociado_documento_id": fake_documento_id,
                }
            ).execute()


class TestAtendimentoNegociacaoParcelasDocumentoFk:
    def test_parcela_documento_id_rejects_an_unknown_document(
        self, sw_db, test_org, atendimento, cleanup,
    ):
        parcela_id = str(uuid.uuid4())
        fake_documento_id = str(uuid.uuid4())
        cleanup.append(("atendimento_negociacao_parcelas", parcela_id))
        with pytest.raises(APIError):
            sw_db.table("atendimento_negociacao_parcelas").insert(
                {
                    "id": parcela_id, "atendimento_id": atendimento,
                    "org_id": test_org["id"], "tipo": "financiamento",
                    "valor": "400000.00", "documento_id": fake_documento_id,
                    "origem": "contrato_financiamento",
                }
            ).execute()

    def test_valor_may_be_null_a_relaxation_not_a_regression(
        self, sw_db, test_org, atendimento, cleanup,
    ):
        """Migration 171 dropped `valor`'s NOT NULL — an extraction-created
        parcela must survive a D2 reject with `valor IS NULL`. Confirms the
        relaxation actually landed (never silently reverted by a later
        migration)."""
        parcela_id = str(uuid.uuid4())
        cleanup.append(("atendimento_negociacao_parcelas", parcela_id))
        sw_db.table("atendimento_negociacao_parcelas").insert(
            {
                "id": parcela_id, "atendimento_id": atendimento,
                "org_id": test_org["id"], "tipo": "financiamento", "valor": None,
            }
        ).execute()
        row = (
            sw_db.table("atendimento_negociacao_parcelas").select("valor")
            .eq("id", parcela_id).execute().data[0]
        )
        assert row["valor"] is None


class TestAtendimentoFinanciamentoDocumentoFk:
    def test_agente_financeiro_documento_id_rejects_an_unknown_document(
        self, sw_db, test_org, atendimento, cleanup,
    ):
        fake_documento_id = str(uuid.uuid4())
        with pytest.raises(APIError):
            sw_db.table("atendimento_financiamento").insert(
                {
                    "atendimento_id": atendimento, "org_id": test_org["id"],
                    "agente_financeiro_documento_id": fake_documento_id,
                    "agente_financeiro_origem": "proposta_financiamento",
                }
            ).execute()


class TestAtendimentoFavorecidosDocumentoFk:
    def test_favorecido_documento_id_rejects_an_unknown_document(
        self, sw_db, test_org, atendimento, cleanup,
    ):
        favorecido_id = str(uuid.uuid4())
        fake_documento_id = str(uuid.uuid4())
        cleanup.append(("atendimento_favorecidos", favorecido_id))
        with pytest.raises(APIError):
            sw_db.table("atendimento_favorecidos").insert(
                {
                    "id": favorecido_id, "atendimento_id": atendimento,
                    "org_id": test_org["id"], "nome": "Vendedor RealDB Test",
                    "documento_id": fake_documento_id, "origem": "contrato_financiamento",
                }
            ).execute()
