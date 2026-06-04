"""Tests for `noctusai_lib.auth` — SSO primitives + session cache.

Added in `projects/core-seed-wiring-v2/` Phase 4 (2026-04-23) when
`create_sso_token_factory`, `verify_sso_token_factory`, and `SSOSessionCache`
were promoted from core's local implementation into the shared library.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import datetime

import jwt as _jwt_pkg

from noctusai_lib.api.auth import (
    SSO_AUDIENCE,
    SSO_ISSUER,
    SSOSessionCache,
    _sso_secret,
    create_sso_token_factory,
    make_get_current_user_org,
    make_require_role,
    require_credential_or_422,
    verify_sso_token_factory,
)


@dataclass
class _Settings:
    """Minimal settings surface that the SSO factories need."""
    jwt_secret: str = "test-secret-do-not-use-in-prod"
    jwt_algorithm: str = "HS256"
    sso_token_expiration_minutes: int = 10
    sso_jwt_secret: str = ""  # empty → falls back to jwt_secret (back-compat)


# ---------------------------------------------------------------------------
# create_sso_token_factory + verify_sso_token_factory — round-trip coverage
# ---------------------------------------------------------------------------


class TestSSOTokenFactories:
    def test_mint_and_verify_roundtrip(self):
        s = _Settings()
        mint = create_sso_token_factory(s)
        verify = verify_sso_token_factory(s)

        token = mint(
            user_id="u1",
            org_id="o1",
            product_slug="therapy",
            email="alice@example.com",
        )
        payload = verify(token)

        assert payload["sub"] == "u1"
        assert payload["org_id"] == "o1"
        assert payload["product"] == "therapy"
        assert payload["email"] == "alice@example.com"
        assert payload["role"] == "user"  # default
        assert payload["org_role"] == "member"  # default
        assert payload["type"] == "sso"
        # Hardening assertions: iss/aud must be present after round-trip.
        assert payload["iss"] == SSO_ISSUER
        assert payload["aud"] == SSO_AUDIENCE

    def test_roles_are_carried_into_payload(self):
        s = _Settings()
        mint = create_sso_token_factory(s)
        verify = verify_sso_token_factory(s)

        token = mint(
            user_id="u2", org_id="o2", product_slug="erp",
            email="b@x.com", role="admin", org_role="owner",
        )
        payload = verify(token)
        assert payload["role"] == "admin"
        assert payload["org_role"] == "owner"

    def test_expired_token_rejected(self):
        s = _Settings(sso_token_expiration_minutes=10)
        mint = create_sso_token_factory(s)
        verify = verify_sso_token_factory(s)

        # Mint a token, then jump system clock forward past expiry.
        token = mint(user_id="u", org_id="o", product_slug="p", email="e@x.com")
        with patch("noctusai_lib.api.auth.jwt.decode") as decoded:
            import jwt as _jwt_pkg
            decoded.side_effect = _jwt_pkg.ExpiredSignatureError("token expired")
            with pytest.raises(HTTPException) as exc:
                verify(token)
            assert exc.value.status_code == 401
            assert "expirado" in exc.value.detail

    def test_invalid_signature_rejected(self):
        s_minter = _Settings(jwt_secret="minter-secret")
        s_verifier = _Settings(jwt_secret="different-secret")
        mint = create_sso_token_factory(s_minter)
        verify = verify_sso_token_factory(s_verifier)

        token = mint(user_id="u", org_id="o", product_slug="p", email="e@x.com")
        with pytest.raises(HTTPException) as exc:
            verify(token)
        assert exc.value.status_code == 401
        assert "inválido" in exc.value.detail

    def test_non_sso_token_type_rejected(self):
        s = _Settings()
        # Mint a fully valid token (iss/aud/exp/iat all present) but with
        # type != 'sso' to exercise the explicit type guard AFTER claim
        # validation passes.
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = {
            "sub": "u",
            "type": "session",
            "iss": SSO_ISSUER,
            "aud": SSO_AUDIENCE,
            "exp": now + datetime.timedelta(minutes=5),
            "iat": now,
        }
        token = _jwt_pkg.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
        verify = verify_sso_token_factory(s)
        with pytest.raises(HTTPException) as exc:
            verify(token)
        assert exc.value.status_code == 401
        assert "não é SSO" in exc.value.detail

    def test_different_settings_instances_isolated(self):
        """Two products with different secrets can't verify each other's tokens."""
        s_a = _Settings(jwt_secret="secret-a")
        s_b = _Settings(jwt_secret="secret-b")
        mint_a = create_sso_token_factory(s_a)
        verify_b = verify_sso_token_factory(s_b)
        token = mint_a(user_id="u", org_id="o", product_slug="p", email="e@x.com")
        with pytest.raises(HTTPException):
            verify_b(token)


# ---------------------------------------------------------------------------
# SSO JWT hardening — iss/aud/required-claims/leeway/dedicated-secret
# (security follow-up: 2026-06-04)
# ---------------------------------------------------------------------------


def _mint_raw(payload: dict, secret: str, algorithm: str = "HS256") -> str:
    """Craft a raw JWT directly — bypasses the factory so we can omit claims."""
    return _jwt_pkg.encode(payload, secret, algorithm=algorithm)


def _base_valid_payload(minutes_from_now: float = 5.0) -> dict:
    """Return a minimal valid SSO payload (all required claims present)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "sub": "u1",
        "type": "sso",
        "iss": SSO_ISSUER,
        "aud": SSO_AUDIENCE,
        "exp": now + datetime.timedelta(minutes=minutes_from_now),
        "iat": now,
    }


class TestSSOTokenHardening:
    """iss/aud/required-claims/leeway/dedicated-secret hardening tests.

    All assertions use strict ``== 401`` per the auth-boundary false-green rule.
    """

    # --- missing required claims ---

    def test_missing_iss_rejected(self):
        s = _Settings()
        payload = _base_valid_payload()
        del payload["iss"]
        token = _mint_raw(payload, s.jwt_secret)
        verify = verify_sso_token_factory(s)
        with pytest.raises(HTTPException) as exc:
            verify(token)
        assert exc.value.status_code == 401

    def test_missing_aud_rejected(self):
        s = _Settings()
        payload = _base_valid_payload()
        del payload["aud"]
        token = _mint_raw(payload, s.jwt_secret)
        verify = verify_sso_token_factory(s)
        with pytest.raises(HTTPException) as exc:
            verify(token)
        assert exc.value.status_code == 401

    def test_wrong_iss_rejected(self):
        s = _Settings()
        payload = _base_valid_payload()
        payload["iss"] = "evil-issuer"
        token = _mint_raw(payload, s.jwt_secret)
        verify = verify_sso_token_factory(s)
        with pytest.raises(HTTPException) as exc:
            verify(token)
        assert exc.value.status_code == 401

    def test_wrong_aud_rejected(self):
        s = _Settings()
        payload = _base_valid_payload()
        payload["aud"] = "wrong-audience"
        token = _mint_raw(payload, s.jwt_secret)
        verify = verify_sso_token_factory(s)
        with pytest.raises(HTTPException) as exc:
            verify(token)
        assert exc.value.status_code == 401

    def test_different_secret_rejected(self):
        """A token signed with a different secret → 401 (signature failure)."""
        s_mint = _Settings(jwt_secret="minter-secret")
        s_verify = _Settings(jwt_secret="verifier-different-secret")
        mint = create_sso_token_factory(s_mint)
        verify = verify_sso_token_factory(s_verify)
        token = mint(user_id="u", org_id="o", product_slug="p", email="e@x.com")
        with pytest.raises(HTTPException) as exc:
            verify(token)
        assert exc.value.status_code == 401

    # --- leeway ---

    def test_token_within_leeway_still_verifies(self):
        """A token that expired 5 s ago still verifies within the 10 s leeway."""
        s = _Settings()
        # Craft a token with exp 5 seconds in the past.
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = _base_valid_payload()
        payload["exp"] = now - datetime.timedelta(seconds=5)
        payload["iat"] = now - datetime.timedelta(seconds=10)
        token = _mint_raw(payload, s.jwt_secret)
        verify = verify_sso_token_factory(s)
        # Should NOT raise — 5 s past < 10 s leeway.
        result = verify(token)
        assert result["type"] == "sso"

    def test_token_beyond_leeway_rejected(self):
        """A token that expired 15 s ago is rejected — beyond the 10 s leeway."""
        s = _Settings()
        now = datetime.datetime.now(datetime.timezone.utc)
        payload = _base_valid_payload()
        payload["exp"] = now - datetime.timedelta(seconds=15)
        payload["iat"] = now - datetime.timedelta(seconds=20)
        token = _mint_raw(payload, s.jwt_secret)
        verify = verify_sso_token_factory(s)
        with pytest.raises(HTTPException) as exc:
            verify(token)
        assert exc.value.status_code == 401

    # --- dedicated sso_jwt_secret ---

    def test_dedicated_secret_used_when_set(self):
        """With sso_jwt_secret set, mint+verify use it (round-trip succeeds)."""
        s = _Settings(jwt_secret="product-secret", sso_jwt_secret="dedicated-sso-secret")
        mint = create_sso_token_factory(s)
        verify = verify_sso_token_factory(s)
        token = mint(user_id="u", org_id="o", product_slug="p", email="e@x.com")
        payload = verify(token)
        assert payload["sub"] == "u"
        assert payload["iss"] == SSO_ISSUER
        assert payload["aud"] == SSO_AUDIENCE

    def test_dedicated_secret_decouples_from_jwt_secret(self):
        """Token minted under jwt_secret (no dedicated) does NOT verify when
        dedicated sso_jwt_secret is set at verify time — proves decoupling."""
        s_without_dedicated = _Settings(jwt_secret="shared-secret", sso_jwt_secret="")
        s_with_dedicated = _Settings(jwt_secret="shared-secret", sso_jwt_secret="dedicated-sso-secret")
        mint = create_sso_token_factory(s_without_dedicated)
        verify = verify_sso_token_factory(s_with_dedicated)
        token = mint(user_id="u", org_id="o", product_slug="p", email="e@x.com")
        # Token was signed with jwt_secret; verifier expects dedicated_sso_secret → fail.
        with pytest.raises(HTTPException) as exc:
            verify(token)
        assert exc.value.status_code == 401

    def test_dedicated_secret_reverse_decoupling(self):
        """Token minted with dedicated secret does NOT verify when verifier
        falls back to jwt_secret (dedicated unset at verify)."""
        s_with_dedicated = _Settings(jwt_secret="shared-secret", sso_jwt_secret="dedicated-sso-secret")
        s_without_dedicated = _Settings(jwt_secret="shared-secret", sso_jwt_secret="")
        mint = create_sso_token_factory(s_with_dedicated)
        verify = verify_sso_token_factory(s_without_dedicated)
        token = mint(user_id="u", org_id="o", product_slug="p", email="e@x.com")
        with pytest.raises(HTTPException) as exc:
            verify(token)
        assert exc.value.status_code == 401

    def test_back_compat_empty_sso_jwt_secret_uses_jwt_secret(self):
        """With sso_jwt_secret empty, falls back to jwt_secret — back-compat
        round-trip works identically to the pre-hardening behaviour."""
        s = _Settings(jwt_secret="my-secret", sso_jwt_secret="")
        mint = create_sso_token_factory(s)
        verify = verify_sso_token_factory(s)
        token = mint(user_id="u2", org_id="o2", product_slug="erp", email="b@x.com")
        payload = verify(token)
        assert payload["sub"] == "u2"

    def test_sso_secret_helper_empty_string_fallback(self):
        """_sso_secret returns jwt_secret when sso_jwt_secret is '' or whitespace."""
        s = _Settings(jwt_secret="base", sso_jwt_secret="")
        assert _sso_secret(s) == "base"
        s2 = _Settings(jwt_secret="base", sso_jwt_secret="   ")
        assert _sso_secret(s2) == "base"

    def test_sso_secret_helper_dedicated_returned_when_set(self):
        """_sso_secret returns sso_jwt_secret when it's non-empty."""
        s = _Settings(jwt_secret="base", sso_jwt_secret="dedicated")
        assert _sso_secret(s) == "dedicated"

    def test_sso_secret_helper_no_sso_jwt_secret_attr(self):
        """_sso_secret falls back gracefully when settings has no sso_jwt_secret attr."""
        @dataclass
        class _LegacySettings:
            jwt_secret: str = "legacy-secret"
            jwt_algorithm: str = "HS256"
            sso_token_expiration_minutes: int = 10

        s = _LegacySettings()
        assert _sso_secret(s) == "legacy-secret"


# ---------------------------------------------------------------------------
# SSOSessionCache — TTL + invalidation + per-key locking
# ---------------------------------------------------------------------------


class TestSSOSessionCache:
    def test_get_on_empty_returns_none(self):
        cache = SSOSessionCache()
        assert cache.get("alice@example.com") is None

    def test_set_then_get_returns_data(self):
        cache = SSOSessionCache()
        cache.set("alice@example.com", {"token": "abc", "org": "o1"})
        assert cache.get("alice@example.com") == {"token": "abc", "org": "o1"}

    def test_ttl_expiry_removes_entry(self):
        cache = SSOSessionCache(ttl_seconds=60)
        cache.set("alice@example.com", {"token": "abc"})

        # Capture the pre-set time BEFORE patching, then advance past TTL.
        now = time.monotonic()
        with patch("noctusai_lib.api.auth.time.monotonic", return_value=now + 120):
            assert cache.get("alice@example.com") is None
            # Entry is also purged from the store on get.
            assert "alice@example.com" not in cache._store

    def test_invalidate_removes_returns_true(self):
        cache = SSOSessionCache()
        cache.set("alice@example.com", {"token": "abc"})
        assert cache.invalidate("alice@example.com") is True
        assert cache.get("alice@example.com") is None

    def test_invalidate_missing_returns_false(self):
        cache = SSOSessionCache()
        assert cache.invalidate("nobody@example.com") is False

    def test_clear_flushes_all(self):
        cache = SSOSessionCache()
        cache.set("a@x.com", {"token": "a"})
        cache.set("b@x.com", {"token": "b"})
        cache.get_lock("a@x.com")  # force lock creation
        cache.clear()
        assert cache.get("a@x.com") is None
        assert cache.get("b@x.com") is None
        assert cache._locks == {}

    def test_get_lock_returns_per_email_instance(self):
        cache = SSOSessionCache()
        lock_a1 = cache.get_lock("a@x.com")
        lock_a2 = cache.get_lock("a@x.com")
        lock_b = cache.get_lock("b@x.com")
        assert lock_a1 is lock_a2  # same email → same lock
        assert lock_a1 is not lock_b  # different emails → different locks

    def test_get_lock_serializes_concurrent_acquirers(self):
        """Concurrent `get_lock(email).acquire()` must serialize — only one
        thread inside the critical section at a time. Validates thread safety."""
        cache = SSOSessionCache()
        entered = []
        active = [0]
        max_concurrent = [0]

        def worker():
            lock = cache.get_lock("alice@example.com")
            with lock:
                active[0] += 1
                max_concurrent[0] = max(max_concurrent[0], active[0])
                entered.append(threading.get_ident())
                time.sleep(0.01)  # hold lock briefly
                active[0] -= 1

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(entered) == 10
        assert max_concurrent[0] == 1  # lock enforced serial access

    def test_custom_ttl_is_honored(self):
        cache = SSOSessionCache(ttl_seconds=600)
        cache.set("a@x.com", {"token": "a"})
        # TTL not reached — still present.
        assert cache.get("a@x.com") is not None


# ---------------------------------------------------------------------------
# make_require_role — factory pattern matching make_get_current_user
# ---------------------------------------------------------------------------


@dataclass
class _FakeUser:
    """Minimal user shape — what product's get_user_role receives."""
    id: str
    role: str


class TestMakeRequireRole:
    """Cover the make_require_role factory + the bound require_role dep."""

    def _build(self, *, user_role: str = "platform_admin"):
        """Helper: returns (require_role_factory, fake_user) bound to the
        given role. The fake get_current_user always succeeds with the
        same user; tests vary `user_role` to control the role check."""
        fake_user = _FakeUser(id="u1", role=user_role)

        async def fake_get_current_user(authorization=None):
            if not authorization:
                raise HTTPException(status_code=401, detail="Token ausente")
            return fake_user, "token-abc"

        def fake_get_user_role(user):
            return user.role

        require_role = make_require_role(fake_get_current_user, fake_get_user_role)
        return require_role, fake_user

    @pytest.mark.asyncio
    async def test_allows_when_role_in_allowed_list(self):
        require_role, fake_user = self._build(user_role="platform_admin")
        dep = require_role("platform_admin")
        user, token, role = await dep(authorization="Bearer xxx")
        assert user is fake_user
        assert token == "token-abc"
        assert role == "platform_admin"

    @pytest.mark.asyncio
    async def test_allows_when_role_in_multi_role_list(self):
        require_role, _ = self._build(user_role="clinic_admin")
        dep = require_role("platform_admin", "clinic_admin")
        _user, _token, role = await dep(authorization="Bearer xxx")
        assert role == "clinic_admin"

    @pytest.mark.asyncio
    async def test_rejects_when_role_not_allowed(self):
        require_role, _ = self._build(user_role="patient")
        dep = require_role("platform_admin")
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer xxx")
        assert exc.value.status_code == 403
        assert "platform_admin" in exc.value.detail

    @pytest.mark.asyncio
    async def test_propagates_401_from_get_current_user(self):
        # If product's get_current_user raises 401 (missing/invalid token),
        # the role check never runs — the 401 surfaces unchanged.
        require_role, _ = self._build()
        dep = require_role("platform_admin")
        with pytest.raises(HTTPException) as exc:
            await dep(authorization=None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_factory_produces_distinct_deps_per_role_set(self):
        require_role, _ = self._build(user_role="patient")
        admin_only = require_role("platform_admin")
        patient_or_admin = require_role("platform_admin", "patient")
        # Same factory; different bindings — patient_or_admin permits, admin_only doesn't.
        with pytest.raises(HTTPException):
            await admin_only(authorization="Bearer xxx")
        _u, _t, role = await patient_or_admin(authorization="Bearer xxx")
        assert role == "patient"

    @pytest.mark.asyncio
    async def test_error_detail_lists_all_allowed_roles(self):
        require_role, _ = self._build(user_role="patient")
        dep = require_role("platform_admin", "clinic_admin", "therapist")
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer xxx")
        assert "platform_admin" in exc.value.detail
        assert "clinic_admin" in exc.value.detail
        assert "therapist" in exc.value.detail


# ---------------------------------------------------------------------------
# make_get_current_user_org — factory pattern matching make_require_role
# ---------------------------------------------------------------------------
#
# Surfaced by personal-finance-wiring Phase 1 Verify-the-seed-ships-it test
# (2026-05-04). PF's local get_current_user_org + ERP's get_org_id shared the
# (user.user_metadata or {}).get("org_id") body — N=2 recurrence, formalized
# as make_get_current_user_org. This test class mirrors TestMakeRequireRole's
# shape (FakeUser dataclass + fake async get_current_user_fn + fake resolver).


@dataclass
class _FakeUserWithMetadata:
    """Minimal user shape — exposes user_metadata so resolvers see it."""
    id: str
    user_metadata: dict


class TestMakeGetCurrentUserOrg:
    """Cover the make_get_current_user_org factory + the bound dep.

    Coverage matrix:
    - happy path: required=True, org present → (user, token, org_id)
    - required=True, org missing → HTTPException(missing_status, missing_detail)
    - required=False, org missing → (user, token, None)
    - required=False, org present → (user, token, org_id)
    - custom missing_status (e.g. 400 to match ERP's local shape)
    - custom missing_detail
    - 401 propagation: get_current_user_fn raises → resolver never runs
    """

    def _build(self, *, org_id="org-123", **factory_kwargs):
        """Helper: returns (dep, fake_user) bound to the given org_id and
        factory kwargs. Fake get_current_user_fn always succeeds with the
        same user; tests vary org_id (set None to simulate missing org)."""
        fake_user = _FakeUserWithMetadata(
            id="u1",
            user_metadata={"org_id": org_id} if org_id else {},
        )

        async def fake_get_current_user(authorization=None):
            if not authorization:
                raise HTTPException(status_code=401, detail="Token ausente")
            return fake_user, "token-abc"

        def fake_get_org_id(user):
            return (user.user_metadata or {}).get("org_id")

        dep = make_get_current_user_org(
            fake_get_current_user,
            fake_get_org_id,
            **factory_kwargs,
        )
        return dep, fake_user

    @pytest.mark.asyncio
    async def test_happy_path_returns_tuple(self):
        """required=True (default), org present → returns (user, token, org_id)."""
        dep, fake_user = self._build(org_id="org-123")
        user, token, org_id = await dep(authorization="Bearer xxx")
        assert user is fake_user
        assert token == "token-abc"
        assert org_id == "org-123"

    @pytest.mark.asyncio
    async def test_required_true_raises_403_on_missing_org(self):
        """required=True (default), org missing → HTTPException(403, default detail)."""
        dep, _ = self._build(org_id=None)  # required=True default
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer xxx")
        assert exc.value.status_code == 403
        assert exc.value.detail == "Usuario sem organizacao associada"

    @pytest.mark.asyncio
    async def test_required_false_returns_none_on_missing_org(self):
        """required=False, org missing → (user, token, None) — no exception."""
        dep, fake_user = self._build(org_id=None, required=False)
        user, token, org_id = await dep(authorization="Bearer xxx")
        assert user is fake_user
        assert token == "token-abc"
        assert org_id is None

    @pytest.mark.asyncio
    async def test_required_false_returns_tuple_on_present_org(self):
        """required=False, org present → still returns the org_id (not coerced to None)."""
        dep, fake_user = self._build(org_id="org-456", required=False)
        user, token, org_id = await dep(authorization="Bearer xxx")
        assert user is fake_user
        assert org_id == "org-456"

    @pytest.mark.asyncio
    async def test_custom_missing_status_used(self):
        """required=True with missing_status=400 → ERP's local shape."""
        dep, _ = self._build(org_id=None, required=True, missing_status=400)
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer xxx")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_custom_missing_detail_used(self):
        """required=True with custom missing_detail → exception carries it verbatim."""
        dep, _ = self._build(
            org_id=None,
            required=True,
            missing_detail="Organizacao nao encontrada no perfil do usuario",
        )
        with pytest.raises(HTTPException) as exc:
            await dep(authorization="Bearer xxx")
        assert exc.value.detail == "Organizacao nao encontrada no perfil do usuario"

    @pytest.mark.asyncio
    async def test_propagates_401_from_get_current_user(self):
        """If get_current_user_fn raises 401 (missing/invalid token), resolver
        never runs — the 401 surfaces unchanged."""
        dep, _ = self._build(org_id="org-123")  # org present, but auth fails first
        with pytest.raises(HTTPException) as exc:
            await dep(authorization=None)
        assert exc.value.status_code == 401
        assert "Token ausente" in exc.value.detail

    @pytest.mark.asyncio
    async def test_resolver_receives_user_object(self):
        """The injected resolver is called with the user object returned by
        get_current_user_fn — not a dict, not the token. Validates the
        injection contract."""
        captured = {}

        fake_user = _FakeUserWithMetadata(id="u1", user_metadata={"org_id": "o1"})

        async def fake_get_current_user(authorization=None):
            return fake_user, "token-abc"

        def capturing_resolver(user):
            captured["user"] = user
            return (user.user_metadata or {}).get("org_id")

        dep = make_get_current_user_org(fake_get_current_user, capturing_resolver)
        await dep(authorization="Bearer xxx")
        assert captured["user"] is fake_user


# ---------------------------------------------------------------------------
# require_credential_or_422 — `ai-plumbing-seed-absorption` (2026-05-04)
# ---------------------------------------------------------------------------
#
# Filed by `projects/ai-plumbing-seed-absorption/` to absorb the byte-
# identical `_require_openai(org_id)` wrappers shipped today in PF + ERP
# `routers/ai.py`. Tests cover: present credential → returns string; absent
# credential + default detail; absent credential + custom detail; org_id=None
# pass-through; resolver raise → bubble up unchanged.


class TestRequireCredentialOr422:
    """Cover the require_credential_or_422 helper — HTTP-layer credential gate."""

    def test_present_credential_returns_value(self):
        # Patch `resolve_credential` at the lazy-import site (the function in
        # api.auth imports it lazily, so we patch the source module).
        with patch(
            "noctusai_lib.config.credentials.resolve_credential",
            return_value="sk-real-key-xyz",
        ):
            value = require_credential_or_422("openai_api_key", "org-1")
        assert value == "sk-real-key-xyz"

    def test_absent_credential_raises_422_with_default_detail(self):
        with patch(
            "noctusai_lib.config.credentials.resolve_credential",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc:
                require_credential_or_422("openai_api_key", "org-1")
        assert exc.value.status_code == 422
        assert "openai_api_key" in exc.value.detail
        assert "not configured" in exc.value.detail

    def test_absent_credential_with_custom_detail(self):
        custom = (
            "OpenAI API Key não configurada. "
            "Acesse Configurações > Chaves de API para configurar."
        )
        with patch(
            "noctusai_lib.config.credentials.resolve_credential",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc:
                require_credential_or_422(
                    "openai_api_key", "org-1", detail=custom
                )
        assert exc.value.status_code == 422
        assert exc.value.detail == custom

    def test_empty_string_credential_treated_as_absent(self):
        """Empty-string is falsy — same handling as None."""
        with patch(
            "noctusai_lib.config.credentials.resolve_credential",
            return_value="",
        ):
            with pytest.raises(HTTPException) as exc:
                require_credential_or_422("openai_api_key", "org-1")
        assert exc.value.status_code == 422

    def test_org_id_none_passes_through_to_resolver(self):
        """When org_id is None, the resolver is called with None — tier 1
        is skipped at the resolver level (platform-tier 2 is the entry)."""
        with patch(
            "noctusai_lib.config.credentials.resolve_credential",
            return_value="env-key",
        ) as mock_resolve:
            value = require_credential_or_422("openai_api_key")
        mock_resolve.assert_called_once_with("openai_api_key", None)
        assert value == "env-key"
