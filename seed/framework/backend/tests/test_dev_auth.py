"""Tests for `noctusai_seed.dev_auth`.

The dev-auth path is a PARALLEL implementation, double-gated, hard-off
in production. These tests pin: (a) the factory refuses to mint a
bypass when the gate is off (no silent backdoor), (b) the synthesized
identity matches the shape downstream auth resolvers read, (c) the
gate semantics (flag AND debug).
"""

from __future__ import annotations

import asyncio

import pytest

from noctusai_seed.dev_auth import (
    DEV_TOKEN,
    DEV_USER_EMAIL,
    dev_auth_enabled,
    make_dev_auth_get_current_user,
)


class _Settings:
    def __init__(self, *, seed_dev_auth=False, debug=False, **extra):
        self.seed_dev_auth = seed_dev_auth
        self.debug = debug
        for k, v in extra.items():
            setattr(self, k, v)


class TestDevAuthEnabled:
    def test_off_by_default(self):
        assert dev_auth_enabled(_Settings()) is False

    def test_flag_alone_not_enough(self):
        assert dev_auth_enabled(_Settings(seed_dev_auth=True, debug=False)) is False

    def test_debug_alone_not_enough(self):
        assert dev_auth_enabled(_Settings(seed_dev_auth=False, debug=True)) is False

    def test_both_gates_required(self):
        assert dev_auth_enabled(_Settings(seed_dev_auth=True, debug=True)) is True

    def test_missing_attrs_default_off(self):
        assert dev_auth_enabled(object()) is False


class TestMakeDevAuthGetCurrentUser:
    def test_refuses_when_gate_off(self):
        # No silent backdoor — fail loud rather than mint a bypass.
        with pytest.raises(RuntimeError, match="dev-auth is OFF"):
            make_dev_auth_get_current_user(_Settings(seed_dev_auth=True, debug=False))

    def test_returns_user_token_tuple_compatible_shape(self):
        settings = _Settings(seed_dev_auth=True, debug=True)
        dep = make_dev_auth_get_current_user(settings)
        user, token = asyncio.get_event_loop().run_until_complete(dep(None))
        assert token == DEV_TOKEN
        assert user.email == DEV_USER_EMAIL
        # Shape downstream resolvers read (resolve_sso_role / get_org_id):
        assert user.user_metadata["org_id"]
        assert user.user_metadata["role"] == "owner"
        assert user.id

    def test_explicit_ids_override_config(self):
        settings = _Settings(seed_dev_auth=True, debug=True)
        dep = make_dev_auth_get_current_user(
            settings, user_id="u-123", org_id="o-456"
        )
        user, _ = asyncio.get_event_loop().run_until_complete(dep(None))
        assert user.id == "u-123"
        assert user.user_metadata["org_id"] == "o-456"

    def test_config_ids_used_when_present(self):
        settings = _Settings(
            seed_dev_auth=True,
            debug=True,
            local_dev_user_id="cfg-user",
            local_dev_org_id="cfg-org",
        )
        dep = make_dev_auth_get_current_user(settings)
        user, _ = asyncio.get_event_loop().run_until_complete(dep(None))
        assert user.id == "cfg-user"
        assert user.user_metadata["org_id"] == "cfg-org"

    def test_malformed_authorization_rejected(self):
        from fastapi import HTTPException

        settings = _Settings(seed_dev_auth=True, debug=True)
        dep = make_dev_auth_get_current_user(settings)
        with pytest.raises(HTTPException) as exc:
            asyncio.get_event_loop().run_until_complete(dep("NotBearer xyz"))
        assert exc.value.status_code == 401

    def test_no_header_accepted(self):
        settings = _Settings(seed_dev_auth=True, debug=True)
        dep = make_dev_auth_get_current_user(settings)
        user, token = asyncio.get_event_loop().run_until_complete(dep(None))
        assert token == DEV_TOKEN
