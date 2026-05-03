"""Tests for `noctusai_lib.integrations.supabase_identity`.

Coverage:
- Happy path: known user with full metadata → all fields populated.
- Missing nome metadata: falls through display_name chain.
- Empty email + empty nome: display_name returns "Usuário".
- API error per user_id: returns empty UserIdentity, doesn't raise.
- Empty input: empty dict.
- Duplicate user_ids: deduplicated in result.
- Falsy user_ids ("" / None): silently skipped.
- foto_url falls back to avatar_url; non-string values null'd.
- Single-user wrapper `fetch_user_identity()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

import pytest

from noctusai_lib.integrations.supabase_identity import (
    UserIdentity,
    fetch_user_identities,
    fetch_user_identity,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeUser:
    email: Optional[str] = None
    user_metadata: Optional[dict] = None


class _FakeAdminAuth:
    """Stand-in for `supabase.auth.admin` — returns canned users by id."""

    def __init__(self, users: dict):
        # Maps user_id → SimpleNamespace(user=...) | Exception | "no_user"
        self._users = users

    def get_user_by_id(self, user_id: str):
        entry = self._users.get(user_id)
        if isinstance(entry, Exception):
            raise entry
        if entry == "no_user":
            return SimpleNamespace(user=None)
        return SimpleNamespace(user=entry)


class _FakeAuth:
    def __init__(self, admin: _FakeAdminAuth):
        self.admin = admin


class _FakeClient:
    def __init__(self, users: dict):
        self.auth = _FakeAuth(_FakeAdminAuth(users))


# ---------------------------------------------------------------------------
# UserIdentity.display_name fallback chain
# ---------------------------------------------------------------------------


class TestDisplayNameFallback:
    def test_nome_wins_when_present(self):
        identity = UserIdentity(user_id="u1", nome="Alice", email="a@x.com")
        assert identity.display_name == "Alice"

    def test_falls_back_to_email_local_part(self):
        identity = UserIdentity(user_id="u1", nome="", email="alice@example.com")
        assert identity.display_name == "alice"

    def test_falls_back_to_usuario_when_nothing(self):
        identity = UserIdentity(user_id="u1", nome="", email="")
        assert identity.display_name == "Usuário"

    def test_falls_back_to_usuario_on_email_without_at_sign(self):
        # Defensive: an email lacking '@' shouldn't crash split or pass through.
        identity = UserIdentity(user_id="u1", nome="", email="malformed")
        assert identity.display_name == "Usuário"


# ---------------------------------------------------------------------------
# fetch_user_identities — batch
# ---------------------------------------------------------------------------


class TestFetchUserIdentitiesBatch:
    def test_happy_path_full_metadata(self):
        client = _FakeClient({
            "uid-a": _FakeUser(
                email="alice@example.com",
                user_metadata={"nome": "Alice Anderson", "foto_url": "https://x/a.png"},
            ),
        })
        result = fetch_user_identities(client, ["uid-a"])
        assert result == {
            "uid-a": UserIdentity(
                user_id="uid-a",
                nome="Alice Anderson",
                email="alice@example.com",
                foto_url="https://x/a.png",
            ),
        }

    def test_full_name_alias_for_nome(self):
        # Some SSO providers populate `full_name` rather than `nome`.
        client = _FakeClient({
            "uid-a": _FakeUser(
                email="bob@example.com",
                user_metadata={"full_name": "Bob Builder"},
            ),
        })
        result = fetch_user_identities(client, ["uid-a"])
        assert result["uid-a"].nome == "Bob Builder"

    def test_avatar_url_alias_for_foto_url(self):
        client = _FakeClient({
            "uid-a": _FakeUser(
                email="b@x.com",
                user_metadata={"avatar_url": "https://gravatar/b"},
            ),
        })
        result = fetch_user_identities(client, ["uid-a"])
        assert result["uid-a"].foto_url == "https://gravatar/b"

    def test_missing_metadata_returns_empty_strings(self):
        client = _FakeClient({
            "uid-a": _FakeUser(email="c@x.com", user_metadata=None),
        })
        result = fetch_user_identities(client, ["uid-a"])
        assert result["uid-a"].nome == ""
        assert result["uid-a"].email == "c@x.com"

    def test_lookup_error_returns_empty_identity(self):
        # API error must not crash the batch — failing IDs get an empty
        # UserIdentity so admin lists keep rendering.
        client = _FakeClient({
            "uid-a": RuntimeError("admin API down"),
            "uid-b": _FakeUser(email="b@x.com", user_metadata={"nome": "Beth"}),
        })
        result = fetch_user_identities(client, ["uid-a", "uid-b"])
        assert result["uid-a"] == UserIdentity(user_id="uid-a")
        assert result["uid-b"].nome == "Beth"

    def test_no_user_in_response_returns_empty_identity(self):
        # Some SDKs return resp.user = None when the user is missing
        # rather than raising. Treat as missing.
        client = _FakeClient({"uid-a": "no_user"})
        result = fetch_user_identities(client, ["uid-a"])
        assert result["uid-a"] == UserIdentity(user_id="uid-a")

    def test_empty_input_returns_empty_dict(self):
        client = _FakeClient({})
        assert fetch_user_identities(client, []) == {}

    def test_duplicate_ids_deduplicated(self):
        client = _FakeClient({
            "uid-a": _FakeUser(email="a@x.com", user_metadata={"nome": "Alice"}),
        })
        result = fetch_user_identities(client, ["uid-a", "uid-a", "uid-a"])
        assert list(result.keys()) == ["uid-a"]
        assert result["uid-a"].nome == "Alice"

    def test_falsy_ids_skipped(self):
        client = _FakeClient({
            "uid-a": _FakeUser(email="a@x.com"),
        })
        result = fetch_user_identities(client, ["uid-a", "", None])
        assert list(result.keys()) == ["uid-a"]

    def test_non_string_metadata_handled_defensively(self):
        # If user_metadata is somehow a list instead of a dict (legacy bad
        # data), the helper must coerce to empty strings rather than raise.
        client = _FakeClient({
            "uid-a": _FakeUser(email="x@x.com", user_metadata=["unexpected", "shape"]),
        })
        result = fetch_user_identities(client, ["uid-a"])
        assert result["uid-a"].nome == ""
        assert result["uid-a"].email == "x@x.com"

    def test_non_string_nome_value_coerced(self):
        # Defensive: if metadata.nome is e.g. an int, return "".
        client = _FakeClient({
            "uid-a": _FakeUser(email="x@x.com", user_metadata={"nome": 12345}),
        })
        result = fetch_user_identities(client, ["uid-a"])
        assert result["uid-a"].nome == ""

    def test_non_string_foto_url_dropped_to_none(self):
        client = _FakeClient({
            "uid-a": _FakeUser(
                email="x@x.com",
                user_metadata={"nome": "X", "foto_url": 42},
            ),
        })
        result = fetch_user_identities(client, ["uid-a"])
        assert result["uid-a"].foto_url is None


# ---------------------------------------------------------------------------
# fetch_user_identity — singular
# ---------------------------------------------------------------------------


class TestFetchUserIdentitySingular:
    def test_happy_path(self):
        client = _FakeClient({
            "uid-a": _FakeUser(email="a@x.com", user_metadata={"nome": "Alice"}),
        })
        identity = fetch_user_identity(client, "uid-a")
        assert identity.nome == "Alice"
        assert identity.email == "a@x.com"

    def test_lookup_error_returns_empty(self):
        client = _FakeClient({"uid-a": RuntimeError("oops")})
        identity = fetch_user_identity(client, "uid-a")
        assert identity == UserIdentity(user_id="uid-a")

    def test_falsy_user_id_returns_empty_without_calling_api(self):
        # Should never even attempt the lookup — return empty shape.
        client = _FakeClient({})  # Empty client; no IDs known.
        assert fetch_user_identity(client, "") == UserIdentity(user_id="")

    def test_none_user_id_returns_empty(self):
        client = _FakeClient({})
        # type: ignore[arg-type] — defensive against mistaken None.
        assert fetch_user_identity(client, None).user_id == ""  # type: ignore[arg-type]
