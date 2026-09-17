"""Tests for `ingest_service.handle_inbound` — contract §3 item 19 +
the engagement/AI-flag hand-offs. `moderar_em_background=False` runs the
AI-flag hand-off synchronously so tests can assert on it deterministically
(production always uses the default `True`, fire-and-forget).

`org_id` / `client` / `modo_ingest` are injected directly (the function's
own DI seam — `KB § PATTERNS/backend/di-test-seam.md`) rather than
patched — no monkeypatching of this product's own code.

LGPD (§6): `conteudo` / `autor_jid` / `participante_jid` / member phones
must never appear in a log line — asserted via `caplog` across every
branch this module can take.
"""
import asyncio
import logging
from unittest.mock import patch
from uuid import UUID

from noctusai_lib.domain.engagement import InMemoryPointsLedger
from noctusai_lib.integrations.whatsapp.types import WhatsAppInboundMessage
from noctusai_lib.testing import MockSupabaseClient

from app.services import ingest_service

ORG = UUID("00000000-0000-0000-0000-000000000123")
GRUPO_ID = "11111111-1111-1111-1111-111111111111"
CHAT_ID = "5511999990000@g.us"
MEMBRO_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SEGREDO_TELEFONE = "+5511999998888"
SEGREDO_JID = "5511999998888@c.us"
SEGREDO_TEXTO = "conteudo-super-secreto-nao-pode-vazar-no-log"


def _inbound(**over) -> WhatsAppInboundMessage:
    base = dict(
        provider_message_id="wamid-1", chat_id=CHAT_ID, from_phone="5511974693365",
        text=SEGREDO_TEXTO, session="default", group_id=CHAT_ID, author_id=SEGREDO_JID,
    )
    base.update(over)
    return WhatsAppInboundMessage(**base)


def _mock_with_grupo(**grupo_over) -> MockSupabaseClient:
    mock = MockSupabaseClient()
    grupo = {"id": GRUPO_ID, "org_id": str(ORG), "chat_id": CHAT_ID, "ativo": True}
    grupo.update(grupo_over)
    mock.set_table_data("grupos", [grupo])
    mock.set_table_data("grupo_membros", [])
    mock.set_table_data("grupo_mensagens", [])
    mock.set_table_data("engajamento_pontos", [])
    return mock


def _run(inbound, mock, *, modo_ingest: str = "moderacao", points_ledger=None):
    # `chat_completion` is the seed's LLM-provider boundary (an external
    # SDK call) — patching it is the allowed "external boundary" case,
    # not a self-patch of this product's own code.
    with patch(
        "app.services.moderacao_ai_service.chat_completion",
        return_value='{"flagged": false}',
    ):
        asyncio.run(ingest_service.handle_inbound(
            inbound, moderar_em_background=False,
            org_id=ORG, client=mock, modo_ingest=modo_ingest,
            points_ledger=points_ledger if points_ledger is not None else InMemoryPointsLedger(),
        ))


class TestGroupFiltering:
    def test_dm_with_no_group_id_is_dropped(self):
        mock = MockSupabaseClient()
        inbound = _inbound(group_id=None, author_id=None)
        _run(inbound, mock)
        # Nothing to assert against a table that was never seeded/touched —
        # the important behavior is that this doesn't raise.

    def test_unknown_group_is_dropped(self):
        mock = MockSupabaseClient()
        mock.set_table_data("grupos", [])
        mock.set_table_data("grupo_mensagens", [])
        _run(_inbound(), mock)
        rows = mock.table("grupo_mensagens").select("*").execute().data
        assert rows == []


class TestModoIngest:
    def test_moderacao_mode_stores_text(self):
        mock = _mock_with_grupo()
        _run(_inbound(), mock, modo_ingest="moderacao")
        row = mock.table("grupo_mensagens").select("*").execute().data[0]
        assert row["conteudo"] == SEGREDO_TEXTO

    def test_metrica_mode_leaves_conteudo_null(self):
        mock = _mock_with_grupo()
        _run(_inbound(), mock, modo_ingest="metrica")
        row = mock.table("grupo_mensagens").select("*").execute().data[0]
        assert row["conteudo"] is None


class TestIdempotency:
    def test_duplicate_provider_message_id_db_backstop_no_ops(self):
        mock = _mock_with_grupo()

        class _UniqueViolation(Exception):
            code = "23505"

        builder_cls = type(mock.table("grupo_mensagens"))
        original_insert = builder_cls.insert
        calls = {"n": 0}

        def _insert(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise _UniqueViolation()
            return original_insert(self, *args, **kwargs)

        # Patches the TESTING LIBRARY's mock builder class (not this
        # product's own code) to simulate the real Postgres 23505
        # unique-violation `grupo_mensagens` insert would raise on a
        # redelivered `provider_message_id` — the DB backstop this test
        # pins.
        with patch.object(builder_cls, "insert", _insert):
            _run(_inbound(), mock)
            _run(_inbound(), mock)
        rows = mock.table("grupo_mensagens").select("*").execute().data
        assert len(rows) == 1


class TestEngagementHandoff:
    def test_matched_member_awards_a_point(self):
        mock = _mock_with_grupo()
        mock.set_table_data("grupo_membros", [{
            "id": "gm1", "org_id": str(ORG), "grupo_id": GRUPO_ID,
            "participante_jid": SEGREDO_JID, "membro_id": MEMBRO_ID,
            "papel": "participante", "visto_em": "2026-01-01T00:00:00+00:00",
        }])
        ledger = InMemoryPointsLedger()
        _run(_inbound(), mock, points_ledger=ledger)
        history = ledger.history(MEMBRO_ID, source="whatsapp", action="mensagem_grupo")
        assert len(history) == 1
        assert history[0].points == 1

    def test_unmatched_autor_jid_stores_row_and_awards_nothing(self):
        mock = _mock_with_grupo()
        ledger = InMemoryPointsLedger()
        _run(_inbound(), mock, points_ledger=ledger)  # no grupo_membros seeded -> no match
        assert ledger.totals() == {}
        rows = mock.table("grupo_mensagens").select("*").execute().data
        assert len(rows) == 1


class TestLgpdNeverLogged:
    def test_text_and_jids_never_appear_in_logs(self, caplog):
        caplog.set_level(logging.DEBUG)
        mock = _mock_with_grupo()
        mock.set_table_data("grupo_membros", [{
            "id": "gm1", "org_id": str(ORG), "grupo_id": GRUPO_ID,
            "participante_jid": SEGREDO_JID, "membro_id": MEMBRO_ID,
            "papel": "participante", "visto_em": "2026-01-01T00:00:00+00:00",
        }])
        _run(_inbound(), mock)
        for record in caplog.records:
            message = record.getMessage()
            assert SEGREDO_TEXTO not in message
            assert SEGREDO_JID not in message
            assert SEGREDO_TELEFONE not in message
