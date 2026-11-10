"""owner_recipients_service — normalization, duplicate guard, actor stamping, owner-line status."""
from __future__ import annotations

import pytest

from app.services import owner_recipients_service as svc
from noctusai_lib.testing import MockSupabaseClient


def _db():
    return MockSupabaseClient()


def test_add_stamps_actor_and_normalizes():
    db = _db()
    item = svc.add_recipient(db, numero="11999999999", nome="  ", user_id="u1")
    assert item["numero"] == "+5511999999999" and item["nome"] is None
    assert db.table(svc.TABLE).select("*").execute().data[0]["alterado_por"] == "u1"


def test_invalid_and_duplicate():
    db = _db()
    with pytest.raises(svc.InvalidNumber):
        svc.add_recipient(db, numero="nope", nome=None, user_id="u")
    svc.add_recipient(db, numero="+5511999999999", nome=None, user_id="u")
    with pytest.raises(svc.DuplicateNumber):
        svc.add_recipient(db, numero="+55 11 99999-9999", nome=None, user_id="u")


def test_unique_violation_race_maps_to_duplicate():
    class Boom:
        def table(self, _):
            return self
        def select(self, *_a):
            return self
        def eq(self, *_a):
            return self
        def insert(self, *_a):
            return self
        def execute(self):
            if getattr(self, "_ins", False):
                raise RuntimeError('duplicate key value violates unique constraint "x"')
            self._ins = True
            class R: data = []
            return R()
    with pytest.raises(svc.DuplicateNumber):
        svc.add_recipient(Boom(), numero="+5511999999999", nome=None, user_id="u")


def test_update_stamps_actor():
    db = _db()
    rid = svc.add_recipient(db, numero="+5511999999999", nome=None, user_id="u1")["id"]
    out = svc.update_recipient(db, recipient_id=rid, patch={"ativo": False}, user_id="u2")
    assert out["ativo"] is False
    assert db.table(svc.TABLE).select("*").execute().data[0]["alterado_por"] == "u2"
    svc.update_recipient(db, recipient_id=rid, patch={"nome": "X"}, user_id="u3")
    assert db.table(svc.TABLE).select("*").execute().data[0]["alterado_por"] == "u3"
    with pytest.raises(svc.RecipientNotFound):
        svc.update_recipient(db, recipient_id="nope", patch={"ativo": True}, user_id="u3")


def test_numero_is_never_in_an_update():
    db = _db()
    rid = svc.add_recipient(db, numero="+5511999999999", nome=None, user_id="u1")["id"]
    svc.update_recipient(db, recipient_id=rid, patch={"numero": "+5511888888888", "ativo": True}, user_id="u1")
    assert db.table(svc.TABLE).select("*").execute().data[0]["numero"] == "+5511999999999"


def test_delete_is_one_rpc_carrying_the_actor():
    db = _db()
    db.set_rpc_data("remover_destinatario_dono", "11111111-1111-1111-1111-111111111111")
    svc.delete_recipient(db, recipient_id="11111111-1111-1111-1111-111111111111", user_id="u3")
    assert db.rpc_calls == [("remover_destinatario_dono",
                             {"p_id": "11111111-1111-1111-1111-111111111111", "p_ator": "u3"})]
    db.set_rpc_data("remover_destinatario_dono", None)
    with pytest.raises(svc.RecipientNotFound):
        svc.delete_recipient(db, recipient_id="11111111-1111-1111-1111-111111111111", user_id="u3")


def test_every_write_requires_an_actor():
    db = _db()
    with pytest.raises(svc.ActorRequired):
        svc.add_recipient(db, numero="+5511999999999", nome=None, user_id=None)
    with pytest.raises(svc.ActorRequired):
        svc.update_recipient(db, recipient_id="x", patch={"ativo": True}, user_id=None)
    with pytest.raises(svc.ActorRequired):
        svc.delete_recipient(db, recipient_id="x", user_id=None)


def test_empty_patch_returns_current():
    db = _db()
    rid = svc.add_recipient(db, numero="+5511999999999", nome="A", user_id="u")["id"]
    assert svc.update_recipient(db, recipient_id=rid, patch={}, user_id="u")["nome"] == "A"


@pytest.mark.parametrize("url,expected", [
    ("", {"configurada": False, "instancia": None}),
    ("https://waha.example.com", {"configurada": True, "instancia": "waha.example.com"}),
    ("waha-noc:3000", {"configurada": True, "instancia": "waha-noc:3000"}),
])
def test_owner_line_status(monkeypatch, url, expected):
    monkeypatch.setenv("NOC_OWNER_LINE_WAHA_URL", url)
    assert svc.owner_line_status() == expected
