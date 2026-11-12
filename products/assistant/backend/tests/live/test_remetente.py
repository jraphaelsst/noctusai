"""Owner flag: `ASSISTANT_OWNER_NUMBERS` -> `remetente` on the agents turn. Fakes only."""
from __future__ import annotations

import json

import pytest

from app.live.numeros import eh_dono, numeros_do_dono
from app.live.resposta import ReplyConfig
from tests.live.test_resposta import NUMERO, Ctl, Reg, _build, _msg, run
from app.live import registro as r


def _rep(owner_raw, agents=None):
    ag = agents or Ctl()
    rep, waha, reg = _build(ag)
    rep._cfg = ReplyConfig(enabled=True, agent_key="assistente", owner_numbers=numeros_do_dono(owner_raw))
    return rep, ag, reg


def test_matching_number_is_dono():
    rep, ag, reg = _rep(f"+{NUMERO}")
    assert run(rep, _msg()) == r.ENVIADA
    assert ag.turns[0].remetente == "dono"
    assert reg.eventos[0]["dados"]["remetente"] == "dono"


def test_non_matching_number_is_contato():
    rep, ag, reg = _rep("+5521977776666")
    run(rep, _msg())
    assert ag.turns[0].remetente == "contato" and reg.eventos[0]["dados"]["remetente"] == "contato"


@pytest.mark.parametrize("raw", ["", "  ", ","])
def test_unset_or_empty_means_nobody_is_the_owner(raw):
    rep, ag, _ = _rep(raw)
    run(rep, _msg())
    assert ag.turns[0].remetente == "contato"


def test_unknown_lid_sender_is_never_the_owner():
    rep, ag, _ = _rep(f"+{NUMERO}")
    run(rep, _msg(chat="123456@lid"))
    assert ag.turns[0].remetente == "contato"


@pytest.mark.parametrize("spelling", ["+55 11 98888-7777", "(11) 98888-7777", "5511988887777", "11988887777"])
def test_normalizer_handles_brazilian_spellings(spelling):
    assert eh_dono(NUMERO, numeros_do_dono(spelling))


def test_several_numbers_and_junk_entries():
    donos = numeros_do_dono("lixo, +5521977776666 ,+55 11 98888-7777")
    assert eh_dono(NUMERO, donos) and eh_dono("5521977776666", donos) and not eh_dono("5531900000000", donos)


def test_owner_number_never_reaches_the_event_row():
    rep, _, reg = _rep(f"+{NUMERO}")
    run(rep, _msg())
    assert NUMERO not in json.dumps(reg.eventos, default=str)
