"""Org picker: platform staff acting in a customer org are judged in THAT org by the
community back-office gate (`_perfil_of` -> the ONE effective-org resolver); everyone
else, and staff without a valid selection, keep the home profile. Fakes only."""
import base64
import json
from types import SimpleNamespace

import pytest

from noctusai_lib.api.auth.org_selection import FakeOrgSelectionStore
from noctusai_lib.domain.licensing import (
    FakeLicenseChecker,
    configure_license_gate,
    get_license_gate,
)

HOME = "00000000-0000-0000-0000-00000000000a"
TARGET = "00000000-0000-0000-0000-00000000000b"
STAFF = "aaaaaaaa-0000-0000-0000-000000000001"
SID = "11111111-1111-1111-1111-111111111111"


def _jwt(sub, aal="aal2"):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'sub': sub, 'aal': aal, 'session_id': SID})}.s"


@pytest.fixture
def picker(client):
    saved = get_license_gate()
    sb = client.mock_supabase
    sb.set_table_data("noctus_users", [
        {"id": STAFF, "org_id": HOME, "org_role": "owner", "role": "admin"},
    ])
    sb.set_table_data("organizations", [{"id": HOME, "nome": "NoctusAI", "is_platform": True}])
    store = FakeOrgSelectionStore(
        ready={"community"}, staff={STAFF}, licensed={(TARGET, "community")}, home_orgs={STAFF: HOME},
    )
    configure_license_gate(
        "community", FakeLicenseChecker(allow_all=False, licensed={(TARGET, "community")}),
        selection_store=store, get_core_client=lambda: sb,
    )
    yield store
    if saved is None:
        configure_license_gate(None)
    else:
        configure_license_gate(
            saved.product_slug, saved.checker, exempt=saved.exempt,
            get_core_client=saved.get_core_client,
            selection_store=saved.selection_store, db_schema=saved.db_schema,
        )


def test_staff_acting_is_judged_as_owner_of_the_target_org(picker):
    from app.dependencies import _perfil_of

    picker.set(STAFF, "community", TARGET, SID)
    perfil = _perfil_of(SimpleNamespace(id=STAFF), _jwt(STAFF))
    assert (perfil["org_id"], perfil["org_role"], perfil["role"]) == (TARGET, "owner", "admin")


def test_without_a_token_or_aal2_or_selection_the_home_profile_stays(picker):
    from app.dependencies import _perfil_of

    user = SimpleNamespace(id=STAFF)
    assert _perfil_of(user)["org_id"] == HOME                       # no token (imperative call)
    assert _perfil_of(user, _jwt(STAFF))["org_id"] == HOME           # no selection yet
    picker.set(STAFF, "community", TARGET, SID)
    assert _perfil_of(user, _jwt(STAFF, aal="aal1"))["org_id"] == HOME
