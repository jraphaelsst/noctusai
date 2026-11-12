"""Per-agent phone allow-list (migration 085, owner 2026-11-12): EMPTY = every number is answered; non-empty = ONLY those
numbers; the on/off is the existing ``modo``. Decision rows, the turn endpoint, the status / controle reads, the Studio
PUT (+ audit) and the migration pin."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.channels.controles import (
    STATUS_AGENTE_DESLIGADO,
    STATUS_CONTROLE_INDISPONIVEL,
    STATUS_NORMAL,
    STATUS_RESTRITO_AVALIACAO,
    ParticipanteView,
    ThreadView,
    decidir,
)
from app.stores.agent_controles import FakeAgentControleStore, normalizar_contatos
from noctusai_lib.testing.migrations import migration_sql
from tests.channels.conftest import chan, turn_body  # noqa: F401 — fixture
from tests.routers.conftest import DEFAULT_USER_ID

AGORA = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
THREAD = ThreadView(ultima_mensagem_lead_em=AGORA)
PART = ParticipanteView(estado="ativo", entrou_em=AGORA)
DONO = "+5511999990000"
AMIGO = "+5511888880000"
FORA = "+5511777770000"
CTL = "/api/studio/agents/julia/controle"


def _d(modo="ligado", telefone=FORA, lista=(), gatilho="mensagem", thread=None, **kw):
    return decidir(modo, thread, PART if thread else None, gatilho, AGORA,
                   contatos_permitidos=lista, telefone_e164=telefone, **kw)


# ── decidir ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("telefone", [FORA, DONO, None, "sem numero"])
def test_empty_list_and_on_answers_every_number_even_without_a_phone(telefone):
    d = _d(telefone=telefone, lista=())
    assert (d.status, d.criar_thread, d.executar_llm) == (STATUS_NORMAL, True, True)


@pytest.mark.parametrize("telefone", [DONO, "5511999990000", "+55 (11) 99999-0000"])
def test_a_listed_number_is_answered_in_any_format(telefone):
    assert _d(telefone=telefone, lista=(DONO, AMIGO)).status == STATUS_NORMAL


@pytest.mark.parametrize("gatilho", ["mensagem", "reengajamento"])
@pytest.mark.parametrize("thread", [None, THREAD])
@pytest.mark.parametrize("telefone", [FORA, None, ""])
def test_an_unlisted_number_with_a_non_empty_list_is_refused_and_never_stored(gatilho, thread, telefone):
    d = _d(telefone=telefone, lista=(DONO,), gatilho=gatilho, thread=thread)
    assert d.status == STATUS_RESTRITO_AVALIACAO
    assert (d.persistir_inbound, d.executar_llm, d.criar_thread, d.transicao) == (False, False, False, None)


def test_off_answers_nobody_listed_or_not():
    assert _d("desligado", telefone=DONO, lista=(DONO,)).status == STATUS_AGENTE_DESLIGADO
    assert _d("desligado", telefone=FORA, lista=()).status == STATUS_AGENTE_DESLIGADO


def test_an_unreadable_list_is_a_503():
    d = _d(lista=None)
    assert (d.status, d.http_status, d.persistir_inbound, d.executar_llm) == (STATUS_CONTROLE_INDISPONIVEL, 503, False, False)


def test_default_arguments_leave_the_decision_table_untouched():
    """Julia never passes the list: the call with and without it agree for every mode / trigger / thread shape."""
    for modo in ("ligado", "drenando", "desligado"):
        for gatilho in ("mensagem", "reengajamento"):
            for thread in (None, THREAD):
                a = decidir(modo, thread, PART if thread else None, gatilho, AGORA)
                b = decidir(modo, thread, PART if thread else None, gatilho, AGORA, contatos_permitidos=())
                assert a == b


def test_normalizar_contatos_dedupes_and_refuses_a_non_phone():
    assert normalizar_contatos(["+55 (11) 99999-0000", "5511999990000", AMIGO]) == (DONO, AMIGO)
    with pytest.raises(ValueError):
        normalizar_contatos(["abc"])
    with pytest.raises(ValueError):
        normalizar_contatos([f"+55119{i:08d}" for i in range(101)])


# ── the turn endpoint ───────────────────────────────────────────────────────


def _lista(chan, *numeros):
    chan.controles.set_contatos_permitidos(chan.org_id, chan.agent.id, numeros=list(numeros))


def test_turn_empty_list_answers(chan):
    chan.seed_agent()
    assert chan.turn(turn_body("Oi")).json()["status"] == "respondido"


def test_turn_listed_number_is_answered(chan):
    chan.seed_agent()
    _lista(chan, "55 (11) 99999-0000")  # turn_body's contact is +5511999990000
    assert chan.turn(turn_body("Oi")).json()["status"] == "respondido"


def test_turn_unlisted_number_gets_no_reply_no_thread_and_nothing_stored(chan):
    chan.seed_agent()
    _lista(chan, AMIGO)
    resp = chan.turn(turn_body("Oi, segredo"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "restrito_avaliacao" and body["thread_id"] is None and body["reply"]["partes"] == []
    assert not [c for c in chan.provider.calls if c["method"] == "chat_with_tools"]
    assert not any("segredo" in str(c) for c in chan.provider.calls)


def test_turn_off_answers_nobody_even_a_listed_number(chan):
    chan.seed_agent()
    _lista(chan, DONO)
    chan.controles.set(chan.org_id, chan.agent.id, modo="desligado")
    assert chan.turn(turn_body("Oi")).json()["status"] == "agente_desligado"


def test_turn_unreadable_control_is_a_503_and_sends_nothing(chan):
    chan.seed_agent()
    _lista(chan, DONO)
    chan.controles.falha = RuntimeError("db down")
    resp = chan.turn(turn_body("Oi"))
    assert resp.status_code == 503
    assert not [c for c in chan.provider.calls if c["method"] == "chat_with_tools"]


def test_the_list_is_read_live_on_every_turn(chan):
    chan.seed_agent()
    assert chan.turn(turn_body("Oi", ids=["l1"])).json()["status"] == "respondido"
    _lista(chan, AMIGO)
    assert chan.turn(turn_body("Oi de novo", ids=["l2"])).json()["status"] == "restrito_avaliacao"
    _lista(chan)  # emptied: everybody again
    assert chan.turn(turn_body("Voltei", ids=["l3"])).json()["status"] == "respondido"


# ── the reads (status for the consumer's send guard, controle) ──────────────


def test_status_and_channel_controle_expose_the_on_off_and_the_list(chan):
    from app.dependencies import SCOPE_CHANNEL_STATUS

    chan.seed_agent()
    _lista(chan, DONO, AMIGO)
    chan.controles.set(chan.org_id, chan.agent.id, modo="ligado")
    with chan.as_token(SCOPE_CHANNEL_STATUS):
        st = chan.request("GET", "/api/channels/agents/julia/status").json()
        ctl = chan.request("GET", "/api/channels/agents/julia/controle").json()
    assert st["modo"] == "ligado" and st["contatos_permitidos"] == [DONO, AMIGO]
    assert ctl["modo"] == "ligado" and ctl["contatos_permitidos"] == [DONO, AMIGO]


def test_a_fresh_agent_is_off_with_an_empty_list():
    r = FakeAgentControleStore().get(uuid4(), uuid4())
    assert r.modo == "desligado" and r.contatos_permitidos == ()


def test_status_with_an_unreadable_control_fails_closed(chan):
    from app.dependencies import SCOPE_CHANNEL_STATUS

    chan.seed_agent()
    chan.controles.falha = RuntimeError("db down")
    with chan.as_token(SCOPE_CHANNEL_STATUS):
        resp = chan.request("GET", "/api/channels/agents/julia/status")
    assert resp.status_code == 503


# ── the Studio PUT ──────────────────────────────────────────────────────────


def test_put_replaces_the_list_normalised_without_mode_preconditions_and_audits_counts(chan):
    chan.seed_agent()
    chan.keys.clear()  # a mode change to ON would be a 409; the same modo must not care
    modo_audits = len(chan.controles.auditoria)
    resp = chan.rt.client.put(CTL, json={"modo": "ligado", "contatos_permitidos": ["+55 (11) 99999-0000", "5511999990000", AMIGO]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["contatos_permitidos"] == [DONO, AMIGO] and resp.json()["modo"] == "ligado"
    assert chan.controles.auditoria_contatos == [(chan.agent.id, DEFAULT_USER_ID, 0, 2)]
    assert len(chan.controles.auditoria) == modo_audits  # no modo audit
    chan.rt.client.put(CTL, json={"modo": "ligado", "contatos_permitidos": [DONO, AMIGO]})
    assert len(chan.controles.auditoria_contatos) == 1  # unchanged -> no new audit row
    resp = chan.rt.client.put(CTL, json={"modo": "ligado", "contatos_permitidos": []})
    assert resp.status_code == 200 and resp.json()["contatos_permitidos"] == []


def test_a_non_admin_member_reads_the_studio_list_masked_the_channel_read_whole(chan, monkeypatch):
    import app.routers.channel_threads_router as r

    chan.seed_agent()
    _lista(chan, DONO)
    monkeypatch.setattr(r, "_e_admin_da_org", lambda ctx, request: False)
    masked = chan.rt.client.get(CTL).json()["contatos_permitidos"]
    assert masked == ["+55 11 *****-0000"] and DONO not in str(masked)
    monkeypatch.setattr(r, "_e_admin_da_org", lambda ctx, request: True)
    assert chan.rt.client.get(CTL).json()["contatos_permitidos"] == [DONO]


def test_put_without_the_field_keeps_the_list(chan):
    chan.seed_agent()
    _lista(chan, DONO)
    assert chan.rt.client.put(CTL, json={"modo": "desligado", "dreno_inatividade_dias": 9}).json()["contatos_permitidos"] == [DONO]


def test_put_refuses_a_non_phone_and_applies_nothing(chan):
    chan.seed_agent()
    _lista(chan, DONO)
    resp = chan.rt.client.put(CTL, json={"modo": "desligado", "contatos_permitidos": [AMIGO, "abc"]})
    assert resp.status_code == 422
    b = resp.json()
    assert (b.get("code") or (b.get("detail") or {}).get("code")) == "contatos_permitidos_invalido"
    assert chan.controles.get(chan.org_id, chan.agent.id).contatos_permitidos == (DONO,)


# ── migration pin ───────────────────────────────────────────────────────────

SQL = migration_sql(Path(__file__).resolve().parents[2], "contatos_permitidos")


def test_migration_column_writer_and_audit():
    assert "ADD COLUMN IF NOT EXISTS contatos_permitidos TEXT[] NOT NULL DEFAULT '{}'" in SQL
    fn = "set_agent_contatos_permitidos(UUID, UUID, TEXT[], UUID)"
    assert f"REVOKE ALL ON FUNCTION agents.{fn} FROM PUBLIC, anon, authenticated" in SQL
    assert f"GRANT EXECUTE ON FUNCTION agents.{fn} TO service_role" in SQL
    assert "'contatos_permitidos_alterados'" in SQL and "SECURITY DEFINER" in SQL
    assert "n !~ '^\\+[0-9]{8,15}$'" in SQL
    assert "5511" not in SQL  # numbers are never audited
