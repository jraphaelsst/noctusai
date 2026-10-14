"""B3 ctx-shaped wrappers: admin is decided in the SELECTED org (tuple or AuthContext), fail closed."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from noctusai_lib.api.auth.session import (
    is_org_admin_for,
    require_org_admin_for,
    resolve_org_role_for,
)
from noctusai_lib.testing import MockSupabaseClient

HOME, OTHER = "org-home", "org-b"


def _core(role="owner"):
    sb = MockSupabaseClient()
    sb.set_table_data("noctus_users", [{"id": "u1", "org_id": HOME, "org_role": role, "role": "user"}])
    return sb


def _tuple(org):
    return (SimpleNamespace(id="u1"), "tok", org)


def test_home_owner_is_admin_in_home_org():
    assert is_org_admin_for(_core(), _tuple(HOME)) is True
    require_org_admin_for(_core(), _tuple(HOME), None, "Teste")
    assert resolve_org_role_for(_core(), _tuple(HOME)) == "owner"


def test_home_owner_member_in_selected_org_is_403():
    core = _core("owner")
    assert is_org_admin_for(core, _tuple(OTHER)) is False
    assert resolve_org_role_for(core, _tuple(OTHER)) is None
    with pytest.raises(HTTPException) as e:
        require_org_admin_for(core, _tuple(OTHER), None, "Teste")
    assert e.value.status_code == 403


def test_plain_member_403_and_missing_org_fails_closed():
    with pytest.raises(HTTPException) as e:
        require_org_admin_for(_core("member"), _tuple(HOME), None, "Teste")
    assert e.value.status_code == 403
    assert is_org_admin_for(_core(), (SimpleNamespace(id="u1"), "tok", None)) is False


def test_auth_context_shape():
    ctx = SimpleNamespace(user_id="u1", org_id=OTHER, raw_token="tok")
    assert is_org_admin_for(_core(), ctx) is False
    assert is_org_admin_for(_core(), SimpleNamespace(user_id="u1", org_id=HOME, raw_token="tok")) is True


def test_real_auth_context_namedtuple_shape():
    from uuid import uuid4

    from noctusai_lib.api.auth.session import AuthContext

    def ctx(org):
        return AuthContext(org_id=org, caller_kind="user", user_id="u1", scopes=[], raw_token="tok", api_token_id=None)

    assert is_org_admin_for(_core(), ctx(HOME)) is True
    assert is_org_admin_for(_core(), ctx(OTHER)) is False
    assert is_org_admin_for(_core(), ctx(uuid4())) is False
