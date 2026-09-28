"""IgIg's background jobs (`app/scheduler.py`) — registration + one tick each
for the jobs closed out in this dispatch:

  * ``igig_financeiro_inadimplencia`` — daily cross-org overdue sweep
    (`financeiro_service.atualizar_inadimplencia` existed unregistered).
  * ``igig_publicacao_fila`` — every-5-minutes cross-org publish worker
    (`publicacao_publisher.processar_fila_publicacao` existed unregistered),
    fronted by the crash-recovery sweep `publicacao_publisher.liberar_travadas`.
  * ``igig_lembretes_pendentes`` — every-5-minutes card-hub reminder delivery
    (`notificacoes.processar_lembretes_pendentes` existed unregistered).

No monkeypatching of our own guards: every test below exercises the REAL
service function end to end against the shared `igig`/`core` mocks (same
fixtures `tests/services/test_notificacoes.py` and the router suites use);
the only seam swapped is `database._db.get_admin_client`/`get_core_client`
— an external-boundary dependency, not logic under test.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from noctusai_lib.api import scheduler as seed_scheduler
from noctusai_lib.integrations.persistence import SupabaseRecordStore

from app import database
from app import scheduler as igig_scheduler
from app.card_hub import CARD_HUB_CLIENTE
from app.dependencies import coerce_org_uuid
from app.repositories import Repositorios

ORG = str(coerce_org_uuid("test-org-123"))
OUTRA_ORG = str(coerce_org_uuid("test-org-456"))

JOB_IDS = {
    "igig_gmail_watch_renovar",
    "igig_automacoes_sla",
    "igig_pautas_extensao",
    "igig_financeiro_inadimplencia",
    "igig_publicacao_fila",
    "igig_lembretes_pendentes",
}


@pytest.fixture
def fresh_scheduler():
    seed_scheduler.reset_for_testing()
    yield seed_scheduler
    seed_scheduler.reset_for_testing()


def test_configure_registers_every_igig_job(fresh_scheduler):
    igig_scheduler.configure()
    registered = {job.id for job in fresh_scheduler.scheduler.get_jobs()}
    assert JOB_IDS <= registered


def test_configure_is_idempotent(fresh_scheduler):
    igig_scheduler.configure()
    igig_scheduler.configure()
    ids = [job.id for job in fresh_scheduler.scheduler.get_jobs()]
    assert sorted(ids) == sorted(set(ids))


class TestJobFinanceiroInadimplencia:
    def test_one_tick_marks_overdue_fatura_and_cliente(self, igig_db, monkeypatch):
        repos = Repositorios(SupabaseRecordStore(igig_db))
        cliente = repos.cliente.criar(ORG, {"nome": "Padaria Sol", "status": "ativo"})
        fatura = repos.fatura.criar(ORG, {
            "cliente_id": cliente["id"], "competencia": "2026-08",
            "valor_total": 500, "status": "aberta", "vencimento": "2026-08-01",
        })
        monkeypatch.setattr(database._db, "get_admin_client", lambda: igig_db)

        asyncio.run(igig_scheduler.job_financeiro_inadimplencia())

        assert repos.fatura.buscar(ORG, fatura["id"])["status"] == "vencida"
        assert repos.cliente.buscar(ORG, cliente["id"])["status"] == "inadimplente"

    def test_job_survives_admin_client_failure(self, monkeypatch, caplog):
        def _quebrado():
            raise RuntimeError("supabase indisponível")

        monkeypatch.setattr(database._db, "get_admin_client", _quebrado)
        # Must not raise — a job failure is loud in the log, never fatal.
        asyncio.run(igig_scheduler.job_financeiro_inadimplencia())
        assert "job igig_financeiro_inadimplencia falhou" in caplog.text


class TestJobPublicacaoFila:
    def _publicacao_agendada(self, db, org_id, *, agendada_para: str) -> dict:
        cliente = db.table("cliente").insert({"org_id": org_id, "nome": "Cliente"}).execute().data[0]
        pauta = db.table("pauta").insert(
            {"org_id": org_id, "cliente_id": cliente["id"], "titulo": "Post"}
        ).execute().data[0]
        return db.table("publicacao").insert({
            "org_id": org_id, "pauta_id": pauta["id"], "canal": "instagram",
            "status": "agendada", "agendada_para": agendada_para,
        }).execute().data[0]

    def test_one_tick_reaches_every_org_with_a_due_publicacao(self, igig_db, monkeypatch):
        """`instagram` is not a homologated channel yet (`CANAIS_HOMOLOGADOS`
        is empty — `NOC-REMEDIATE[igig-publishing]`), so a real tick leaves
        both rows `ignorada`d rather than published; that in itself is the
        proof the fan-out REACHED both orgs without crashing on the first —
        the same shape `distribuicao_router`'s own worker tests read."""
        passado = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        p1 = self._publicacao_agendada(igig_db, ORG, agendada_para=passado)
        p2 = self._publicacao_agendada(igig_db, OUTRA_ORG, agendada_para=passado)
        monkeypatch.setattr(database._db, "get_admin_client", lambda: igig_db)

        asyncio.run(igig_scheduler.job_publicacao_fila())

        [linha1] = igig_db.table("publicacao").select("*").eq("id", p1["id"]).execute().data
        [linha2] = igig_db.table("publicacao").select("*").eq("id", p2["id"]).execute().data
        # Untouched (never claimed) — an unhomologated channel is skipped,
        # not failed; but reaching the ELSE branch for org 2 as well as org 1
        # is exactly what an early-return-after-first-org bug would break.
        assert linha1["status"] == "agendada"
        assert linha2["status"] == "agendada"

    def test_one_tick_recovers_a_publicacao_stuck_in_publicando(self, igig_db, monkeypatch):
        travada = self._publicacao_agendada(
            igig_db, ORG, agendada_para=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        )
        antiga = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        igig_db.table("publicacao").update(
            {"status": "publicando", "updated_at": antiga}
        ).eq("id", travada["id"]).execute()
        monkeypatch.setattr(database._db, "get_admin_client", lambda: igig_db)

        asyncio.run(igig_scheduler.job_publicacao_fila())

        [linha] = igig_db.table("publicacao").select("*").eq("id", travada["id"]).execute().data
        assert linha["status"] == "agendada"
        assert linha["erro"] == "tentativa interrompida"

    def test_a_freshly_claimed_publicacao_is_left_alone(self, igig_db, monkeypatch):
        """The 15-minute grace window: a publish genuinely in flight right
        now must not be yanked back to `agendada` mid-attempt."""
        travada = self._publicacao_agendada(
            igig_db, ORG, agendada_para=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        )
        recente = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        igig_db.table("publicacao").update(
            {"status": "publicando", "updated_at": recente}
        ).eq("id", travada["id"]).execute()
        monkeypatch.setattr(database._db, "get_admin_client", lambda: igig_db)

        asyncio.run(igig_scheduler.job_publicacao_fila())

        [linha] = igig_db.table("publicacao").select("*").eq("id", travada["id"]).execute().data
        assert linha["status"] == "publicando"

    def test_job_survives_admin_client_failure(self, monkeypatch, caplog):
        def _quebrado():
            raise RuntimeError("indisponível")

        monkeypatch.setattr(database._db, "get_admin_client", _quebrado)
        asyncio.run(igig_scheduler.job_publicacao_fila())
        assert "job igig_publicacao_fila falhou" in caplog.text


class TestJobLembretesPendentes:
    def test_one_tick_delivers_a_due_reminder(self, igig_db, core_db, monkeypatch):
        cliente = igig_db.table("cliente").insert(
            {"org_id": ORG, "nome": "Padaria Sol"}
        ).execute().data[0]
        prof = igig_db.table("profissional").insert(
            {"org_id": ORG, "nome": "Ana", "usuario_id": "user-ana", "ativo": True}
        ).execute().data[0]
        igig_db.table(CARD_HUB_CLIENTE.tables.membros).insert(
            {"org_id": ORG, "cliente_id": cliente["id"], "profissional_id": prof["id"]}
        ).execute()
        passado = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        igig_db.table(CARD_HUB_CLIENTE.tables.lembretes).insert({
            "org_id": ORG, "cliente_id": cliente["id"], "dispara_em": passado,
            "enviado_em": None, "cancelado_em": None, "destinatarios": [],
        }).execute()
        monkeypatch.setattr(database._db, "get_admin_client", lambda: igig_db)
        monkeypatch.setattr(database._db, "get_core_client", lambda: core_db)

        asyncio.run(igig_scheduler.job_lembretes_pendentes())

        [notificacao] = core_db.table("notifications")._data
        assert notificacao["user_id"] == "user-ana"
        [atualizado] = igig_db.table(CARD_HUB_CLIENTE.tables.lembretes)._data
        assert atualizado["enviado_em"] is not None

    def test_job_survives_a_failure(self, monkeypatch, caplog):
        def _quebrado():
            raise RuntimeError("indisponível")

        monkeypatch.setattr(database._db, "get_admin_client", _quebrado)
        asyncio.run(igig_scheduler.job_lembretes_pendentes())
        assert "job igig_lembretes_pendentes falhou" in caplog.text
