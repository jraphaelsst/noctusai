"""Tests for the invitation-acceptance half of `noctusai_lib.domain.org`.

`provision_invited_identity` + `attach_user_to_org` + `sync_org_metadata` are
what turn an accepted invitation into a person who can actually log in. Before
2026-08-07 the seed team router did none of it: it flipped the invitation row
to `accepted` and returned success, leaving the invitee with no identity, no
`public.noctus_users` profile and no org membership. Core's
`/api/sso/launch/{slug}` reads that profile row to mint an SSO token and 404s
"Perfil não encontrado" without it, so the invitee could not open ANY product.

Seam notes:

- `MockSupabaseClient.auth` is a `MagicMock`. Supabase Auth is an EXTERNAL
  service, so mocking it is the sanctioned boundary — not a monkey-patch of our
  own code (`KB § PATTERNS/backend/di-test-seam.md`).
- Table state is seeded through `set_table_data` and read back through
  `inserted_payloads` / `updated_payloads`, the mock's real read-side seams.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from noctusai_lib.domain.org import (
    attach_user_to_org,
    find_auth_user_id_by_email,
    provision_invited_identity,
    sync_org_metadata,
)
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _db(profiles: list | None = None) -> MockSupabaseClient:
    db = MockSupabaseClient(validate_schema=False, schema="public")
    db.set_table_data("noctus_users", profiles or [])
    return db


def _auth_user(user_id: str = USER):
    return SimpleNamespace(id=user_id)


# ---------------------------------------------------------------------------
# find_auth_user_id_by_email
# ---------------------------------------------------------------------------


class TestFindAuthUserIdByEmail:
    def test_finds_via_profile_row_without_listing_users(self):
        """The cheap path: our own record of the identity. `list_users` is a
        paged scan of every account on the platform — not something to run when
        one indexed row read answers the question."""
        db = _db([{"id": USER, "email": "a@test.com", "org_id": ORG_A}])
        assert find_auth_user_id_by_email(db, "a@test.com") == USER
        db.auth.admin.list_users.assert_not_called()

    def test_falls_back_to_list_users_when_no_profile(self):
        """A core signup that never joined an org has an `auth.users` row and
        NO profile — invisible to the cheap lookup, and exactly the case that
        must not be re-created as a duplicate identity."""
        db = _db([])
        db.auth.admin.list_users.return_value = [
            SimpleNamespace(id="other", email="someone@test.com"),
            SimpleNamespace(id=USER, email="a@test.com"),
        ]
        assert find_auth_user_id_by_email(db, "a@test.com") == USER

    def test_accepts_the_users_attribute_response_shape(self):
        """supabase-py has returned a bare list AND an object with `.users`
        across versions; both must resolve."""
        db = _db([])
        db.auth.admin.list_users.return_value = SimpleNamespace(
            users=[SimpleNamespace(id=USER, email="a@test.com")]
        )
        assert find_auth_user_id_by_email(db, "a@test.com") == USER

    def test_email_match_is_case_and_whitespace_insensitive(self):
        db = _db([])
        db.auth.admin.list_users.return_value = [
            SimpleNamespace(id=USER, email="  A@Test.COM ")
        ]
        assert find_auth_user_id_by_email(db, "a@test.com") == USER

    def test_unknown_email_returns_none(self):
        db = _db([])
        db.auth.admin.list_users.return_value = []
        assert find_auth_user_id_by_email(db, "nobody@test.com") is None

    def test_list_users_failure_returns_none_not_raise(self):
        """An auth-service hiccup must degrade to the create path, not 500 the
        acceptance before it starts."""
        db = _db([])
        db.auth.admin.list_users.side_effect = RuntimeError("auth down")
        assert find_auth_user_id_by_email(db, "a@test.com") is None


# ---------------------------------------------------------------------------
# provision_invited_identity
# ---------------------------------------------------------------------------


class TestProvisionInvitedIdentity:
    def test_creates_identity_with_email_confirmed(self):
        db = _db([])
        db.auth.admin.list_users.return_value = []
        db.auth.admin.create_user.return_value = SimpleNamespace(user=_auth_user())

        user_id, created = provision_invited_identity(
            db, email="new@test.com", password="hunter2", nome="Nova",
        )

        assert (user_id, created) == (USER, True)
        payload = db.auth.admin.create_user.call_args[0][0]
        assert payload["email"] == "new@test.com"
        assert payload["password"] == "hunter2"
        # The invite email already proved the address receives mail; a second
        # confirmation round-trip would strand the user mid-flow.
        assert payload["email_confirm"] is True
        assert payload["user_metadata"]["nome"] == "Nova"

    def test_existing_identity_is_linked_not_recreated(self):
        db = _db([{"id": USER, "email": "a@test.com", "org_id": None}])
        user_id, created = provision_invited_identity(
            db, email="a@test.com", password="whatever", nome="A",
        )
        assert (user_id, created) == (USER, False)
        db.auth.admin.create_user.assert_not_called()

    def test_existing_identity_password_is_NOT_reset(self):
        """The security property. An invitation link is not proof of control
        over an existing account — if accepting one could set that account's
        password, "invite someone" would become "take over their login"."""
        db = _db([{"id": USER, "email": "a@test.com", "org_id": None}])
        provision_invited_identity(
            db, email="a@test.com", password="attacker-chosen", nome="A",
        )
        db.auth.admin.create_user.assert_not_called()
        db.auth.admin.update_user_by_id.assert_not_called()

    def test_create_race_resolves_to_the_winning_identity(self):
        """Two accepts for one token: the loser's create fails, but the intent
        (this email has an identity) is satisfied — re-check before failing."""
        db = _db([])
        db.auth.admin.list_users.side_effect = [
            [],                                                # pre-create: absent
            [SimpleNamespace(id=USER, email="a@test.com")],    # post-failure: present
        ]
        db.auth.admin.create_user.side_effect = RuntimeError("already registered")

        assert provision_invited_identity(
            db, email="a@test.com", password="p", nome="A",
        ) == (USER, False)

    def test_create_failure_with_no_identity_raises_500(self):
        db = _db([])
        db.auth.admin.list_users.return_value = []
        db.auth.admin.create_user.side_effect = RuntimeError("boom")
        with pytest.raises(HTTPException) as exc:
            provision_invited_identity(db, email="a@test.com", password="p", nome="A")
        assert exc.value.status_code == 500

    def test_create_returning_no_user_raises_500(self):
        db = _db([])
        db.auth.admin.list_users.return_value = []
        db.auth.admin.create_user.return_value = SimpleNamespace(user=None)
        with pytest.raises(HTTPException) as exc:
            provision_invited_identity(db, email="a@test.com", password="p", nome="A")
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# attach_user_to_org
# ---------------------------------------------------------------------------


class TestAttachUserToOrg:
    def test_creates_profile_when_none_exists(self):
        db = _db([])
        row = attach_user_to_org(
            db, USER, org_id=ORG_A, email="a@test.com", nome="Alice", org_role="admin",
        )
        inserted = db.table("noctus_users").inserted_payloads
        assert len(inserted) == 1, inserted
        assert inserted[0]["id"] == USER
        assert inserted[0]["org_id"] == ORG_A
        assert inserted[0]["org_role"] == "admin"
        assert inserted[0]["email"] == "a@test.com"
        assert inserted[0]["nome"] == "Alice"
        assert row["org_id"] == ORG_A

    def test_platform_role_stays_user_even_for_an_admin_invite(self):
        """`org_role` is authority INSIDE one org; `role` is platform-wide. An
        org admin inviting someone must not be able to mint a platform admin."""
        db = _db([])
        attach_user_to_org(
            db, USER, org_id=ORG_A, email="a@test.com", nome="A", org_role="admin",
        )
        assert db.table("noctus_users").inserted_payloads[0]["role"] == "user"

    def test_nome_defaults_to_the_email_local_part(self):
        """`noctus_users.nome` is NOT NULL — a missing name must not become a
        constraint violation at the very end of an acceptance."""
        db = _db([])
        attach_user_to_org(db, USER, org_id=ORG_A, email="alice@test.com")
        assert db.table("noctus_users").inserted_payloads[0]["nome"] == "alice"

    def test_orgless_existing_profile_is_updated_not_duplicated(self):
        db = _db([{"id": USER, "email": "a@test.com", "nome": "A", "org_id": None}])
        attach_user_to_org(db, USER, org_id=ORG_A, email="a@test.com", org_role="member")
        assert db.table("noctus_users").inserted_payloads == []
        updates = db.table("noctus_users").updated_payloads
        assert updates == [{"org_id": ORG_A, "org_role": "member"}], updates

    def test_already_in_the_same_org_is_a_no_op(self):
        """A double-submitted accept must be idempotent, not a 500."""
        db = _db([{"id": USER, "email": "a@test.com", "nome": "A",
                   "org_id": ORG_A, "org_role": "member"}])
        row = attach_user_to_org(db, USER, org_id=ORG_A, email="a@test.com")
        assert row["org_id"] == ORG_A
        assert db.table("noctus_users").updated_payloads == []
        assert db.table("noctus_users").inserted_payloads == []

    def test_already_in_a_DIFFERENT_org_raises_409(self):
        """Membership is a single-org FK. Honouring the invite would EVICT the
        user from their current org, losing access to every product licensed to
        it. Refusing is the only non-destructive answer."""
        db = _db([{"id": USER, "email": "a@test.com", "nome": "A",
                   "org_id": ORG_B, "org_role": "owner"}])
        with pytest.raises(HTTPException) as exc:
            attach_user_to_org(db, USER, org_id=ORG_A, email="a@test.com")
        assert exc.value.status_code == 409
        assert "outra organizacao" in exc.value.detail

    def test_conflicting_membership_is_not_mutated(self):
        """The 409 must leave the existing membership untouched — a partial
        write here would be the eviction the guard exists to prevent."""
        db = _db([{"id": USER, "email": "a@test.com", "nome": "A",
                   "org_id": ORG_B, "org_role": "owner"}])
        with pytest.raises(HTTPException):
            attach_user_to_org(db, USER, org_id=ORG_A, email="a@test.com")
        assert db.table("noctus_users").updated_payloads == []
        assert db.table("noctus_users").inserted_payloads == []

    def test_default_org_role_is_member(self):
        db = _db([])
        attach_user_to_org(db, USER, org_id=ORG_A, email="a@test.com")
        assert db.table("noctus_users").inserted_payloads[0]["org_role"] == "member"


# ---------------------------------------------------------------------------
# sync_org_metadata
# ---------------------------------------------------------------------------


class TestSyncOrgMetadata:
    def test_writes_org_id_and_org_role(self):
        """Both are load-bearing: the seed's `get_org_id(user)` reads
        `user_metadata["org_id"]` and 403s without it, and the frontend's
        `resolveSSOContext` reads `org_role` to gate admin UI."""
        db = _db([])
        assert sync_org_metadata(
            db, USER, org_id=ORG_A, org_role="admin", nome="Alice",
        ) is True
        user_id_arg, payload = db.auth.admin.update_user_by_id.call_args[0]
        assert user_id_arg == USER
        assert payload["user_metadata"]["org_id"] == ORG_A
        assert payload["user_metadata"]["org_role"] == "admin"
        assert payload["user_metadata"]["nome"] == "Alice"

    def test_omits_nome_when_not_supplied(self):
        """Supabase merges user_metadata shallowly — writing `nome: None` would
        clobber a name the user already set."""
        db = _db([])
        sync_org_metadata(db, USER, org_id=ORG_A, org_role="member")
        payload = db.auth.admin.update_user_by_id.call_args[0][1]
        assert "nome" not in payload["user_metadata"]

    def test_failure_returns_false_instead_of_raising(self):
        """Best-effort by design: the membership row is the source of truth and
        core's SSO bridge re-syncs from it on every launch. Failing the accept
        here would undo work that already succeeded."""
        db = _db([])
        db.auth.admin.update_user_by_id.side_effect = RuntimeError("auth down")
        assert sync_org_metadata(db, USER, org_id=ORG_A, org_role="member") is False
