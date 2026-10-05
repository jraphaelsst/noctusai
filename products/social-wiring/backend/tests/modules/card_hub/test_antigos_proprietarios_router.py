"""HTTP boundary of the antigos-proprietários routes: strict 401, admin-only
dispensation (403 for a member, 200 for an owner), 422 on a missing motivo."""
from __future__ import annotations

from uuid import uuid4

from noctusai_lib.testing import TEST_USER_ID

from tests.modules.card_hub.conftest import ORG_ID
from tests.modules.card_hub.test_antigos_proprietarios_service import _card

BASE = "/api/clientes/{cid}/certidoes/antigos-proprietarios"


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


def test_every_route_is_a_strict_401_unauthenticated(anon_client):
    cid = uuid4()
    url = BASE.format(cid=cid)
    for method, path, kw in (
        ("get", url, {}),
        ("post", url + "/sincronizar", {"json": {}}),
        ("post", url, {"json": {"nome": "A B", "cpf": "52998224725"}}),
        ("put", url + "/dispensa", {"json": {"motivo": "abc"}}),
        ("delete", url + "/dispensa", {}),
        ("delete", f"{url}/{uuid4()}", {}),
    ):
        assert getattr(anon_client, method)(path, **kw).status_code == 401, (method, path)


def test_a_member_cannot_dispense_but_an_owner_can(client, scoped):
    cid, aid = _card(scoped)
    url = BASE.format(cid=cid) + "/dispensa"
    r = client.put(url, json={"motivo": "Acordo com o cliente"}, headers=_auth())
    assert r.status_code == 403, r.text
    assert not scoped.table("atendimentos").select("*").execute().data[0].get("antigos_dispensados_em")
    r = client.delete(url, headers=_auth())
    assert r.status_code == 403, r.text

    scoped.set_table_data("noctus_users", [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": "owner"}])
    r = client.put(url, json={"motivo": "ab"}, headers=_auth())
    assert r.status_code == 422, r.text
