"""Unit tests for `noctusai_lib.domain.org.ensure_personal_org`.

The helper is the platform's personal-org bootstrap surface. PF (and any
future product needing solo-mode signup) calls it at first-login to
provision a Pessoal org + attach the user to it.

Idempotency, write-shape, and the noctus_users existence branches are
covered. No live DB; mocks per `KB § PATTERNS/testing.md`.
"""
from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.domain.org import _slugify, ensure_personal_org
from noctusai_lib.testing import MockSupabaseClient


def _run(coro):
    return asyncio.run(coro)


class TestSlugify:
    def test_lowercases_and_dashes(self):
        assert _slugify("Pessoal — alice@example.com") == "pessoal-alice-example-com"

    def test_collapses_whitespace_and_punctuation(self):
        assert _slugify("Hello, world!") == "hello-world"

    def test_empty_falls_back_to_pessoal(self):
        assert _slugify("---") == "pessoal"
        assert _slugify("") == "pessoal"


class TestEnsurePersonalOrgIdempotent:
    """If noctus_users.org_id already set, return it without writing."""

    def test_returns_existing_org_id_without_writes(self):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data(
            "noctus_users",
            [{"id": "u-1", "email": "a@x.com", "org_id": "org-existing"}],
        )

        org_id = _run(
            ensure_personal_org(db, "u-1", email="a@x.com")
        )

        assert org_id == "org-existing"
        # No org row created, no noctus_users mutation.
        assert db.table("organizations").inserted_payloads == []
        # noctus_users.inserted_payloads should be empty (no insert) — the
        # builder for `noctus_users` exists from set_table_data, but no
        # additional inserts were issued.
        assert db.table("noctus_users").inserted_payloads == []


class TestEnsurePersonalOrgFreshUser:
    """noctus_users row absent → create org + insert noctus_users."""

    def test_creates_org_and_provisions_user_row(self):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data("noctus_users", [])  # user not in noctus_users yet
        db.set_table_data("organizations", [])

        org_id = _run(
            ensure_personal_org(db, "u-new", email="bob@example.com")
        )

        assert org_id  # truthy uuid-or-mock-id
        org_inserts = db.table("organizations").inserted_payloads
        assert len(org_inserts) == 1
        org = org_inserts[0]
        assert org["nome"] == "Pessoal — bob@example.com"
        assert org["owner_id"] == "u-new"
        assert org["is_personal"] is True
        assert org["category"] == "normal"
        assert org["slug"].startswith("pessoal-bob-example-com")

        user_inserts = db.table("noctus_users").inserted_payloads
        assert len(user_inserts) == 1
        u = user_inserts[0]
        assert u["id"] == "u-new"
        assert u["email"] == "bob@example.com"
        assert u["nome"] == "bob"  # default = local part
        assert u["org_id"] == org_id
        assert u["role"] == "user"
        assert u["org_role"] == "owner"

    def test_respects_explicit_nome(self):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data("noctus_users", [])

        _run(ensure_personal_org(db, "u-2", email="b@x.com", nome="Beth"))
        users = db.table("noctus_users").inserted_payloads
        assert users[0]["nome"] == "Beth"

    def test_respects_custom_name_template(self):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data("noctus_users", [])

        _run(
            ensure_personal_org(
                db,
                "u-3",
                email="c@x.com",
                name_template="Solo: {email}",
            )
        )
        orgs = db.table("organizations").inserted_payloads
        assert orgs[0]["nome"] == "Solo: c@x.com"

    def test_is_personal_can_be_overridden(self):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data("noctus_users", [])

        _run(
            ensure_personal_org(
                db, "u-4", email="d@x.com", is_personal=False
            )
        )
        orgs = db.table("organizations").inserted_payloads
        assert orgs[0]["is_personal"] is False


class TestEnsurePersonalOrgDefensiveBranch:
    """Existing noctus_users row WITHOUT org_id (defensive — FK NOT NULL means
    this shouldn't happen in practice but the helper still handles it)."""

    def test_updates_existing_user_row_without_re_inserting(self):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data(
            "noctus_users",
            [{"id": "u-5", "email": "e@x.com", "org_id": None}],
        )

        org_id = _run(
            ensure_personal_org(db, "u-5", email="e@x.com")
        )

        assert org_id
        # Org was created.
        assert len(db.table("organizations").inserted_payloads) == 1
        # noctus_users INSERT did NOT happen (existing row was updated).
        assert db.table("noctus_users").inserted_payloads == []


class TestEnsurePersonalOrgFailureModes:
    def test_raises_when_org_insert_returns_empty(self):
        db = MockSupabaseClient(validate_schema=False)
        db.set_table_data("noctus_users", [])
        # Force the org insert to return an empty data set.
        from noctusai_lib.testing import MockSupabaseResponse

        db.set_sequential_responses(
            "organizations", [MockSupabaseResponse(data=[])]
        )

        with pytest.raises(RuntimeError, match="organizations insert returned empty"):
            _run(ensure_personal_org(db, "u-9", email="f@x.com"))
