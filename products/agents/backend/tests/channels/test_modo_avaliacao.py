"""Evaluation mode (Julia v3 contract section 12.12): decision rows, phone normalisation, the turn endpoint (no
thread for an outsider), the status endpoint (flag, never the numbers), the controle PUT/GET and its audit."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.channels.controles import (
    numeros_de_avaliacao,
    STATUS_AGENTE_DESLIGADO,
    STATUS_AGENTE_DESLIGADO_PLATAFORMA,
    STATUS_CONTROLE_INDISPONIVEL,
    STATUS_NORMAL,
    STATUS_RESTRITO_AVALIACAO,
    ParticipanteView,
    ThreadView,
    decidir,
)
from app.stores.usuarios_avaliacao import FakeUsuariosAvaliacao
from app.stores.agent_controles import FakeAgentControleStore, normalizar_e164, normalizar_usuarios
from tests.channels.conftest import chan, turn_body  # noqa: F401 — fixture
from tests.routers.conftest import DEFAULT_USER_ID

AGORA = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
THREAD = ThreadView(ultima_mensagem_lead_em=AGORA)
PART = ParticipanteView(estado="ativo", entrou_em=AGORA)
LISTA = ("+5511999990000", "+5511888880000")
DONO = "+55 (11) 99999-0000"
FORA = "+5511777770000"


def _d(modo="ligado", thread=None, part=None, gatilho="mensagem", **kw):
    kw.setdefault("modo_avaliacao", True)
    kw.setdefault("avaliacao_numeros", LISTA)
    return decidir(modo, thread, part, gatilho, AGORA, **kw)


# ── phone normalisation ─────────────────────────────────────────────────────


@pytest.mark.parametrize("bruto", ["+55 11 99999-0000", "5511999990000", "+5511999990000", "(55) 11 99999 0000", DONO])
def test_formatted_and_bare_numbers_normalise_to_the_same_e164(bruto):
    assert normalizar_e164(bruto) == "+5511999990000"


@pytest.mark.parametrize("bruto", [None, "", "abc", "123", "1" * 16])
def test_an_implausible_number_does_not_normalise(bruto):
    assert normalizar_e164(bruto) is None


def test_the_allow_list_of_users_is_deduplicated_and_validated():
    u = uuid4()
    assert normalizar_usuarios([u, str(u)]) == (u,)
    with pytest.raises(ValueError):
        normalizar_usuarios(["nope"])
    with pytest.raises(ValueError):
        normalizar_usuarios([uuid4() for _ in range(21)])


# ── decidir ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("gatilho", ["mensagem", "reengajamento"])
@pytest.mark.parametrize("modo", ["ligado", "drenando"])
@pytest.mark.parametrize("thread", [None, THREAD])
def test_an_outsider_is_refused_in_every_mode_and_trigger_without_creating_anything(gatilho, modo, thread):
    d = _d(modo, thread, PART if thread else None, gatilho, telefone_e164=FORA)
    assert d.status == STATUS_RESTRITO_AVALIACAO
    assert (d.executar_llm, d.criar_thread, d.transicao, d.http_status) == (False, False, None, 200)
    assert d.persistir_inbound is False  # owner 2026-11-05: a blocked message is never stored, not even on an existing thread


@pytest.mark.parametrize("telefone", [None, "", "sem numero"])
def test_a_missing_or_invalid_phone_is_refused(telefone):
    assert _d(telefone_e164=telefone).status == STATUS_RESTRITO_AVALIACAO


def test_an_empty_allow_list_refuses_everybody():
    assert _d(avaliacao_numeros=(), telefone_e164=DONO).status == STATUS_RESTRITO_AVALIACAO


@pytest.mark.parametrize("telefone", [DONO, "5511999990000", "+5511999990000", "+55 11 88888-0000"])
def test_an_allow_listed_number_gets_a_normal_turn_in_any_format(telefone):
    d = _d(telefone_e164=telefone)  # no thread: the lead opens one as usual
    assert (d.status, d.criar_thread, d.executar_llm) == (STATUS_NORMAL, True, True)
    d = _d(thread=THREAD, part=PART, telefone_e164=telefone)
    assert (d.status, d.executar_llm) == (STATUS_NORMAL, True)


def test_an_allow_listed_re_engagement_runs():
    assert _d(thread=THREAD, part=PART, gatilho="reengajamento", telefone_e164=DONO).status == STATUS_NORMAL


def test_the_allow_list_is_normalised_on_the_stored_side_too():
    assert _d(avaliacao_numeros=("55 11 99999 0000",), telefone_e164=DONO).status == STATUS_NORMAL


def test_mode_off_leaves_everyone_open():
    d = _d(modo_avaliacao=False, telefone_e164=FORA)
    assert (d.status, d.criar_thread) == (STATUS_NORMAL, True)


def test_precedence_kill_then_org_off_then_evaluation():
    assert _d(desligado_plataforma=True, telefone_e164=FORA).status == STATUS_AGENTE_DESLIGADO_PLATAFORMA
    assert _d("desligado", telefone_e164=FORA).status == STATUS_AGENTE_DESLIGADO


@pytest.mark.parametrize("gatilho", ["mensagem", "reengajamento"])
def test_an_unreadable_flag_is_a_503(gatilho):
    d = _d(thread=THREAD, part=PART, gatilho=gatilho, modo_avaliacao=None, telefone_e164=DONO)
    assert (d.status, d.http_status, d.persistir_inbound, d.executar_llm) == (STATUS_CONTROLE_INDISPONIVEL, 503, False, False)


# ── resolving the allow-list from noc users (per turn, fail closed) ─────────


def _fake(*usuarios):
    f = FakeUsuariosAvaliacao()
    for org, u, tel in usuarios:
        f.add(org, u, nome="Fulano", telefone=tel)
    return f


def test_phones_come_from_noc_users_of_the_org_only():
    org, outra = uuid4(), uuid4()
    a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()
    f = _fake((org, a, "+55 11 99999-0000"), (org, b, None), (outra, c, "+5511666660000"))
    assert numeros_de_avaliacao(org, [a, b, c, d], f) == ("+5511999990000",)


def test_an_empty_list_reads_nothing_and_allows_nobody():
    f = _fake()
    assert numeros_de_avaliacao(uuid4(), [], f) == () and f.leituras == 0


def test_an_unreadable_user_table_allows_nobody(caplog):
    f = _fake()
    f.falha = RuntimeError("core down")
    assert numeros_de_avaliacao(uuid4(), [uuid4()], f) == ()
    assert "avaliacao_telefones_ilegiveis" in caplog.text


def test_a_missing_resolver_allows_nobody():
    assert numeros_de_avaliacao(uuid4(), [uuid4()], None) == ()


# ── the turn endpoint ───────────────────────────────────────────────────────

CTL = "/api/studio/agents/julia/controle"
TEL_DONO = "+5511999990000"  # the default contact of turn_body


def _dono(chan, telefone=TEL_DONO):
    return chan.usuarios.add(chan.org_id, uuid4(), nome="Dono", telefone=telefone)


def _avaliacao(chan, *usuarios):
    chan.controles.set_avaliacao(chan.org_id, chan.agent.id, modo_avaliacao=True, usuarios=list(usuarios))


def test_an_outsider_turn_gets_no_reply_and_no_thread(chan):
    chan.seed_agent()
    _avaliacao(chan, _dono(chan, "+5511111110000"))
    resp = chan.turn(turn_body("Oi"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "restrito_avaliacao" and resp.json()["thread_id"] is None
    assert resp.json()["reply"]["partes"] == []
    assert not [c for c in chan.provider.calls if c["method"] == "chat_with_tools"]


def test_a_contact_without_a_phone_is_refused(chan):
    chan.seed_agent()
    _avaliacao(chan, _dono(chan))
    assert chan.turn(turn_body("Oi", contact={"display_name": "Sem telefone"})).json()["status"] == "restrito_avaliacao"


def test_the_users_phone_in_noc_is_the_allow_list_in_any_format(chan):
    chan.seed_agent()
    _avaliacao(chan, _dono(chan, "55 (11) 99999-0000"))
    assert chan.turn(turn_body("Oi")).json()["status"] == "respondido"


def test_a_phone_edited_in_noc_applies_on_the_next_message(chan):
    chan.seed_agent()
    uid = _dono(chan)
    _avaliacao(chan, uid)
    assert chan.turn(turn_body("Oi", ids=["p1"])).json()["status"] == "respondido"
    chan.usuarios.add(chan.org_id, uid, nome="Dono", telefone="+5511222220000")  # edited in noc
    assert chan.turn(turn_body("Oi de novo", ids=["p2"])).json()["status"] == "restrito_avaliacao"


def test_an_unreadable_user_table_replies_to_nobody_not_to_everybody(chan):
    chan.seed_agent()
    _avaliacao(chan, _dono(chan))
    chan.usuarios.falha = RuntimeError("core down")
    resp = chan.turn(turn_body("Oi"))
    assert resp.status_code == 200 and resp.json()["status"] == "restrito_avaliacao"
    assert not [c for c in chan.provider.calls if c["method"] == "chat_with_tools"]


def test_a_listed_user_of_another_org_does_not_open_the_gate(chan):
    chan.seed_agent()
    estranho = chan.usuarios.add(uuid4(), uuid4(), nome="Outra org", telefone=TEL_DONO)
    _avaliacao(chan, estranho)
    assert chan.turn(turn_body("Oi")).json()["status"] == "restrito_avaliacao"


def test_the_lookup_runs_once_per_turn_and_never_when_the_mode_is_off(chan):
    chan.seed_agent()
    uid = _dono(chan)
    chan.controles.set_avaliacao(chan.org_id, chan.agent.id, modo_avaliacao=False, usuarios=[uid])
    chan.turn(turn_body("Oi", ids=["q0"]))
    assert chan.usuarios.leituras == 0
    _avaliacao(chan, uid)
    chan.turn(turn_body("Oi", ids=["q1"]))
    assert chan.usuarios.leituras == 1


def test_an_existing_thread_of_an_outsider_stores_nothing_and_it_never_surfaces_when_testing_ends(chan):
    chan.seed_agent()
    assert chan.turn(turn_body("Oi", ids=["a1"])).json()["status"] == "respondido"
    _avaliacao(chan, _dono(chan, "+5511111110000"))
    calls = len(chan.provider.calls)
    resp = chan.turn(turn_body("Voltei com segredo", ids=["a2"]))
    assert resp.json()["status"] == "restrito_avaliacao"
    assert len(chan.provider.calls) == calls  # no LLM, no tool, no memory work
    tid = UUID(resp.json()["thread_id"])
    rows = chan.rt.stores.messages.list(chan.org_id, tid, limite=50)
    assert not any("segredo" in (m.texto or "") for m in rows)
    chan.controles.set_avaliacao(chan.org_id, chan.agent.id, modo_avaliacao=False)   # testing ends
    assert chan.turn(turn_body("Quero visitar", ids=["a3"])).json()["status"] == "respondido"
    assert not any("segredo" in (m.texto or "") for m in chan.rt.stores.messages.list(chan.org_id, tid, limite=50))
    assert not any("segredo" in str(c) for c in chan.provider.calls), "never in the model context"



def test_the_mode_off_again_opens_the_agent(chan):
    chan.seed_agent()
    _avaliacao(chan, _dono(chan, "+5511111110000"))
    chan.controles.set_avaliacao(chan.org_id, chan.agent.id, modo_avaliacao=False)
    assert chan.turn(turn_body("Oi")).json()["status"] == "respondido"


def test_the_mode_is_a_live_state_stranger_answered_when_off_refused_again_when_flipped_on(chan):
    """Owner 2026-11-05: testing mode is read on every turn, never latched."""
    chan.seed_agent()
    dono = _dono(chan, "+5511111110000")
    _avaliacao(chan, dono)
    assert chan.turn(turn_body("Oi")).json()["status"] == "restrito_avaliacao"
    chan.controles.set_avaliacao(chan.org_id, chan.agent.id, modo_avaliacao=False)
    assert chan.turn(turn_body("Tem apartamento?")).json()["status"] == "respondido"
    chan.controles.set_avaliacao(chan.org_id, chan.agent.id, modo_avaliacao=True)
    assert chan.turn(turn_body("E de dois quartos?")).json()["status"] == "restrito_avaliacao"


def test_status_reports_the_flag_and_the_controle_read_the_user_ids_never_numbers(chan):
    from app.dependencies import SCOPE_CHANNEL_STATUS

    chan.seed_agent()
    _avaliacao(chan, _dono(chan))
    with chan.as_token(SCOPE_CHANNEL_STATUS):
        body = chan.request("GET", "/api/channels/agents/julia/status").json()
        ctl = chan.request("GET", "/api/channels/agents/julia/controle").json()
    assert body["modo_avaliacao"] is True and not [k for k in body if k.startswith("avaliacao")]
    # the controle read hands SW the evaluation USER IDS (so SW can let a listed member through its staff filter) -- no phone, no name
    assert ctl["modo_avaliacao"] is True and ctl["avaliacao_usuarios"] == [str(u) for u in chan.controles.get(chan.org_id, chan.agent.id).avaliacao_usuarios]
    assert ctl["avaliacao_usuarios"] and ctl["avaliacao_resolvidos"] == []
    assert "5511" not in str(ctl)


# ── the Studio controle ─────────────────────────────────────────────────────


def test_controle_defaults_off_with_an_empty_list(chan):
    chan.seed_agent()
    body = chan.rt.client.get(CTL).json()
    assert body["modo_avaliacao"] is False and body["avaliacao_usuarios"] == []


def test_only_the_evaluation_fields_change_without_mode_preconditions_and_are_audited(chan):
    chan.seed_agent()
    uid = _dono(chan)
    chan.keys.clear()  # a mode change to ON would be a 409; the same modo must not care
    antes = len(chan.controles.auditoria)
    resp = chan.rt.client.put(CTL, json={"modo": "ligado", "modo_avaliacao": True, "avaliacao_usuarios": [str(uid), str(uid)]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["modo_avaliacao"] is True and resp.json()["avaliacao_usuarios"] == [str(uid)]
    assert len(chan.controles.auditoria) == antes  # no modo audit
    assert chan.controles.auditoria_avaliacao == [(chan.agent.id, DEFAULT_USER_ID, (False, 0), (True, 1))]
    chan.rt.client.put(CTL, json={"modo": "ligado", "modo_avaliacao": True})
    assert len(chan.controles.auditoria_avaliacao) == 1  # unchanged -> no new audit row
    resp = chan.rt.client.put(CTL, json={"modo": "ligado", "modo_avaliacao": False})
    assert resp.status_code == 200 and resp.json()["modo_avaliacao"] is False


def _code(resp):
    b = resp.json()
    return b.get("code") or (b.get("detail") or {}).get("code")


def test_turning_it_on_needs_a_listed_user_with_a_phone_naming_those_without(chan):
    chan.seed_agent()
    sem = chan.usuarios.add(chan.org_id, uuid4(), nome="Maria Sem Telefone", telefone=None)
    resp = chan.rt.client.put(CTL, json={"modo": "ligado", "modo_avaliacao": True, "avaliacao_usuarios": [str(sem)]})
    assert resp.status_code == 422 and _code(resp) == "avaliacao_sem_telefone"
    assert "Maria Sem Telefone" in resp.text
    assert chan.controles.get(chan.org_id, chan.agent.id).modo_avaliacao is False  # nothing applied
    # an empty list cannot be turned on either
    resp = chan.rt.client.put(CTL, json={"modo": "ligado", "modo_avaliacao": True})
    assert resp.status_code == 422 and _code(resp) == "avaliacao_sem_telefone"
    # one with a phone is enough, even beside one without
    ok = _dono(chan)
    resp = chan.rt.client.put(CTL, json={"modo": "ligado", "modo_avaliacao": True, "avaliacao_usuarios": [str(sem), str(ok)]})
    assert resp.status_code == 200


def test_emptying_the_list_while_on_is_refused_and_the_mode_stays_consistent(chan):
    chan.seed_agent()
    _avaliacao(chan, _dono(chan))
    resp = chan.rt.client.put(CTL, json={"modo": "ligado", "avaliacao_usuarios": []})
    assert resp.status_code == 422 and _code(resp) == "avaliacao_sem_telefone"


def test_a_user_of_another_org_or_unknown_is_refused(chan):
    chan.seed_agent()
    estranho = chan.usuarios.add(uuid4(), uuid4(), nome="Outra org", telefone=TEL_DONO)
    for uid in (estranho, uuid4()):
        resp = chan.rt.client.put(CTL, json={"modo": "ligado", "avaliacao_usuarios": [str(uid)]})
        assert resp.status_code == 422 and _code(resp) == "avaliacao_usuario_fora_da_org"


@pytest.mark.parametrize("lista", [["nope"], [str(uuid4()) for _ in range(21)]])
def test_a_malformed_list_is_422_and_nothing_applies(chan, lista):
    chan.seed_agent()
    resp = chan.rt.client.put(CTL, json={"modo": "desligado", "avaliacao_usuarios": lista})
    assert resp.status_code == 422
    assert chan.controles.get(chan.org_id, chan.agent.id).modo == "ligado"  # the mode change did not half-apply


def test_an_unreadable_user_table_on_write_is_503_and_nothing_applies(chan):
    chan.seed_agent()
    uid = _dono(chan)
    chan.usuarios.falha = RuntimeError("core down")
    resp = chan.rt.client.put(CTL, json={"modo": "ligado", "modo_avaliacao": True, "avaliacao_usuarios": [str(uid)]})
    assert resp.status_code == 503 and _code(resp) == "controle_indisponivel"
    assert chan.controles.get(chan.org_id, chan.agent.id).modo_avaliacao is False


def test_a_non_admin_cannot_write_it(chan):
    chan.seed_agent()
    chan.rt.client.mock_supabase.set_table_data("noctus_users", [{
        "id": str(DEFAULT_USER_ID), "org_id": str(chan.org_id), "role": "user", "org_role": "member"}])
    assert chan.rt.client.put(CTL, json={"modo": "ligado", "modo_avaliacao": True}).status_code == 403


def test_the_fake_store_audits_counts_only():
    s = FakeAgentControleStore()
    org, ag = uuid4(), uuid4()
    s.set_avaliacao(org, ag, modo_avaliacao=True, usuarios=[uuid4()])
    assert s.auditoria_avaliacao[0][2:] == ((False, 0), (True, 1))


# ── avaliacao_resolvidos: the users as noc knows them (phone masked for non-admins) ──


def _resolvidos_body(chan, *, admin: bool):
    papel = "owner" if admin else "member"
    chan.rt.client.mock_supabase.set_table_data("noctus_users", [{
        "id": str(DEFAULT_USER_ID), "org_id": str(chan.org_id), "role": "user", "org_role": papel}])
    return chan.rt.client.get(CTL)


def test_mask_keeps_country_area_and_last_four_only():
    from app.routers.channel_threads_router import mascarar_telefone

    assert mascarar_telefone("+5511999993365") == "+55 11 *****-3365"
    assert mascarar_telefone(None) is None and mascarar_telefone("") is None
    assert mascarar_telefone("123") == "*****"


def test_the_controle_get_resolves_users_full_phone_to_admins_masked_to_members(chan):
    chan.seed_agent()
    uid = chan.usuarios.add(chan.org_id, uuid4(), nome="Dono", telefone="+5511999993365")
    semtel = chan.usuarios.add(chan.org_id, uuid4(), nome="Maria", telefone=None)
    _avaliacao(chan, uid, semtel)
    adm = _resolvidos_body(chan, admin=True)
    assert adm.status_code == 200, adm.text
    assert adm.json()["avaliacao_usuarios"] == [str(uid), str(semtel)] and adm.json()["avaliacao_resolucao_erro"] is False
    assert adm.json()["avaliacao_resolvidos"] == [
        {"usuario_id": str(uid), "nome": "Dono", "telefone": "+5511999993365"},
        {"usuario_id": str(semtel), "nome": "Maria", "telefone": None}]
    mem = _resolvidos_body(chan, admin=False)
    assert mem.status_code == 200
    assert mem.json()["avaliacao_usuarios"] == [str(uid), str(semtel)]  # ids stay readable
    assert mem.json()["avaliacao_resolvidos"][0]["telefone"] == "+55 11 *****-3365"
    assert "+5511999993365" not in mem.text


def test_a_failed_lookup_still_renders_with_null_name_and_phone_and_the_error_flag(chan):
    chan.seed_agent()
    uid = _dono(chan)
    _avaliacao(chan, uid)
    chan.usuarios.falha = RuntimeError("core down")
    resp = _resolvidos_body(chan, admin=True)
    assert resp.status_code == 200
    body = resp.json()
    assert body["avaliacao_resolucao_erro"] is True
    assert body["avaliacao_resolvidos"] == [{"usuario_id": str(uid), "nome": None, "telefone": None}]


def test_the_put_response_carries_the_resolved_users_with_the_full_phone(chan):
    chan.seed_agent()
    uid = _dono(chan)
    resp = chan.rt.client.put(CTL, json={"modo": "ligado", "modo_avaliacao": True, "avaliacao_usuarios": [str(uid)]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["avaliacao_resolvidos"] == [{"usuario_id": str(uid), "nome": "Dono", "telefone": TEL_DONO}]


def test_no_users_means_no_lookup_and_no_error(chan):
    chan.seed_agent()
    body = chan.rt.client.get(CTL).json()
    assert (body["avaliacao_resolvidos"], body["avaliacao_resolucao_erro"], chan.usuarios.leituras) == ([], False, 0)
