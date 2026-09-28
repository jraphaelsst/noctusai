"""Card-hub reminders — the DELIVERY half `noctusai_lib.domain.card_hub.
lembretes` never ran (`NOC-REMEDIATE[reminder-delivery]`, plat achado #9).

Rows are materialised correctly by the seed's `sync_lembrete` (not exercised
here — that is the SCHEDULING side, a separate concern); these tests plant a
row directly, the same shape `sync_lembrete` would have written, and prove
`processar_lembretes_pendentes` turns a DUE one into an in-app notification
exactly once, leaves a future/cancelled/already-sent one alone, and never
silently drops a reminder nobody can be told about.
"""
from datetime import datetime, timedelta, timezone

from app.card_hub import CARD_HUB_CLIENTE, CARD_HUB_NEGOCIO
from app.dependencies import coerce_org_uuid
from app.services.notificacoes import processar_lembretes_pendentes

ORG = str(coerce_org_uuid("test-org-123"))


def _ha(minutos: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutos)).isoformat()


def _em(minutos: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutos)).isoformat()


def _cliente(igig_db, nome="Padaria Sol") -> dict:
    return igig_db.table("cliente").insert({"org_id": ORG, "nome": nome}).execute().data[0]


def _lembrete_cliente(igig_db, cliente_id, **over) -> dict:
    linha = {
        "org_id": ORG, "cliente_id": cliente_id, "dispara_em": _ha(5),
        "enviado_em": None, "cancelado_em": None, "destinatarios": [],
        **over,
    }
    return igig_db.table(CARD_HUB_CLIENTE.tables.lembretes).insert(linha).execute().data[0]


def _profissional_vinculado(igig_db, usuario_id="user-ana") -> dict:
    return igig_db.table("profissional").insert(
        {"org_id": ORG, "nome": "Ana", "usuario_id": usuario_id, "ativo": True}
    ).execute().data[0]


class TestProcessarLembretesPendentes:
    def test_delivers_a_due_reminder_with_a_linked_member(self, igig_db, core_db):
        cliente = _cliente(igig_db)
        prof = _profissional_vinculado(igig_db)
        igig_db.table(CARD_HUB_CLIENTE.tables.membros).insert(
            {"org_id": ORG, "cliente_id": cliente["id"], "profissional_id": prof["id"]}
        ).execute()
        _lembrete_cliente(igig_db, cliente["id"])

        resumo = processar_lembretes_pendentes(igig_db, core_db)
        assert resumo == {"processados": 1, "notificados": 1, "sem_destinatario": 0, "falhas": 0}

        [notificacao] = core_db.table("notifications")._data
        assert notificacao["user_id"] == "user-ana"
        assert "Padaria Sol" in notificacao["title"]
        assert notificacao["metadata"]["link"] == f"/clientes?id={cliente['id']}"

        [atualizado] = igig_db.table(CARD_HUB_CLIENTE.tables.lembretes)._data
        assert atualizado["enviado_em"] is not None

    def test_a_future_reminder_is_left_alone(self, igig_db, core_db):
        cliente = _cliente(igig_db)
        _lembrete_cliente(igig_db, cliente["id"], dispara_em=_em(60))
        resumo = processar_lembretes_pendentes(igig_db, core_db)
        assert resumo["processados"] == 0
        assert core_db.table("notifications")._data == []

    def test_a_cancelled_reminder_is_skipped(self, igig_db, core_db):
        cliente = _cliente(igig_db)
        _lembrete_cliente(igig_db, cliente["id"], cancelado_em=_ha(1))
        resumo = processar_lembretes_pendentes(igig_db, core_db)
        assert resumo["processados"] == 0

    def test_an_already_sent_reminder_is_not_redelivered(self, igig_db, core_db):
        cliente = _cliente(igig_db)
        _lembrete_cliente(igig_db, cliente["id"], enviado_em=_ha(1))
        resumo = processar_lembretes_pendentes(igig_db, core_db)
        assert resumo["processados"] == 0

    def test_falls_back_to_org_admins_when_no_member_is_linked(self, igig_db, core_db):
        cliente = _cliente(igig_db)
        core_db.table("noctus_users").insert(
            {"id": "admin-1", "org_id": ORG, "org_role": "owner"}
        ).execute()
        _lembrete_cliente(igig_db, cliente["id"])

        resumo = processar_lembretes_pendentes(igig_db, core_db)
        assert resumo["notificados"] == 1
        [notificacao] = core_db.table("notifications")._data
        assert notificacao["user_id"] == "admin-1"

    def test_no_recipient_at_all_is_left_pending_not_marked_sent(self, igig_db, core_db):
        cliente = _cliente(igig_db)
        _lembrete_cliente(igig_db, cliente["id"])

        resumo = processar_lembretes_pendentes(igig_db, core_db)
        assert resumo == {"processados": 1, "notificados": 0, "sem_destinatario": 1, "falhas": 0}
        assert core_db.table("notifications")._data == []
        [linha] = igig_db.table(CARD_HUB_CLIENTE.tables.lembretes)._data
        assert linha["enviado_em"] is None

    def test_a_negocio_reminder_links_to_the_comercial_board(self, igig_db, core_db):
        negocio = igig_db.table("negocio").insert(
            {"org_id": ORG, "titulo": "Padaria Sol", "status": "aberto", "kanban_pos": "0"}
        ).execute().data[0]
        prof = _profissional_vinculado(igig_db)
        igig_db.table(CARD_HUB_NEGOCIO.tables.membros).insert(
            {"org_id": ORG, "negocio_id": negocio["id"], "profissional_id": prof["id"]}
        ).execute()
        igig_db.table(CARD_HUB_NEGOCIO.tables.lembretes).insert({
            "org_id": ORG, "negocio_id": negocio["id"], "dispara_em": _ha(5),
            "enviado_em": None, "cancelado_em": None, "destinatarios": [],
        }).execute()

        processar_lembretes_pendentes(igig_db, core_db)
        [notificacao] = core_db.table("notifications")._data
        assert notificacao["metadata"]["link"] == f"/comercial?negocio={negocio['id']}"

    def test_a_bad_row_does_not_stop_the_sweep(self, igig_db, core_db):
        """One malformed reminder (missing its own entity fk) must not
        swallow the others in the same sweep."""
        cliente = _cliente(igig_db)
        prof = _profissional_vinculado(igig_db)
        igig_db.table(CARD_HUB_CLIENTE.tables.membros).insert(
            {"org_id": ORG, "cliente_id": cliente["id"], "profissional_id": prof["id"]}
        ).execute()
        igig_db.table(CARD_HUB_CLIENTE.tables.lembretes).insert({
            "org_id": ORG, "dispara_em": _ha(5),  # no cliente_id — malformed
            "enviado_em": None, "cancelado_em": None, "destinatarios": [],
        }).execute()
        _lembrete_cliente(igig_db, cliente["id"])

        resumo = processar_lembretes_pendentes(igig_db, core_db)
        assert resumo["processados"] == 2
        assert resumo["falhas"] == 1
        assert resumo["notificados"] == 1
